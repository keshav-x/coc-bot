import sys
sys.path.insert(0, '.')
import numpy as np
from unittest.mock import MagicMock
from app.config import Config
from app.core.strategies import TroopSpamStrategy

config = Config()
input_mock = MagicMock()
vision_mock = MagicMock()

strat = TroopSpamStrategy(input_mock, vision_mock, config, troop_name="sneaky")

# Test across multiple resolutions: 1080p, 1440p, 720p, 16:10 (1920x1200)
resolutions = [(1920, 1080), (2560, 1440), (1280, 720), (1920, 1200)]

for fw, fh in resolutions:
    config.set_target_size(fw, fh)
    pts = strat._get_safe_perimeter_points(fw, fh)
    assert len(pts) == 11, f"Expected 11 perimeter points, got {len(pts)}"

    center_x, center_y = fw * 0.50, fh * 0.48

    for idx, (x, y) in enumerate(pts):
        # Must be strictly above bottom troop ribbon (y <= 0.79 * fh)
        assert y <= int(fh * 0.79), f"Point {idx} ({x}, {y}) touches bottom troop ribbon (max {int(fh * 0.79)})"
        # Must be strictly below top HUD (y >= 0.12 * fh)
        assert y >= int(fh * 0.12), f"Point {idx} ({x}, {y}) touches top HUD (min {int(fh * 0.12)})"
        # Must be inside screen borders
        assert x >= int(fw * 0.06), f"Point {idx} ({x}, {y}) off screen left"
        assert x <= int(fw * 0.94), f"Point {idx} ({x}, {y}) off screen right"

        # Check distance from center: must be outside center village area
        dist_from_center = ((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5
        assert dist_from_center > 0.20 * fh, f"Point {idx} ({x}, {y}) too close to base center ({dist_from_center:.1f})"

    print(f"[PASS] Geometry validated for {fw}x{fh}: 11 points safely on outer grass arc")

# Test execute method simulation
dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
vision_mock.bottom_half_region.return_value = (0, 540, 1920, 540)
vision_mock.find_template.return_value = (300, 950) # Sneaky goblin found in bar
strat._get_screenshot = MagicMock(return_value=None)

success = strat.execute(dummy_frame)
assert success is True, "Strategy execute failed"
# Wave 1 (33 clicks) + Wave 2 (33 clicks) + Wave 3 (22 clicks) + 3 troop re-clicks = ~91 clicks
assert input_mock.click.call_count >= 80, f"Expected at least 80 discrete clicks for 100% troop dump, got {input_mock.click.call_count}"
print(f"[PASS] Strategy execution simulation passed: {input_mock.click.call_count} discrete clicks registered for 100% camp dump")
print("\n*** ALL DEPLOYMENT GEOMETRY TESTS PASSED! ***")
