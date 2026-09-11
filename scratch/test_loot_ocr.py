import sys
sys.path.insert(0, '.')
import cv2
import numpy as np
from app.services.vision import VisionService
from app.utils.tesseract_env import configure_tesseract
configure_tesseract()

# Test 1: Full 1080p frame with player name, Available Loot, and commas
f1 = np.full((1080, 1920, 3), 35, dtype=np.uint8)
cv2.putText(f1, 'SuperLeader99', (60, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
cv2.putText(f1, 'Available Loot', (60, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
cv2.putText(f1, '950,200', (100, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f1, '820,100', (100, 190), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f1, '7,400', (100, 235), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f1, '+32  -16', (60, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

res1 = VisionService.extract_battle_loot(f1)
assert res1 == (950200, 820100, 7400), f"Test 1 failed: {res1}"
print("[PASS] Test 1: Full 1080p frame with commas and player name digits ->", res1)

# Test 2: Space separated numbers and missing Available Loot header
f2 = np.full((1080, 1920, 3), 35, dtype=np.uint8)
cv2.putText(f2, 'ClashMaster7', (60, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
cv2.putText(f2, '1 400 000', (100, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f2, '1 150 000', (100, 175), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f2, '9 200', (100, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f2, '+24  -20', (60, 270), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

res2 = VisionService.extract_battle_loot(f2)
assert res2 == (1400000, 1150000, 9200), f"Test 2 failed: {res2}"
print("[PASS] Test 2: Space separated numbers without header ->", res2)

# Test 3: TH6 Base (no Dark Elixir)
f3 = np.full((1080, 1920, 3), 35, dtype=np.uint8)
cv2.putText(f3, 'TH6Player', (60, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
cv2.putText(f3, 'Available Loot', (60, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
cv2.putText(f3, '380,000', (100, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f3, '290,000', (100, 195), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

res3 = VisionService.extract_battle_loot(f3)
assert res3 == (380000, 290000, 0), f"Test 3 failed: {res3}"
print("[PASS] Test 3: TH6 base without dark elixir ->", res3)

# Test 4: Small isolated level badge ("14") above Available Loot
f4 = np.full((1080, 1920, 3), 35, dtype=np.uint8)
cv2.putText(f4, '14 PlayerClan', (60, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
cv2.putText(f4, 'Available Loot', (60, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)
cv2.putText(f4, '1,050,000', (100, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f4, '980,000', (100, 195), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(f4, '8,500', (100, 245), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

res4 = VisionService.extract_battle_loot(f4)
assert res4 == (1050000, 980000, 8500), f"Test 4 failed: {res4}"
print("[PASS] Test 4: Level badge '14' filtered out ->", res4)

print("\n*** ALL BATTLE LOOT OCR TESTS PASSED PERFECTLY! ***")
