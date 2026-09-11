import sys
sys.path.insert(0, '.')
import cv2
import numpy as np
import pytesseract
from app.utils.tesseract_env import configure_tesseract
configure_tesseract()

def extract_battle_loot_test(screen_img: np.ndarray) -> tuple[int | None, int | None, int | None]:
    if pytesseract is None or screen_img is None or getattr(screen_img, "size", 0) == 0:
        return (None, None, None)

    h_s, w_s = screen_img.shape[:2]
    rx = int(w_s * 0.02)
    ry = int(h_s * 0.06)
    rw = int(w_s * 0.28)
    rh = int(h_s * 0.28)
    roi = screen_img[ry : ry + rh, rx : rx + rw]
    if roi.size == 0:
        return (None, None, None)

    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 140, 255, cv2.THRESH_BINARY)
    passes = [gray, thresh]

    for img_pass in passes:
        try:
            data = pytesseract.image_to_data(img_pass, config="--psm 6", output_type=pytesseract.Output.DICT)
        except Exception:
            continue

        words = []
        header_y = None
        for i in range(len(data.get("text", []))):
            raw = str(data["text"][i] or "").strip()
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                conf = 0.0
            if not raw or conf < 15:
                continue
            top = int(data["top"][i])
            left = int(data["left"][i])
            words.append((top, left, raw, conf))
            low = raw.lower()
            if any(w in low for w in ("available", "loot", "botin", "butin", "beute")):
                if header_y is None or top < header_y:
                    header_y = top

        filtered = [w for w in words if header_y is None or w[0] > (header_y - 5)]

        candidates = []
        for top, left, raw, conf in filtered:
            if any(c.isalpha() for c in raw):
                continue
            if "+" in raw or "-" in raw:
                continue
            digits = "".join(c for c in raw if c.isdigit())
            if not digits:
                continue
            candidates.append((top, left, digits, raw))

        if not candidates:
            continue

        candidates.sort(key=lambda c: (c[0] // 16, c[1]))

        clustered = []
        for c in candidates:
            if not clustered:
                clustered.append(c)
            else:
                prev = clustered[-1]
                if abs(c[0] - prev[0]) < 16:
                    merged_digits = prev[2] + c[2]
                    clustered[-1] = (prev[0], min(prev[1], c[1]), merged_digits, prev[3] + " " + c[3])
                else:
                    clustered.append(c)

        if len(clustered) >= 2:
            try:
                gold = int(clustered[0][2])
                elixir = int(clustered[1][2])
                dark = int(clustered[2][2]) if len(clustered) >= 3 else 0
                if gold >= 0 and elixir >= 0:
                    return (gold, elixir, dark)
            except (ValueError, TypeError):
                pass

    return (None, None, None)

# Test 1: Full 1080p frame with player name, Available Loot, and commas
f1 = np.full((1080, 1920, 3), 35, dtype=np.uint8)
cv2.putText(f1, 'SuperLeader99', (60, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
cv2.putText(f1, 'Available Loot', (60, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
cv2.putText(f1, '950,200', (100, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f1, '820,100', (100, 205), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f1, '7,400', (100, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f1, '+32  -16', (60, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

res1 = extract_battle_loot_test(f1)
assert res1 == (950200, 820100, 7400), f"Test 1 failed: {res1}"
print("[PASS] Test 1: Full 1080p frame with commas and player name digits ->", res1)

# Test 2: Space separated numbers and missing Available Loot header
f2 = np.full((1080, 1920, 3), 35, dtype=np.uint8)
cv2.putText(f2, 'ClashMaster7', (60, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
cv2.putText(f2, '1 400 000', (100, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f2, '1 150 000', (100, 195), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f2, '9 200', (100, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f2, '+24  -20', (60, 290), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

res2 = extract_battle_loot_test(f2)
assert res2 == (1400000, 1150000, 9200), f"Test 2 failed: {res2}"
print("[PASS] Test 2: Space separated numbers without header ->", res2)

# Test 3: TH6 Base (no Dark Elixir)
f3 = np.full((1080, 1920, 3), 35, dtype=np.uint8)
cv2.putText(f3, 'TH6Player', (60, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
cv2.putText(f3, 'Available Loot', (60, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
cv2.putText(f3, '380,000', (100, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f3, '290,000', (100, 215), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

res3 = extract_battle_loot_test(f3)
assert res3 == (380000, 290000, 0), f"Test 3 failed: {res3}"
print("[PASS] Test 3: TH6 base without dark elixir ->", res3)

print("\n*** ALL BATTLE LOOT OCR TESTS PASSED PERFECTLY! ***")
