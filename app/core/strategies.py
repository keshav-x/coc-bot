"""Attack strategies – exact port of BasePilot reference implementation.

All core algorithms (arc sampling, earthquake polygon, diamond perimeter, even
perimeter spacing, hero placement) are taken verbatim from the BasePilot source
to ensure 100% compatible behaviour.
"""

from __future__ import annotations

import math
import random
import time
from typing import Any, List, Optional, Tuple

from app.config import ASPECT_16_9, Config
from app.services.input import InputService
from app.services.vision import VisionService
from app.utils.logger import setup_logger
from app.utils.profile_settings_store import (
    EARTHQUAKE_METHOD_CURVE,
    EARTHQUAKE_METHOD_RANDOM,
)

logger = setup_logger("Strategies")

_EARTHQUAKE_REGION_ARC_SAMPLES = 49
_EARTHQUAKE_RANDOM_LINE_FROM_BOTTOM = (4, 10)
_EDRAG_COUNT = 12
_EDRAG_DELAY = 0.2
_EDRAG_CORNER_MARGIN = 100
_DIAMOND_EDGES = (("left", "top"), ("top", "right"))


class AttackStrategy:
    """Base class for attack strategies."""

    def __init__(
        self,
        input_service: InputService,
        vision_service: VisionService,
        config: Config,
        stop_event: Optional[Any] = None,
        earthquake_method: str = EARTHQUAKE_METHOD_CURVE,
    ) -> None:
        self.input = input_service
        self.vision = vision_service
        self.config = config
        self.stop_event = stop_event
        self.earthquake_method = earthquake_method
        self.CORNER_ORDER = ["left", "top", "right", "bottom"]

    def execute(self, frame: Any, stop_event: Optional[Any] = None) -> bool:
        raise NotImplementedError

    def _expand_loc(self, x: int, y: int) -> Tuple[int, int]:
        try:
            from app.services.antiban import AntiBanService
            if not AntiBanService().config.random_clicks_enabled:
                return (x, y)
        except Exception:
            pass
        return (x + random.randint(-10, 10), y + random.randint(-10, 10))

    def _sync_frame_size(self, frame: Any) -> None:
        self.config.set_target_size_from_frame(frame)

    def _point(self, key: str) -> Tuple[int, int]:
        return self.config.get_point(key)

    def _quantize_deploy_to_frame(self, x: int, y: int, frame_w: int, frame_h: int) -> Tuple[int, int]:
        """Clamp deploy coordinates to valid red-line exterior grass."""
        min_x = int(frame_w * 0.08)
        max_x = int(frame_w * 0.92)
        min_y = int(frame_h * 0.12)
        max_y = int(frame_h * 0.81)
        cx = max(min_x, min(max_x, int(x)))
        cy = max(min_y, min(max_y, int(y)))
        return (cx, cy)

    def deploy_multi_wave(
        self,
        troop_x: int,
        troop_y: int,
        start_pt: Tuple[int, int],
        end_pt: Tuple[int, int],
        count_per_wave: int = 4,
        num_waves: int = 1,
        delay: float = 0.05,
    ) -> None:
        """Surgical multi-wave deployment along a line segment between start_pt and end_pt."""
        self.input.click(troop_x, troop_y, pause=0.15, rand=False)
        w, h = 1920, 1080
        if self.config:
            sz = getattr(self.config, "target_size", None)
            if sz:
                w, h = sz
        for _ in range(num_waves):
            if self.stop_event and self.stop_event.is_set():
                break
            for i in range(count_per_wave):
                t = i / max(1, count_per_wave - 1)
                x = int(start_pt[0] + t * (end_pt[0] - start_pt[0]))
                y = int(start_pt[1] + t * (end_pt[1] - start_pt[1]))
                cx, cy = self._quantize_deploy_to_frame(x, y, w, h)
                self.input.click(cx, cy, pause=delay, rand=True)

    def _scaled_deployment_data(self) -> dict:
        return {key: self._point(key) for key in self.CORNER_ORDER}

    def deploy_heroes(self, frame: Any) -> None:
        self._sync_frame_size(frame)
        heroes = ["queen", "warden", "RC", "king", "prince", "dragonduke"]
        random.shuffle(heroes)
        deployed_heroes = []
        roi = self.vision.bottom_half_region(frame)
        ix, iy = self.vision.find_template(frame, "loglauncher.png", threshold=0.7, region=roi)
        if not ix:
            ix, iy = self.vision.find_template(frame, "siegebarracks.png", threshold=0.7, region=roi)
        if ix:
            deploy_point = self._get_hero_deploy_point(frame)
            self.input.click(ix, iy, pause=0.2, rand=False)
            self.input.click(*deploy_point, pause=0.2)
        for hero in heroes:
            bx, by = self.vision.find_template(frame, f"{hero}.png", threshold=0.7, region=roi)
            if not bx:
                continue
            deploy_point = self._get_hero_deploy_point(frame)
            self.input.click(bx, by, pause=0.2, rand=False)
            self.input.click(*deploy_point, pause=0.2)
            deployed_heroes.append((bx, by))
        for hx, hy in deployed_heroes:
            self.input.click(hx, hy, pause=0.2)
            if self.stop_event:
                self.stop_event.wait(random.uniform(0.1, 0.2))
            else:
                time.sleep(random.uniform(0.1, 0.2))

    def _hero_corner_xy(self, corner: str) -> Tuple[int, int]:
        """Corner used when building hero deploy lines; on 16_9, ``top`` is nudge-scaled."""
        px, py = self.config.get_point(corner)
        if self.config.aspect_key == ASPECT_16_9 and corner == "top":
            py -= self.config.scale_scalar(70)
        return (int(px), int(py))

    @staticmethod
    def _quantize_deploy_to_frame(
        px: float, py: float, fw: int, fh: int
    ) -> Tuple[int, int]:
        """Clamp to [0, fw-1] x [0, fh-1], round to nearest pixels."""
        if fw <= 0 or fh <= 0:
            return (int(round(px)), int(round(py)))
        cx = max(0, min(float(fw - 1), float(px)))
        cy = max(0, min(float(fh - 1), float(py)))
        return (int(round(cx)), int(round(cy)))

    def _get_hero_deploy_point(self, frame: Any = None) -> Tuple[int, int]:
        c_name = random.choice(["top", "right", "left"])
        c1x, c1y = self._hero_corner_xy(c_name)
        if c_name in ("left", "right"):
            c2x, c2y = self._hero_corner_xy("top")
        else:
            corner = random.choice(["left", "right"])
            c2x, c2y = self._hero_corner_xy(corner)
        t = random.uniform(0, 1)
        xf = c1x + (c2x - c1x) * t
        yf = c1y + (c2y - c1y) * t
        if frame is not None and getattr(frame, "size", 0):
            fh, fw = frame.shape[:2]
            return self._quantize_deploy_to_frame(xf, yf, fw, fh)
        return (int(round(xf)), int(round(yf)))

    @staticmethod
    def _earthquake_anchor_triplet(
        data: dict, offset: int
    ) -> Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]:
        """Left / top / right drop anchors (same nudge as legacy earthquake logic)."""
        lx, ly = data["left"]
        lx += int(offset * 1.3)
        tx, ty = data["top"]
        ty += int(offset)
        rx, ry = data["right"]
        rx -= int(offset * 1.3)
        return ((float(lx), float(ly)), (float(tx), float(ty)), (float(rx), float(ry)))

    @staticmethod
    def _sample_arc_through_three(
        ltr: Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]],
        n: int,
    ) -> List[Tuple[int, int]]:
        """n points along a circular arc from L to R that passes through T.
        If L, T, R are collinear uses a quadratic Bezier.
        """
        L, T, R = ltr
        ax, ay = L
        bx, by = T
        cx, cy = R
        d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
        if n < 2:
            return [(int(round(L[0])), int(round(L[1])))]
        if abs(d) < 1e-6:
            p1x = 2 * bx - 0.5 * ax - 0.5 * cx
            p1y = 2 * by - 0.5 * ay - 0.5 * cy
            out = []
            for i in range(n):
                t = i / (n - 1)
                u = 1 - t
                x = u * u * ax + 2 * u * t * p1x + t * t * cx
                y = u * u * ay + 2 * u * t * p1y + t * t * cy
                out.append((int(round(x)), int(round(y))))
            return out
        a2 = ax * ax + ay * ay
        b2 = bx * bx + by * by
        c2 = cx * cx + cy * cy
        ox = (a2 * (by - cy) + b2 * (cy - ay) + c2 * (ay - by)) / d
        oy = (a2 * (cx - bx) + b2 * (ax - cx) + c2 * (bx - ax)) / d
        r = math.hypot(ax - ox, ay - oy)

        def ang(p: Tuple[float, float]) -> float:
            return math.atan2(p[1] - oy, p[0] - ox)

        phi_r = ang(R)
        phi_t = ang(T)
        phi_l = ang(L)
        two_pi = 2 * math.pi
        ccw_span = (phi_r - phi_l) % two_pi
        t_ccw = (phi_t - phi_l) % two_pi
        if t_ccw <= ccw_span:
            sweep = ccw_span
        else:
            sweep = ccw_span - two_pi
        out = []
        for i in range(n):
            t = i / (n - 1)
            phi = phi_l + t * sweep
            x = ox + r * math.cos(phi)
            y = oy + r * math.sin(phi)
            out.append((int(round(x)), int(round(y))))
        return out

    @staticmethod
    def _earthquake_horizontal_y(
        frame_h: int, from_bottom_num: int, from_bottom_den: int
    ) -> int:
        """Row y for a line from_bottom_num/from_bottom_den of the way from bottom to top."""
        if frame_h <= 0:
            return 0
        h = frame_h
        f = from_bottom_num / float(from_bottom_den)
        return int(round((h - 1) * (1 - f)))

    @staticmethod
    def _earthquake_fill_polygon(
        arc_pts: List[Tuple[int, int]], y_line: int
    ) -> List[Tuple[int, int]]:
        """Closed polygon: arc polyline (left→right) then segment along y=y_line back to start."""
        if len(arc_pts) < 2:
            return list(arc_pts)
        x0, y0 = arc_pts[0]
        x1, y1 = arc_pts[-1]
        return list(arc_pts) + [(x1, y_line), (x0, y_line)]

    @staticmethod
    def _polygon_double_area(poly: List[Tuple[int, int]]) -> float:
        if len(poly) < 3:
            return 0
        a = 0
        n = len(poly)
        for i in range(n):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % n]
            a += x1 * y2 - x2 * y1
        return a

    @staticmethod
    def _point_in_polygon(px: int, py: int, poly: List[Tuple[int, int]]) -> bool:
        """Even-odd ray test; poly closed implicitly."""
        n = len(poly)
        if n < 3:
            return False
        inside = False
        j = n - 1
        for i in range(n):
            ix, iy = poly[i]
            jx, jy = poly[j]
            if (iy > py) != (jy > py):
                x_at = (jx - ix) * (py - iy) / (jy - iy) + ix
                if px < x_at:
                    inside = not inside
            j = i
        return inside

    @staticmethod
    def _random_points_in_polygon(
        poly: List[Tuple[int, int]], frame_w: int, frame_h: int, n_points: int
    ) -> List[Tuple[int, int]]:
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        min_x = max(0, min(xs))
        max_x = min(frame_w - 1, max(xs))
        min_y = max(0, min(ys))
        max_y = min(frame_h - 1, max(ys))
        out = []
        if max_x < min_x or max_y < min_y:
            return out
        for _ in range(n_points):
            for _try in range(1000):
                rx = random.randint(min_x, max_x)
                ry = random.randint(min_y, max_y)
                if not AttackStrategy._point_in_polygon(rx, ry, poly):
                    continue
                out.append((rx, ry))
                break
            else:
                ax, ay = poly[max(1, len(poly) // 4)]
                out.append((max(0, min(frame_w - 1, ax)), max(0, min(frame_h - 1, ay))))
        return out

    def _earthquake_curve_points_with_jitter(
        self,
        ltr: Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]],
    ) -> List[Tuple[int, int]]:
        points = self._sample_arc_through_three(ltr, 11)
        if random.choice((True, False)):
            points.reverse()
        jitter_px = 100
        return [
            (cx + random.randint(-jitter_px, jitter_px), cy + random.randint(-jitter_px, jitter_px))
            for cx, cy in points
        ]

    def _random_diamond_perimeter_point(self, frame: Any) -> Tuple[int, int]:
        c1, c2 = random.choice(_DIAMOND_EDGES)
        x1, y1 = self._point(c1)
        x2, y2 = self._point(c2)
        edge_len = math.hypot(x2 - x1, y2 - y1)
        if edge_len <= 2 * _EDRAG_CORNER_MARGIN:
            t = 0.5
        else:
            t_min = _EDRAG_CORNER_MARGIN / edge_len
            t_max = 1 - t_min
            t = random.uniform(t_min, t_max)
        xf = x1 + (x2 - x1) * t
        yf = y1 + (y2 - y1) * t
        fh, fw = frame.shape[:2]
        return self._quantize_deploy_to_frame(xf, yf, fw, fh)

    @staticmethod
    def _point_on_polyline_at_distance(
        vertices: List[Tuple[float, float]], distance: float
    ) -> Tuple[float, float]:
        """Point `distance` pixels along a polyline from the first vertex."""
        if not vertices:
            return (0, 0)
        if len(vertices) == 1:
            return (float(vertices[0][0]), float(vertices[0][1]))
        remaining = max(0, float(distance))
        x0, y0 = float(vertices[0][0]), float(vertices[0][1])
        for i in range(len(vertices) - 1):
            x1, y1 = float(vertices[i + 1][0]), float(vertices[i + 1][1])
            seg_len = math.hypot(x1 - x0, y1 - y0)
            if seg_len <= 0:
                x0, y0 = x1, y1
                continue
            if remaining <= seg_len:
                t = remaining / seg_len
                return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
            remaining -= seg_len
            x0, y0 = x1, y1
        return (x0, y0)

    def _even_diamond_top_perimeter_points(
        self,
        frame: Any,
        count: int,
        *,
        deviation_frac: float = 0.1,
        reserve_top_corner_slot: bool = False,
    ) -> List[Tuple[int, int]]:
        """Evenly spaced deploy clicks along left→top→right diamond edges (Edrag front),
        with ±deviation_frac jitter per slot and corner margin clamping.

        When reserve_top_corner_slot is set, spacing uses count+1 slots and the
        slot nearest the top vertex is left empty (virtual troop at the apex).
        """
        if count <= 0:
            return []
        vertices = [tuple(self._point(corner)) for corner in ("left", "top", "right")]
        seg_lens = [
            math.hypot(
                vertices[i + 1][0] - vertices[i][0],
                vertices[i + 1][1] - vertices[i][1],
            )
            for i in range(len(vertices) - 1)
        ]
        total_len = sum(seg_lens)
        margin = float(self.config.scale_scalar(_EDRAG_CORNER_MARGIN))
        start_d = margin
        end_d = total_len - margin
        span = end_d - start_d
        fh, fw = frame.shape[:2]
        if span <= 0:
            mid = self._point_on_polyline_at_distance(vertices, total_len / 2)
            return [self._quantize_deploy_to_frame(mid[0], mid[1], fw, fh)]
        slot_count = count + 1 if reserve_top_corner_slot else count
        spacing = span / slot_count
        slot_distances = []
        for i in range(slot_count):
            d = start_d + (i + 0.5) * spacing
            d += random.uniform(-deviation_frac, deviation_frac) * spacing
            d = max(start_d, min(end_d, d))
            slot_distances.append(d)
        skip_idx = None
        if reserve_top_corner_slot and slot_count > 1:
            top_d = seg_lens[0]
            skip_idx = min(range(slot_count), key=lambda i: abs(slot_distances[i] - top_d))
        out = []
        for i, d in enumerate(slot_distances):
            if i == skip_idx:
                continue
            xf, yf = self._point_on_polyline_at_distance(vertices, d)
            out.append(self._quantize_deploy_to_frame(xf, yf, fw, fh))
        return out

    def _deploy_diamond_perimeter_troop(
        self,
        frame: Any,
        template_name: str,
        stop_event: Optional[Any] = None,
        *,
        count: int = _EDRAG_COUNT,
        delay: float = _EDRAG_DELAY,
    ) -> bool:
        """Select troop in the bottom bar and click count points on the diamond perimeter."""
        ev = stop_event or self.stop_event
        roi = self.vision.bottom_half_region(frame)
        tx, ty = self.vision.find_template(frame, template_name, region=roi)
        if tx is None:
            return False
        self.input.click(tx, ty, pause=0.3, rand=False)
        if ev and ev.wait(0.2):
            return True
        for _ in range(count):
            if ev and ev.is_set():
                return True
            px, py = self._random_diamond_perimeter_point(frame)
            self.input.click(px, py, pause=delay, rand=False)
        return True

    def deploy_golden_drags_if_present(
        self, frame: Any, stop_event: Optional[Any] = None
    ) -> bool:
        """Optional Super Dragon deploy after main troops, before heroes."""
        ev = stop_event or self.stop_event
        if self._deploy_diamond_perimeter_troop(frame, "goldendrag.png", ev):
            logger.info("Deployed golden dragons")
        return bool(ev and ev.is_set())

    def deploy_spells(self, frame: Any) -> None:
        self._sync_frame_size(frame)
        roi = self.vision.bottom_half_region(frame)
        bx, by = self.vision.find_template(frame, "earthquake.png", region=roi)
        if bx:
            self.input.click(bx, by, pause=0.2)
            offset = int(self.config.get_scaled("earthquake", 400))
            ltr = self._earthquake_anchor_triplet(self._scaled_deployment_data(), offset)
            fh, fw = frame.shape[:2]
            num, den = _EARTHQUAKE_RANDOM_LINE_FROM_BOTTOM
            y_line = self._earthquake_horizontal_y(fh, num, den)
            if self.earthquake_method == EARTHQUAKE_METHOD_RANDOM:
                arc_dense = self._sample_arc_through_three(ltr, _EARTHQUAKE_REGION_ARC_SAMPLES)
                if random.choice((True, False)):
                    arc_dense = arc_dense[::-1]
                poly = self._earthquake_fill_polygon(arc_dense, y_line)
                if abs(self._polygon_double_area(poly)) < 2:
                    logger.warning(
                        "Earthquake random region degenerate; using curve placement with jitter."
                    )
                    points = self._earthquake_curve_points_with_jitter(ltr)
                else:
                    points = self._random_points_in_polygon(poly, fw, fh, 11)
            else:
                points = self._earthquake_curve_points_with_jitter(ltr)
            for cx, cy in points:
                jx = max(0, min(fw - 1, cx))
                jy = max(0, min(fh - 1, cy))
                self.input.click_at(jx, jy, rand=False)
                delay = random.uniform(0.1, 0.3)
                if self.stop_event:
                    self.stop_event.wait(delay)
                else:
                    time.sleep(delay)


