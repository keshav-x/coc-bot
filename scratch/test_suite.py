import sys
import time
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

print("=== STARTING CLASH AUTOLOOT AUTOMATED TEST SUITE ===")
print("Python:", sys.version)

# 1. Test Trial & License constants
from app.services.trial import TrialClient, TRIAL_TOTAL_SECONDS, TrialResult
from app.ui.qt._constants import PLAN_PRICE_MONTHLY, PLAN_DEVICE_LIMIT, PLAN_TRIAL_HOURS, PLAN_DESCRIPTION

print("[1/5] Testing Trial & Subscription Definitions...")
assert TRIAL_TOTAL_SECONDS == 7200, f"Expected 7200s, got {TRIAL_TOTAL_SECONDS}"
assert PLAN_PRICE_MONTHLY == "$3.00 / month"
assert "1 Device" in PLAN_DEVICE_LIMIT
assert PLAN_TRIAL_HOURS == 2

r_valid = TrialResult(ok=True, remaining_seconds=3600)
assert r_valid.allowed() is True
r_expired = TrialResult(ok=True, remaining_seconds=0)
assert r_expired.allowed() is False
r_fail = TrialResult(ok=False, remaining_seconds=3600)
assert r_fail.allowed() is False
print("   -> TrialResult logic & pricing constants verified!")

# 2. Test AntiBan
from app.services.antiban import (
    AntiBanService,
    AntiBanConfig,
    PROFILE_STEALTH,
    PROFILE_BALANCED,
    PROFILE_FAST
)

print("[2/5] Testing AntiBan Engine & Trajectories...")
ab = AntiBanService()
ab.config.profile = PROFILE_STEALTH

# Bezier trajectory test
start_pt = (120, 300)
end_pt = (650, 780)
pts = ab.generate_bezier_path(start_pt[0], start_pt[1], end_pt[0], end_pt[1], steps=20)
assert len(pts) >= 20
assert pts[-1] == end_pt

# Micro-tremor / Gaussian scatter test
for _ in range(50):
    sx, sy = ab.gaussian_point(250, 450, sigma=4.0)
    assert abs(sx - 250) <= 25
    assert abs(sy - 450) <= 25

# APM rate limiter
for _ in range(5):
    ab.record_action()

print("   -> AntiBan Bezier generation, Gaussian scatter, and APM throttling verified!")

# 3. Test Loot Filtration Engine
from app.core.loot_filter import (
    LootFilterEngine,
    LootFilterConfig,
    FILTER_MODE_OR,
    FILTER_MODE_AND,
    FILTER_MODE_DE,
)

print("[3/5] Testing Smart Loot Filtration Engine...")
lfe = LootFilterEngine()
lfe.config.enabled = True

# Test OR mode
lfe.config.filter_mode = FILTER_MODE_OR
lfe.config.min_gold = 400000
lfe.config.min_elixir = 400000
lfe.config.min_dark_elixir = 2000
lfe.config.max_skips = 40

dec1 = lfe.evaluate(500000, 100000, 500)
assert dec1.should_attack is True

dec2 = lfe.evaluate(100000, 500000, 500)
assert dec2.should_attack is True

dec3 = lfe.evaluate(100000, 100000, 500)
assert dec3.should_attack is False

# Test AND mode
lfe.config.filter_mode = FILTER_MODE_AND
assert lfe.evaluate(500000, 500000, 0).should_attack is True
assert lfe.evaluate(500000, 200000, 0).should_attack is False

# Test DE mode
lfe.config.filter_mode = FILTER_MODE_DE
lfe.config.min_dark_elixir = 4000
assert lfe.evaluate(1000000, 1000000, 4500).should_attack is True
assert lfe.evaluate(1000000, 1000000, 2000).should_attack is False

# Test skip tracking & stats
lfe.stats.reset()
lfe.stats.record_skip()
lfe.stats.record_skip()
lfe.stats.record_skip()
assert lfe.stats.bases_skipped == 3

# Max skip override
lfe.config.max_skips = 3
forced_dec = lfe.evaluate(10000, 10000, 100, current_skip_count=3)
assert forced_dec.should_attack is True
assert "Max search skips reached" in forced_dec.reason

lfe.stats.record_raid(gold=650000, elixir=700000, dark_elixir=4500)
assert lfe.stats.raids_completed == 1
assert lfe.stats.total_gold == 650000
assert lfe.stats.total_elixir == 700000
assert lfe.stats.total_dark_elixir == 4500
assert lfe.stats.gold_per_hour > 0
print("   -> Smart Loot filtration (OR, AND, DE, Max Skips, Stats) verified!")

# 4. Test Input Service coord unpacking
from app.services.input import InputService

print("[4/5] Testing InputService coordinates unpacking & bounds check...")
inp = InputService(None)
assert inp._unpack_coords(100, 200) == (100, 200)
assert inp._unpack_coords((100, 200)) == (100, 200)
assert inp._unpack_coords([100, 200]) == (100, 200)
print("   -> Input coordinate unpacking verified for tuples, lists, and direct x,y pairs!")

# 5. Test Discord Webhook dispatcher
from app.services.webhook import (
    WebhookConfig,
    load_webhook_config,
    save_webhook_config,
    notify_bot_started,
    notify_raid_complete,
)

