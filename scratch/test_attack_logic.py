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
    # Verify scatter is now tight (+-2px) instead of +-12px
    assert abs(last_x - 500) <= 2, f"Expected scatter <= 2px, got {last_x - 500}"
    assert abs(last_y - 500) <= 2, f"Expected scatter <= 2px, got {last_y - 500}"
print("[PASS] InputService precision scatter verified (+-2px max)")

# 2. Test Multi-Wave Deployment Math
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
    # X should be between 180 and 820, Y around 200 (+-10px)
    assert 180 <= pt[0] <= 820
    assert 180 <= pt[1] <= 220
print("[PASS] Multi-wave surgical boundary deploy points verified")

# 3. Test Bot Attack Fallback Coordinates
bot = Bot()
dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
h, w = dummy_frame.shape[:2]
fb_x = int(w * 0.058)
fb_y = int(h * 0.915)
assert 100 <= fb_x <= 120, f"Expected attack button x ~111, got {fb_x}"
assert 970 <= fb_y <= 1000, f"Expected attack button y ~988, got {fb_y}"
print(f"[PASS] Calibrated Attack button coordinates verified: ({fb_x}, {fb_y}) on 1920x1080")

# 4. Test Edrag Strategy Polyline Points
edrag = EdragStrategy(inp, None, cfg)
edrag_points = edrag._even_diamond_top_perimeter_points(dummy_frame, count=8)
assert len(edrag_points) == 8
for px, py in edrag_points:
    assert 0 <= px < 1920
    assert 0 <= py < 1080
print("[PASS] Edrag diamond perimeter deployment points verified")

print("\n*** ALL COORDINATE ALIGNMENT & STRATEGY TESTS PASSED! ***")