class TroopSpamStrategy(AttackStrategy):
    """Drag troops along the full diamond perimeter for the configured duration."""

    def __init__(
        self,
        input_service: InputService,
        vision_service: VisionService,
        config: Config,
        stop_event: Any = None,
        troop_name: str = "sneaky",
        duration: float = 8.0,
        status_callback: Optional[Any] = None,
        earthquake_method: str = EARTHQUAKE_METHOD_CURVE,
    ) -> None:
        super().__init__(
            input_service,
            vision_service,
            config,
            stop_event,
            earthquake_method=earthquake_method,
        )
        self.troop_name = troop_name
        self.duration = duration
        self.status_callback = status_callback

    def execute(self, frame: Any, stop_event: Optional[Any] = None) -> bool:
        ev = stop_event or self.stop_event
        self._sync_frame_size(frame)
        logger.info(f"Executing {self.troop_name} strategy")
        roi = self.vision.bottom_half_region(frame) if self.vision else None
        tx, ty = (None, None)
        if self.vision and roi:
            tx, ty = self.vision.find_template(frame, f"{self.troop_name}.png", region=roi)
        (fh, fw) = frame.shape[:2] if hasattr(frame, "shape") else (1080, 1920)
        if tx is None:
            # Fallback to standard slot 1 if template not found
            tx, ty = int(fw * 0.18), int(fh * 0.92)
            logger.info(f"Troop {self.troop_name} not found via template; using fallback slot at ({tx}, {ty})")
        self.input.click(tx, ty, pause=0.3, rand=False)
        if ev and ev.wait(0.2):
            return True
        corners = ["top", "right", "bottom", "left"]
        if self.config.aspect_key == ASPECT_16_9:
            start_idx = random.choice([1, 3])
        else:
            start_idx = random.choice([0, 1, 3])
        direction = random.choice([1, -1])
        ordered_corners = []
        for i in range(5):
            idx = (start_idx + i * direction) % 4
            ordered_corners.append(corners[idx])
        start_corner = ordered_corners[0]
        sp = self._point(start_corner)
        curr_x, curr_y = self._quantize_deploy_to_frame(sp[0], sp[1], fw, fh)
        curr_x, curr_y = self._quantize_deploy_to_frame(*self._expand_loc(curr_x, curr_y), fw, fh)
        self.input.mouse_down(curr_x, curr_y)
        if ev and ev.wait(0.65):
            self.input.mouse_up(curr_x, curr_y)
            return True
        try:
            total_duration = self.duration
            segment_duration = total_duration / 4
            for i in range(len(ordered_corners) - 1):
                if ev and ev.is_set():
                    break
                next_c = ordered_corners[i + 1]
                np_pt = self._point(next_c)
                target_x, target_y = self._quantize_deploy_to_frame(np_pt[0], np_pt[1], fw, fh)
                target_x, target_y = self._quantize_deploy_to_frame(*self._expand_loc(target_x, target_y), fw, fh)
                seg_dur = random.uniform(segment_duration * 0.9, segment_duration * 1.1)
                self.input.human_move(curr_x, curr_y, target_x, target_y, duration=seg_dur)
                curr_y = target_y
                curr_x = target_x
            self.input.mouse_up(curr_x, curr_y)
            if ev and ev.is_set():
                return True
            ws = getattr(self.input, "window_service", None)
            if ws is not None and hasattr(ws, "screenshot"):
                frame = ws.screenshot()
                if frame is not None:
                    self._sync_frame_size(frame)
                    if self.deploy_golden_drags_if_present(frame, ev):
                        return True
                    self.deploy_heroes(frame)
                    if ev and ev.is_set():
                        return True
                    frame = ws.screenshot()
                    if frame is not None:
                        self._sync_frame_size(frame)
                        self.deploy_spells(frame)
            return True
        except Exception:
            self.input.mouse_up(curr_x, curr_y)
            raise


