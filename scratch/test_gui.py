import os
import sys
from pathlib import Path

# Force Qt offscreen platform
os.environ["QT_QPA_PLATFORM"] = "offscreen"
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

print("=== STARTING CLASH AUTOLOOT GUI HEADLESS TEST SUITE ===")
from PySide6.QtWidgets import QApplication

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

# Test 1: Widgets & Card.card_layout property
print("[1/3] Testing Card & StatCard widgets...")
from app.ui.qt.widgets import Card, StatCard
card = Card()
assert card.card_layout is not None, "Card.card_layout returned None!"

stat_card = StatCard("Gold / hr", "0", "💰")
stat_card.set_value("1,250,000")
assert stat_card._val_lbl.text() == "1,250,000"
print("   -> Card & StatCard widgets functioning flawlessly!")

# Test 2: MainWindow instantiation (wires BotController, RunPage, LootFilterPage, AntiBanPage, LicensePage, LogsPage)
print("[2/2] Testing MainWindow full integration & page stack...")
from app.ui.qt.main_window import MainWindow
main_win = MainWindow()
assert main_win._stack.count() >= 5
print(f"   -> MainWindow loaded successfully with {main_win._stack.count()} navigation pages!")
assert main_win._run_page is not None
assert main_win._run_page._stat_gold is not None
assert main_win._run_page._stat_elixir is not None
assert main_win._run_page._stat_dark is not None
assert main_win._run_page._stat_raids is not None
assert main_win._run_page._raid_table is not None
from app.core.loot_filter import RaidRecord
test_rec = RaidRecord(raid_num=1, timestamp_str="12:00:00", gold=950000, elixir=920000, dark_elixir=7500, skips=3, status="Victory")
main_win._run_page._raid_table.add_raid_row(test_rec)
assert main_win._run_page._raid_table.rowCount() == 1
print("   -> RunPage verified with 4 live StatCards and live RaidHistoryTable!")

assert main_win._trial_banner is not None
from app.services.license import LicenseState
main_win._trial_banner.update_status(LicenseState.EMPTY, 5400)
assert "1h 30m" in main_win._trial_banner._status_lbl.text()
assert main_win._trial_banner._progress.value() > 0
main_win._trial_banner.update_status(LicenseState.VALID, None)
assert "Pro Active" in main_win._trial_banner._status_lbl.text()
print("   -> Sidebar TrialBanner verified with dynamic progress bar and pro status!")

assert main_win._settings_page is not None
assert main_win._settings_page._webhook_url is not None
print("   -> SettingsPage verified with Discord Webhook configuration!")

assert main_win._loot_filter_page is not None
print("   -> LootFilterPage verified.")
assert main_win._antiban_page is not None
print("   -> AntiBanPage verified.")
assert main_win._license_page is not None
print("   -> LicensePage verified.")
assert main_win._logs_page is not None
print("   -> LogsPage verified.")

# Verify pre-default setting: Builder Base fully disabled, Home Village enabled
plan = main_win._run_page.build_plan()
assert plan.includes("home"), "Expected Home Village to be included by default"
assert not plan.includes("builder"), "Expected Builder Base to be FULLY DISABLED by default"
print("   -> Run plan verified: Builder Base is FULLY DISABLED by default, Home Village enabled!")

print("\n*** ALL GUI HEADLESS TESTS PASSED WITH ZERO CRASHES! ***")
