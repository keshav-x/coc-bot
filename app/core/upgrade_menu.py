'''Builder-popup ("upgrade menu") reader for the auto-maxer.

Parses a frame showing the open builder popup into structured :class:`UpgradeRow`
entries (label, section, cost, resource, affordability, click point), and reads the
top-HUD builder chip (free/total builders). Vision only — no clicks.

The popup lists rows in three sections: "Upgrades in progress:" (label + remaining
time), "Suggested upgrades:" and "Other upgrades:" (label [+ xN multiplier] + resource
icon + cost). Cost text is white when affordable and red when not; red text falls
below the white-text binarization floor, so red rows are detected by hue in the cost
zone instead of OCR (their numeric cost stays unknown — the policy only acts on
affordable rows anyway).

Geometry notes (fractions of the frame, 16:9 verified live): the popup's label column
spans ~x 0.40-0.50, the cost column ~x 0.50-0.63; the popup is translucent, so village
pixels bleed through and OCR picks up stray words — the x/y fences below are what keep
that noise out of rows.
'''
import difflib
from dataclasses import dataclass, replace
from typing import List, Optional, Tuple

import cv2

from app.services.vision import VisionService
from app.utils.logger import setup_logger

logger = setup_logger('UpgradeMenu')

SECTION_IN_PROGRESS = 'in_progress'
SECTION_SUGGESTED = 'suggested'
SECTION_OTHER = 'other'

RESOURCE_GOLD = 'gold'
RESOURCE_ELIXIR = 'elixir'
RESOURCE_DARK = 'dark_elixir'

_MIN_COST_DIGITS = 4  # real costs are 5+ digits at TH10+; multiplier/time digits are 1-3
_MIN_COST_VALUE = 1000  # a dropped leading digit leaves '000000' → value 0 (live repro: "Mortar 0 gold")
# Sanity ceiling against OCR digit-merging (live repro: 87M "Air Defense"). Must clear
# the most expensive real upgrade at the HIGHEST Town Hall (TH17-era buildings run past
# 20M) — bump this when a game update crosses it, or cheap rows will still parse but
# the priciest late-game rows silently vanish from the scan.
_MAX_COST_VALUE = 40000000
_COST_GAP_CHAR_WIDTHS = 2.5  # x-gap (in median char widths) separating "x4" from the cost digits
_RED_COST_FRACTION = 0.04  # red text is sparse in the wide cost zone
_LABEL_X_MIN_FRAC = 0.395  # label column fence (left)
_LABEL_X_MAX_FRAC = 0.50  # label column fence (right) — beyond this live times/costs, not names
_COST_X_MIN_FRAC = 0.50  # cost column fence (left)
_COST_X_MAX_FRAC = 0.66  # cost column fence (right) — OCR glyph boxes inflate past the visual text
_ROW_Y_MIN_FRAC = 0.09  # rows live below the top HUD chips
_ICON_PATCH_HEIGHTS = 2.2  # resource icon sits within this many text-heights left of the cost


@dataclass(frozen = True)
class UpgradeRow:
    '''One row of the builder popup, in full-frame coordinates.'''
    label: str
    section: str  # SECTION_* ('' when no section header was visible above the row)
    cost: Optional[int]  # parsed white cost; None for in-progress / red / unparsed rows
    resource: Optional[str]  # RESOURCE_* from the icon left of the cost; None when unknown
    affordable: Optional[bool]  # True: white cost parsed; False: cost zone reads red; None: unknown
    center: Tuple[int, int]  # label center — the row's click target
    line_y: int


def _normalize_label(text):
    return ' '.join((text or '').lower().split())


def is_wall_row(row):
    return any(t.startswith('wall') for t in _normalize_label(row.label).split())


def is_town_hall_row(row):
    '''Fuzzy on purpose — this exclusion is what keeps the maxer off the Town Hall,
    and OCR mangles the label ('TownMall', 'TownHail', 'TownHali' — all live) past
    any exact substring check. Priciest-first made this a live bug: the TH row is
    the most expensive row on the board, so a mangled TH label became the top pick
    (the red-cost veto blocked the actual purchase 14× — but the pick wasted every
    pass until cooldown).'''
    compact = _normalize_label(row.label).replace(' ', '')
    if 'townhall' in compact:
        return True
    # Probe the prefix too: trailing OCR junk ('townmallx2') dilutes the full-string
    # ratio below threshold while the first 8 chars still read as the Town Hall.
    return any(difflib.SequenceMatcher(None, probe, 'townhall').ratio() >= 0.8
               for probe in (compact, compact[:8]))