class EdragStrategy(AttackStrategy):
    """Electro Dragon farming — even diamond top perimeter placement."""

    def __init__(
        self,
        input_service: InputService,
        vision_service: VisionService,
        config: Config,
        stop_event: Any = None,
        status_callback: Optional[Any] = None,
        earthquake_method: str = EARTHQUAKE_METHOD_CURVE,
    ) -> None:
        super().__init__(
            input_service,
            vision_service,
            config,
            stop_event,
            earthquake_method=earthquake_method,
        )
        self.status_callback = status_callback

    def execute(self, frame: Any, stop_event: Optional[Any] = None) -> bool:
        ev = stop_event or self.stop_event
        self._sync_frame_size(frame)
        logger.info("Executing edrag strategy")
        if not self._deploy_diamond_perimeter_troop(frame, "edrag.png", ev):
            msg = "Troop edrag not found!"
            logger.warning(msg)
            if self.status_callback:
                self.status_callback(msg)
            return False
        if ev and ev.is_set():
            return True
        frame = self.input.window_service.screenshot()
        if frame is not None:
            self._sync_frame_size(frame)
            if self.deploy_golden_drags_if_present(frame, ev):
                return True
            self.deploy_heroes(frame)
            if ev and ev.is_set():
                return True
            frame = self.input.window_service.screenshot()
            if frame is not None:
                self._sync_frame_size(frame)
                self.deploy_spells(frame)
        return True
