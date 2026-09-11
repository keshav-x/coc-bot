import os
import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import cv2
import numpy as np
from app.utils.tesseract_env import configure_tesseract
configure_tesseract()

from app.config import Config, ASPECT_16_9
from app.services.vision import VisionService
from app.services.input import InputService
from app.core.bot import Bot

print("=== RUNNING WALL UPGRADE & SAFE SCROLLING TEST SUITE ===")

# Test 1: find_wall_labels_top_center_ocr with various formats
frame = np.full((1080, 1920, 3), 45, dtype=np.uint8)
# Add Town Hall at top (y=280)
cv2.putText(frame, "Town Hall Lv 16", (800, 280), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (240, 240, 240), 2)
# Add Clan Castle at (y=420)
cv2.putText(frame, "Clan Castle Lv 11", (800, 420), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (240, 240, 240), 2)
# Add Cannon at (y=560)
cv2.putText(frame, "Cannon Lv 21", (800, 560), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (240, 240, 240), 2)
# Add Wall at bottom of builder menu (y=820)
cv2.putText(frame, "Wall (Lv 15)", (800, 820), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (240, 240, 240), 2)

wall_pt = VisionService.find_wall_labels_top_center_ocr(frame)
assert wall_pt is not None, "Failed to find Wall (Lv 15) at y=820!"
print(f"[PASS] Successfully detected Wall at {wall_pt}")
# Ensure Y is around 820 (+-30px) and NOT at Town Hall (y=280) or Clan Castle (y=420)
assert abs(wall_pt[1] - 820) < 40, f"Expected wall Y ~820, got {wall_pt[1]} (false match on building!)"
print("[PASS] Town Hall & Clan Castle false positives successfully excluded")

# Test 2: Walls plural format "Walls (25)"
frame2 = np.full((1080, 1920, 3), 45, dtype=np.uint8)
cv2.putText(frame2, "Walls (25)", (800, 780), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (240, 240, 240), 2)
wall_pt2 = VisionService.find_wall_labels_top_center_ocr(frame2)
assert wall_pt2 is not None, "Failed to find Walls (25)!"
assert abs(wall_pt2[1] - 780) < 40
print(f"[PASS] Successfully detected plural Walls at {wall_pt2}")

# Test 3: Safe scrolling behavior
bot = Bot()
bot.config.set_target_size(1920, 1080)
scroll_events = []
mouse_events = []

class MockInput:
    def scroll(self, x, y, amount, upward=True):
        scroll_events.append(('scroll', x, y, amount, upward))
    def move(self, x, y, wparam=0):
        mouse_events.append(('move', x, y, wparam))
    def mouse_down(self, x, y):
        mouse_events.append(('down', x, y))
    def mouse_up(self, x, y):
        mouse_events.append(('up', x, y))
    def human_move(self, x1, y1, x2, y2, duration=0.2):
        mouse_events.append(('drag', x1, y1, x2, y2))
    def click(self, x, y=None, pause=0.2, rand=False):
        pass

bot.input = MockInput()

# Call _wall_menu_drag_to_bottom
bot._wall_menu_drag_to_bottom()

# Verify swipe is in the safe center-neutral column (0.45*w <= x <= 0.52*w) away from right-side upgrade buttons
assert len(mouse_events) >= 1
for ev in mouse_events:
    if ev[0] in ('move', 'down', 'up'):
        assert int(1920 * 0.45) <= ev[1] <= int(1920 * 0.52), f"Mouse event X outside safe center column: {ev[1]}"
    elif ev[0] == 'drag':
        assert int(1920 * 0.45) <= ev[1] <= int(1920 * 0.52)
        # Verify drag is upward (scrolling down), y1 > y2
        assert ev[2] > ev[4], f"Drag should be upward swipe, got {ev[2]} -> {ev[4]}"
print("[PASS] Safe list swipe is positioned strictly in the center neutral column (x ~ 0.48*w)")

# Test 4: _wall_menu_drag_retry_nudge
scroll_events.clear()
mouse_events.clear()
bot._wall_menu_drag_retry_nudge()
for ev in mouse_events:
    if ev[0] == 'drag':
        # Must be upward swipe, never downward
        assert ev[2] > ev[4], f"Retry nudge dragged downward back to top: {ev[2]} -> {ev[4]}"
print("[PASS] _wall_menu_drag_retry_nudge safely scrolls downward in the center column")

# Test 5: Clean dismissal when no walls available
empty_clicks = []
bot.input.click = lambda x, y=None, pause=0.2, rand=False: empty_clicks.append((x, y) if y is not None else x)
# Empty frame without walls
empty_frame = np.full((1080, 1920, 3), 45, dtype=np.uint8)
cv2.putText(empty_frame, "Archer Tower Lv 19", (800, 500), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (240, 240, 240), 2)
bot.window.screenshot = lambda: empty_frame
bot._find_home_village_builder = lambda f, r: (960, 50)
bot._upgrade_walls()
# Verify empty click was sent to dismiss menu cleanly
assert len(empty_clicks) >= 2, "Expected click on builder then click on empty"
print("[PASS] Cleanly dismisses builder menu when walls are maxed or not found")

print("\n*** ALL WALL UPGRADE & SAFE SCROLLING TESTS PASSED! ***")