def _line_text(words):
    return ' '.join(w.text for w in sorted(words, key = (lambda b: b.left)))


_HEADER_CANON = (
    ('upgradesinprogress', SECTION_IN_PROGRESS),
    ('suggestedupgrades', SECTION_SUGGESTED),
    ('otherupgrades', SECTION_OTHER))


def _match_section_header(line_text):
    t = line_text.lower()
    if 'progress' in t:
        return SECTION_IN_PROGRESS
    if 'suggested' in t:
        return SECTION_SUGGESTED
    if 'other' in t and 'upgrade' in t:
        return SECTION_OTHER
    # Live OCR mangles header words ("Upgradesinpragress", "Geher upgrades") — fuzzy-match
    # the compacted text against the canonical headers before treating the line as a row.
    compact = ''.join(ch for ch in t if ch.isalpha())
    for canon, section in _HEADER_CANON:
        if difflib.SequenceMatcher(None, compact, canon).ratio() >= 0.72:
            return section
    return None


def _split_digit_segments(chars):
    '''Split a line's digit chars (sorted by left) on large x-gaps → list of segments.'''
    chars = sorted(chars, key = (lambda c: c.left))
    if not chars:
        return []
    widths = sorted(c.width for c in chars)
    med_w = max(1, widths[len(widths) // 2])
    segments = [[chars[0]]]
    for prev, cur in zip(chars, chars[1:]):
        gap = cur.left - (prev.left + prev.width)
        if gap > _COST_GAP_CHAR_WIDTHS * med_w:
            segments.append([])
        segments[-1].append(cur)
    return segments


def _segment_value_and_bbox(segment):
    text = ''.join(c.text for c in segment).replace('l', '1')
    if not text.isdigit():
        return (None, None)
    left = min(c.left for c in segment)
    top = min(c.top for c in segment)
    right = max(c.left + c.width for c in segment)
    bottom = max(c.top + c.height for c in segment)
    return (int(text), (left, top, right - left, bottom - top))


def _classify_resource_icon(frame, cost_bbox):
    '''Sample the icon patch immediately left of the cost text. Gold coin → yellow,
    elixir drop → bright pink; the dark-elixir drop is too dark for either mask, so
    "neither" classifies as dark. The popup is translucent, so floors are tuned to
    survive village bleed-through (verified against known rows in saved frames).'''
    (left, top, _w, h) = cost_bbox
    (fh, fw) = frame.shape[:2]
    pad = 2
    unit = max(8, h)
    # OCR glyph boxes drift ~1 char left of the visual text, so the icon straddles the
    # reported left edge — sample both sides of it (digits are white, hue-neutral).
    x0 = max(0, left - int(1.8 * unit))
    x1 = min(fw, left + int(0.8 * unit))
    y0 = max(0, top - pad)
    y1 = min(fh, top + h + pad)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None
    patch = frame[y0:y1, x0:x1]
    yf = VisionService.yellow_fraction(patch)
    pf = VisionService.pink_fraction(patch)
    pf_bright = VisionService.pink_fraction(patch, val_floor = 140)
    pf_vivid = VisionService.pink_fraction(patch, val_floor = 170)
    logger.debug('icon patch @x%d-%d y%d-%d: yellow=%.2f pink=%.2f bright=%.2f vivid=%.2f', x0, x1, y0, y1, yf, pf, pf_bright, pf_vivid)
    if yf >= 0.10 and yf >= pf:
        return RESOURCE_GOLD
    if pf_vivid >= 0.05:
        # The elixir drop is bright magenta; the dark-elixir drop's purple body is
        # pink-hued too but dark, so only elixir survives the high value floor
        # (measured: elixir icons 0.08-0.20 vivid, dark-elixir icons 0.00).
        return RESOURCE_ELIXIR
    if pf >= 0.10:
        # Dark elixir: pink-hued but dark (measured 0.16-0.41 at the default value
        # floor on real DE rows; the crafting-ball icon and a missed patch read ~0.00).
        return RESOURCE_DARK
    # Neither gold, elixir, nor dark — an unknown currency. Live repro: crafted
    # seasonal defenses (Cake-A-Pult) list component upgrades here priced in a
    # CRAFTING currency (a black ball icon, ~0.0 pink) that the fallthrough used to
    # call "dark" — the policy then chased 30k phantom-bargains it must never buy.
    # Unknown resource = unspendable row; every future seasonal currency self-excludes.
    return None


def _ocr_label_words(frame):
    '''Letter OCR in the top-center band, fenced to the popup's label column; runs both
    polarities and keeps the richer pass. Single-char words are dropped (time units
    H/M, multiplier x) — no building name has them.'''
    (fh, fw) = frame.shape[:2]
    x_min = int(fw * _LABEL_X_MIN_FRAC)
    x_max = int(fw * _LABEL_X_MAX_FRAC)
    y_min = int(fh * _ROW_Y_MIN_FRAC)
    best = []
    for white in (False, True):
        words = VisionService.ocr_letters_top_center(frame, white_text = white, cc_filter_blobs = False)
        words = [
            w for w in words
            if len(w.text.strip()) >= 2 and x_min <= w.left < x_max and w.top >= y_min]
        if len(words) > len(best):
            best = words
    return best


def _collect_label_lines(words):
    '''Cluster label word boxes into text lines sorted top-to-bottom.'''
    if not words:
        return []
    heights = sorted(w.height for w in words)
    med_h = max(1, heights[len(heights) // 2])
    # Row pitch is ~2.5x the text height; one row's fragments can sit ~1 text-height
    # apart vertically, so tolerate a full height without bridging adjacent rows.
    y_tol = max(10, med_h)
    return VisionService.cluster_ocr_boxes_by_y(words, y_tol)


def parse_builder_menu(frame, initial_section = ''):
    '''Parse one frame of the open builder popup → list of :class:`UpgradeRow`
    (top to bottom). ``initial_section`` carries the running section across scroll
    steps when the header has scrolled above the fold.'''
    if frame is None or frame.size == 0:
        return []
    (fh, fw) = frame.shape[:2]
    roi = VisionService.top_middle_square_roi(fw, fh)

    lines = _collect_label_lines(_ocr_label_words(frame))

    # White-cost digits as raw per-line char clusters, so multiplier digits ("x4") can
    # be split off by x-gap; the rightmost segment inside the cost column is the cost.
    char_clusters = []
    VisionService.extract_grouped_numbers_in_region(
        frame, roi, white_text = True, cc_filter_blobs = False,
        allow_hud_ocr_debug = True, hud_debug_char_clusters_out = char_clusters)
    cost_x_min = int(fw * _COST_X_MIN_FRAC)
    cost_x_max = int(fw * _COST_X_MAX_FRAC)
    costs = []  # (line_cy, value, bbox)
    for chars in char_clusters:
        segments_dbg = _split_digit_segments(chars)
        if segments_dbg and logger.isEnabledFor(10):
            logger.debug('cost cluster y~%d: %s', int(sum(c.top for c in chars) / max(1, len(chars))),
                         [(''.join(c.text for c in s), min(c.left for c in s), max(c.left + c.width for c in s)) for s in segments_dbg])
        # Right-to-left: village digits bleeding through right of the popup can share
        # the line — take the rightmost segment that passes every cost filter.
        for seg in reversed(_split_digit_segments(chars)):
            if len(seg) < _MIN_COST_DIGITS:
                continue
            (value, bbox) = _segment_value_and_bbox(seg)
            if value is None or value % 100 != 0:
                # Every real cost is a round number; bleed-through digits are not.
                continue
            if not _MIN_COST_VALUE <= value <= _MAX_COST_VALUE:
                continue
            (bx, _by, bw, _bh) = bbox
            if bx < cost_x_min or bx + bw > cost_x_max:
                continue
            costs.append((bbox[1] + bbox[3] * 0.5, value, bbox))
            break

    # First pass: line geometry + running section.
    infos = []
    section = initial_section or ''
    for line in lines:
        text = _line_text(line)
        header = _match_section_header(text)
        if header:
            section = header
            continue
        if 'available' in text.lower() or len(text) < 3:
            continue
        if max(len(w) for w in text.split()) < 4:
            # Village bleed-through produces lines of short fragments ("we BN hie");
            # every real building name has at least one 4+ letter word.
            continue
        tops = [w.top for w in line]
        bottoms = [w.top + w.height for w in line]
        infos.append({
            'text': text,
            'section': section,
            'y': int((min(tops) + max(bottoms)) / 2),
            'h': max(bottoms) - min(tops),
            'left': min(w.left for w in line),
            'right': max(w.left + w.width for w in line),
            'top': min(tops),
            'bottom': max(bottoms) })

    # Global cost→line assignment: nearest line within tolerance, one cost per line.
    assigned = {}
    for ci, (cy, _value, _bbox) in enumerate(costs):
        best = None
        best_d = None
        for li, info in enumerate(infos):
            if info['section'] == SECTION_IN_PROGRESS:
                continue
            d = abs(info['y'] - cy)
            if d <= max(10, info['h']) and (best_d is None or d < best_d):
                (best, best_d) = (li, d)
        if best is not None and (best not in assigned or best_d < assigned[best][0]):
            assigned[best] = (best_d, ci)

    rows = []
    for li, info in enumerate(infos):
        cost = None
        resource = None
        affordable = None
        if li in assigned:
            (_d, ci) = assigned[li]
            (_cy, cost, bbox) = costs[ci]
            resource = _classify_resource_icon(frame, bbox)
            affordable = True
        elif info['section'] and info['section'] != SECTION_IN_PROGRESS:
            # No white cost — red (unaffordable) if the cost zone shows red text.
            zx0 = min(info['right'] + 4, cost_x_min)
            zx1 = min(cost_x_max, fw)
            zy0 = max(0, info['top'] - 2)
            zy1 = min(fh, info['bottom'] + 2)
            if zx1 - zx0 >= 8 and zy1 - zy0 >= 4:
                if VisionService.red_hue_fraction(frame[zy0:zy1, zx0:zx1]) >= _RED_COST_FRACTION:
                    affordable = False
        rows.append(UpgradeRow(
            label = info['text'], section = info['section'], cost = cost,
            resource = resource, affordable = affordable,
            center = ((info['left'] + info['right']) // 2, info['y']), line_y = info['y']))
    return rows


def _find_fuzzy_key(by_label, key, row):
    '''OCR-variant dedupe: map ``key`` onto an existing key when they are clearly the
    same row. ≥0.90 similarity always merges; 0.80-0.90 only with matching parsed
    cost+resource — that keeps "Spell Factory" (0.86 vs "Dark Spell Factory", both
    costless RED rows) apart while collapsing "GiantBombx"/"GiantBornbxt" (same cost).'''
    a = key.replace(' ', '')
    for k, held in by_label.items():
        b = k.replace(' ', '')
        ratio = difflib.SequenceMatcher(None, a, b).ratio()
        if ratio >= 0.9:
            return k
        if ratio >= 0.8 and row.cost is not None and row.cost == held.cost and row.resource == held.resource:
            return k
    return None


def merge_rows(existing, new_rows):
    '''Merge rows parsed at different scroll positions, deduped by normalized label
    (with OCR-variant fuzzy matching). Prefers entries that carry a section / cost.'''
    by_label = {}
    order = []
    for row in list(existing) + list(new_rows):
        key = _normalize_label(row.label)
        if not key:
            continue
        if key not in by_label:
            fuzzy = _find_fuzzy_key(by_label, key, row)
            if fuzzy is not None:
                key = fuzzy
        held = by_label.get(key)
        if held is None:
            by_label[key] = row
            order.append(key)
            continue
        better = row
        if (held.section and not row.section) or (held.cost is not None and row.cost is None):
            better = held
        elif held.resource is not None and row.resource is None and held.cost == row.cost:
            # Icon-patch sampling misses the icon on some sightings (measured: the same
            # Barbarian King row reads pink=0.16 → dark in one frame, 0.00 → unknown in
            # another) — a sighting that resolved the resource outranks one that didn't.
            better = held
        if held.cost is not None and row.cost is not None and held.cost != row.cost:
            # Sightings disagree on the cost: OCR drops LEADING digits, which always
            # shrinks the number (live repro: 'Workshop 1000000e' beside the real
            # 11000000e — the fake bargain then outbids every real row as "cheapest").
            # The larger sighting is the true cost.
            bigger = held if held.cost > row.cost else row
            if better.cost != bigger.cost:
                better = replace(better, cost = bigger.cost,
                                 resource = bigger.resource or better.resource,
                                 affordable = bigger.affordable if bigger.affordable is not None else better.affordable)
        if not better.section and (held.section or row.section):
            better = replace(better, section = held.section or row.section)
        by_label[key] = better
    return [by_label[k] for k in order]


# Top-HUD "free/total" chips. Each ROI covers only the chip's text — including the
# icon inside it (builder face / lab flask) breaks Tesseract's single-line
# segmentation (a huge bright blob next to three small glyphs).
_BUILDER_CHIP_ROI_FRAC = (0.489, 0.018, 0.05, 0.048)  # x, y, w, h as fractions of the frame
# Lab chip ("0/1" with a flask+sword icon) sits immediately left of the builder chip.
# Calibrated on live 1299x731 frames: text spans x 513-563, y 25-45. Keep the ROI top
# BELOW y_frac 0.026 — the bobbing "i" info-bubble above the chip dips into a taller
# ROI and breaks PSM7 line segmentation (live repro: '0' dropped, read '1').
_LAB_CHIP_ROI_FRAC = (0.394, 0.026, 0.048, 0.036)


def _parse_fraction_chip(frame, roi_frac, max_total):
    '''Read a top-HUD "free/total" chip → ``(free, total)`` or ``None``.
    The slash is not in the digit whitelist, so it appears as a gap (or an ``l`` → ``1``).
    The chips are translucent — animated village pixels behind the glyphs push the
    binarization over/under threshold frame to frame (live repro: identical-looking
    frames 2s apart read '01', '1', nothing) — so escalate through upscales/polarity
    until one pass parses.'''
    if frame is None or frame.size == 0:
        return None
    (fh, fw) = frame.shape[:2]
    (rx, ry, rw, rh) = roi_frac
    roi = (int(fw * rx), int(fh * ry), int(fw * rw), int(fh * rh))
    for upscale, white in ((6, True), (8, True), (6, False)):
        parsed = _parse_fraction_chip_once(frame, roi, max_total, upscale, white)
        if parsed is not None:
            return parsed
    return None


def _parse_fraction_chip_once(frame, roi, max_total, roi_upscale, white_text):
    clusters = []
    VisionService.extract_grouped_numbers_in_region(
        frame, roi, white_text = white_text, cc_filter_blobs = False, roi_upscale = roi_upscale,
        tesseract_config = '--psm 7 -c tessedit_char_whitelist=0123456789l/',
        allow_hud_ocr_debug = True, hud_debug_char_clusters_out = clusters)
    logger.debug('chip roi=%s upscale=%s white=%s clusters=%s', roi, roi_upscale, white_text, [[c.text for c in cl] for cl in clusters])
    for chars in clusters:
        segments = _split_digit_segments([c for c in chars if c.text.isdigit() or c.text == 'l'])
        digits = [''.join(c.text for c in seg).replace('l', '1') for seg in segments]
        digits = [d for d in digits if d.isdigit()]
        if not digits:
            continue
        if len(digits) >= 2:
            (free_s, total_s) = (digits[0], digits[-1])
        elif len(digits[0]) == 2:
            (free_s, total_s) = (digits[0][0], digits[0][1])
        elif len(digits[0]) == 3 and digits[0][1] == '1':
            # slash OCR'd as l→1 and merged: "1/6" → "116"
            (free_s, total_s) = (digits[0][0], digits[0][2])
        else:
            continue
        (free, total) = (int(free_s), int(total_s))
        if 0 <= free <= total <= max_total:
            return (free, total)
    return None


def parse_builder_chip(frame):
    '''Top-HUD builder chip → ``(free, total)`` builders, or ``None``.
    max_total 6: the Home Village never has more builders — and dialog screens leak
    stray digits into the chip ROI (live repro: an upgrade confirm screen read as
    "8/8" and passed the old ≤8 bound, poisoning the post-upgrade verification).'''
    return _parse_fraction_chip(frame, _BUILDER_CHIP_ROI_FRAC, max_total = 6)


def parse_lab_chip(frame):
    '''Top-HUD laboratory chip (flask+sword icon, "0/1") → ``(free, total)`` research
    slots, or ``None`` when unreadable/absent (no laboratory yet, or the chip band is
    covered). total ≤ 2 also keeps a stray read of the builder chip ("0/6") from being
    mistaken for the lab.'''
    return _parse_fraction_chip(frame, _LAB_CHIP_ROI_FRAC, max_total = 2)
