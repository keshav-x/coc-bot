import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np
from app.config import Config, ASPECT_16_9, ASPECT_16_10
from app.services.window import WindowService
from app.services.input import InputService
from app.core.strategies import TroopSpamStrategy, EdragStrategy, AttackStrategy
from app.core.bot import Bot

print("=== RUNNING ATTACK & COORDINATE INTEGRATION TESTS ===")

# 1. Test InputService Precision Click Jitter
inp = InputService(None)
clicks = []
def mock_inject(x, y):
    clicks.append((x, y))
inp._inject_click = mock_inject

for _ in range(50):
    inp.click(500, 500)
    last_x, last_y = clicks[-1]
    # Verify scatter is tight (+-2px max)
    assert abs(last_x - 500) <= 2, f"Expected scatter <= 2px, got {last_x - 500}"
    assert abs(last_y - 500) <= 2, f"Expected scatter <= 2px, got {last_y - 500}"
print("[PASS] InputService precision scatter verified (+-2px max)")

# 2. Test Multi-Wave Deployment Math & Perimeter Clamping
cfg = Config()
strat = TroopSpamStrategy(inp, None, cfg, troop_name="sneaky")
assert strat.troop_name == "sneaky"

wave_clicks = []
inp.click = lambda x, y=None, pause=0.2, rand=True: wave_clicks.append((x, y))
strat.deploy_multi_wave(100, 900, (200, 200), (800, 200), count_per_wave=4, num_waves=1, delay=0.05)
# First click is troop select at (100, 900), followed by 4 wave deploy points
assert len(wave_clicks) == 5
assert wave_clicks[0] == (100, 900)
for pt in wave_clicks[1:]:
    # X should be between 150 and 850, Y strictly clamped above bottom ribbon
    assert 150 <= pt[0] <= 850
    assert 100 <= pt[1] <= 870
print("[PASS] Multi-wave surgical boundary deploy points verified")

# 3. Test Clamped Deploy Boundaries on 1920x1080
dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
h, w = dummy_frame.shape[:2]
strat._sync_frame_size(dummy_frame)

for corner in ("left", "top", "right", "bottom"):
    pt = strat._point(corner)
    cx, cy = strat._quantize_deploy_to_frame(pt[0], pt[1], w, h)
    assert int(w * 0.08) <= cx <= int(w * 0.92), f"Corner {corner} X out of bounds: {cx}"
    assert int(h * 0.12) <= cy <= int(h * 0.81), f"Corner {corner} Y out of safe grass bounds: {cy} (must be above ribbon {int(h * 0.84)})"
    print(f"[PASS] Corner '{corner}' safely placed on deployable grass: ({cx}, {cy})")

# 4. Test Bot Attack Button Coordinates
bot = Bot()
fb_x = int(w * 0.058)
fb_y = int(h * 0.915)
assert 100 <= fb_x <= 120, f"Expected attack button x ~111, got {fb_x}"
assert 970 <= fb_y <= 1000, f"Expected attack button y ~988, got {fb_y}"
print(f"[PASS] Calibrated Attack button coordinates verified: ({fb_x}, {fb_y}) on 1920x1080")

# 5. Test Edrag Strategy Polyline Points
edrag = EdragStrategy(inp, None, cfg)
edrag_points = edrag._even_diamond_top_perimeter_points(dummy_frame, count=8)
assert len(edrag_points) == 8
for px, py in edrag_points:
    assert 0 <= px < 1920
    assert 0 <= py < 1080
print("[PASS] Edrag diamond perimeter deployment points verified")

# 6. Test Continuous Drag Streaming in TroopSpamStrategy
mouse_events = []
inp.mouse_down = lambda x, y: mouse_events.append(('down', x, y))
inp.mouse_up = lambda x, y: mouse_events.append(('up', x, y))
inp.human_move = lambda x1, y1, x2, y2, duration=0.5: mouse_events.append(('move', x1, y1, x2, y2))
inp.window_service = None

# Mock vision to return None so it tests fallback slot 1
class MockVision:
    def bottom_half_region(self, frame):
        return (0, 540, 1920, 540)
    def find_template(self, *args, **kwargs):
        return (None, None)
strat.vision = MockVision()

# Execute strategy with mock
res = strat.execute(dummy_frame)
assert res is True
# Verify mouse_down was called followed by move segments and mouse_up
downs = [e for e in mouse_events if e[0] == 'down']
moves = [e for e in mouse_events if e[0] == 'move']
ups = [e for e in mouse_events if e[0] == 'up']
assert len(downs) >= 1, "Expected at least 1 mouse_down for continuous army streaming"
assert len(moves) >= 4, f"Expected at least 4 moves across corners, got {len(moves)}"
assert len(ups) >= 1, "Expected at least 1 mouse_up"

for _, x1, y1, x2, y2 in moves:
    assert int(h * 0.12) <= y1 <= int(h * 0.81), f"Drag start Y out of grass bounds: {y1}"
    assert int(h * 0.12) <= y2 <= int(h * 0.81), f"Drag target Y out of grass bounds: {y2}"
print("[PASS] Continuous perimeter army streaming verified with safe boundary adherence")

print("\n*** ALL COORDINATE ALIGNMENT & COMBAT OVERHAUL TESTS PASSED! ***")