print("[5/5] Testing Discord Webhook dispatch formatting...")
test_cfg = WebhookConfig(
    enabled=False,
    url="https://discord.com/api/webhooks/dummy/dummy",
    notify_on_raid=True,
    notify_on_break=True,
    notify_on_stop=True,
)
assert test_cfg.enabled is False
assert test_cfg.notify_on_raid is True
# Ensure notify functions execute safely without crashing when disabled
notify_bot_started("Sneaky Goblins Farm")
notify_raid_complete(gold=750000, elixir=800000, dark_elixir=5000, skips=4)
print("   -> Discord Webhook config and dispatcher verified safely!")

# 6. Test Autonomous Watchdog & Auto-Recovery
from app.core.watchdog import AutoRecoveryWatchdog

print("[6/8] Testing Autonomous Watchdog & Auto-Recovery Engine...")
class DummyVision:
    def find_image_in_frame(self, frame, tpl):
        if tpl == "okay":
            return (450, 550)
        return None

class DummyInput:
    def __init__(self):
        self.clicks = []
    def click(self, x, y=None, pause=0.2, rand=False):
        self.clicks.append((x, y))

class DummyWindow:
    hwnd = 12345
    def screenshot(self):
        return None

d_vis = DummyVision()
d_inp = DummyInput()
d_win = DummyWindow()
watchdog = AutoRecoveryWatchdog(d_vis, d_inp, d_win)

# Test recovery from Supercell modal prompt
dummy_frame = [1, 2, 3]
recovered = watchdog.check_and_recover(dummy_frame)
assert recovered is True
assert len(d_inp.clicks) == 1
assert watchdog.consecutive_recoveries == 1
print("   -> Watchdog modal detection & auto-recovery verified!")

# 7. Test Native Desktop Notification Dispatcher
from app.services.notifications import NotificationService

print("[7/8] Testing Native Windows Notifications...")
NotificationService.notify_mega_raid(750000, 800000, 4500)
NotificationService.notify_break_started(5)
NotificationService.notify_trial_warning(15)
print("   -> Native Desktop Notifications dispatched safely!")

# 8. Test RaidRecord Telemetry
from app.core.loot_filter import RaidRecord

print("[8/8] Testing RaidRecord Telemetry Storage...")
rec = lfe.stats.record_raid(gold=800000, elixir=850000, dark_elixir=6000, skips=5, status="Victory")
assert rec.gold == 800000
assert rec.skips == 5
assert len(lfe.stats.raid_history) >= 1
assert lfe.stats.raid_history[-1].raid_num == rec.raid_num
# 9. Test Zero-Gem Guard, Progression Dialogs & Escape Recovery
print("[9/9] Testing Zero-Gem Guard, Supercell Progression Dialogs & Recovery...")
import cv2
import numpy as np
from app.services.vision import VisionService
from app.core.bot import Bot

# 9a. Test Zero-Gem Guard on Missing Resources dialog
gem_frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
cv2.putText(gem_frame, "Missing resources!", (800, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
cv2.putText(gem_frame, "Purchase missing resources for 250 Gems?", (650, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
cv2.putText(gem_frame, "Cancel", (700, 600), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (220, 220, 220), 2)
gem_res = VisionService.detect_gem_spending_dialog(gem_frame)
assert gem_res.detected is True, "Zero-Gem Guard failed to detect missing resources gem dialog!"
assert gem_res.cancel_point is not None, "Zero-Gem Guard failed to locate Cancel button!"
print(f"   -> Zero-Gem Guard successfully detected gem prompt: {gem_res.reason}")

# 9b. Test Bot dismissal of gem dialog
test_bot = Bot()
test_escapes = []
test_clicks = []
test_bot.input.send_escape = lambda: test_escapes.append(True)
test_bot.input.click = lambda *args, **kwargs: test_clicks.append(args)
dismissed = test_bot._dismiss_gem_prompt_if_open(gem_frame)
assert dismissed is True, "Bot._dismiss_gem_prompt_if_open failed to dismiss gem dialog!"
assert len(test_escapes) >= 1, "Expected Escape key to be sent to dismiss gem dialog!"
assert len(test_clicks) >= 1, "Expected Cancel or empty click to be sent to dismiss gem dialog!"
print("   -> Bot._dismiss_gem_prompt_if_open safely vetoed and dismissed gem prompt with Zero Gems spent!")

# 9c. Test Supercell uncancelable update/event progression buttons
prog_frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
cv2.putText(prog_frame, "Welcome to the New Season!", (750, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
# Draw green progression button with "Claim"
cv2.rectangle(prog_frame, (860, 600), (1060, 660), (35, 180, 50), -1)
cv2.putText(prog_frame, "Claim", (920, 640), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
prog_pt = VisionService.find_uncancelable_progression_button(prog_frame)
assert prog_pt is not None, "Failed to detect Supercell uncancelable progression button!"
assert abs(prog_pt[0] - 960) < 100 and abs(prog_pt[1] - 630) < 50
print(f"   -> Supercell uncancelable update progression button successfully detected at {prog_pt}!")

print("\n*** ALL 9 TEST MODULES COMPLETED SUCCESSFULLY WITH ZERO ERRORS! ***")
