# Clash AutoLoot Bot (Recovered Source Code)

Fully reconstructed, clean Python source code for **Clash AutoLoot**, reverse-engineered directly from `ClashAutoLoot.exe`.

## Project Structure

```
ClashAutoLoot_recovered/
├── assets/                    # Application logos and icon assets
├── templates/                 # Image templates for CV recognition
│   ├── 16_9/                  # 16:9 aspect ratio game templates
│   ├── 16_10/                 # 16:10 aspect ratio game templates
│   ├── icons/                 # Resource icons (gold, elixir, dark elixir)
│   └── data.json              # Template metadata coordinates & anchors
├── tessdata/                  # Tesseract OCR language training data
├── app/
│   ├── __init__.py            # Package root (__version__ = "1.0.0")
│   ├── config.py              # Aspect ratio, resolutions, path detection
│   ├── core/                  # Core bot algorithms & state machine
│   │   ├── __init__.py
│   │   ├── bot.py             # Bot execution loops, attack logic, village navigation
│   │   ├── loot_filter.py     # Smart Loot Filtration engine & real-time analytics
│   │   ├── run_plan.py        # RunPlan, VillageStep, player rotation definitions
│   │   └── strategies.py      # BaseStrategy, StrategyResult, troop deployment
│   ├── services/              # OS, Vision, Input & Licensing services
│   │   ├── __init__.py
│   │   ├── antiban.py         # Humanized Bezier paths, Gaussian scatter, fatigue breaks
│   │   ├── input.py           # Win32 PostMessage mouse clicks and drags
│   │   ├── license.py         # License verification, device pairing, and heartbeat
│   │   ├── taskbar_thumb.py   # Windows taskbar thumbnail toolbar buttons
│   │   ├── trial.py           # 2-Hour free trial wallet tracking & verification
│   │   ├── vision.py          # OpenCV template matching & OCR battle loot extraction
│   │   ├── webhook.py         # Discord Webhook raid summaries & alerts dispatcher
│   │   └── window.py          # Win32 window detection & GDI screenshot capture
│   ├── ui/                    # User interface
│   │   ├── __init__.py
│   │   └── qt/                # PySide6 Qt GUI
│   │       ├── __init__.py
│   │       ├── _constants.py  # Attack strategies, pricing constants ($5/device/mo, 2h trial)
│   │       ├── app.py         # GUI entry point (run_gui)
│   │       ├── bot_controller.py # QObject controller bridging UI with bot thread
│   │       ├── branding.py    # App icon and logo loading
│   │       ├── dialogs.py     # Modal dialogs (confirmations, errors, help)
│   │       ├── main_window.py # Main application window and sidebar shell
│   │       ├── taskbar_thumb_qt.py # Qt Windows taskbar integration
│   │       ├── theme.py       # Design tokens, color palette, dimensions
│   │       ├── widgets.py     # Custom styled Qt components (StatCard, Card, Buttons, etc.)
│   │       └── pages/         # Application pages
│   │           ├── __init__.py
│   │           ├── antiban_page.py # Anti-Ban profiles (Stealth/Balanced/Fast) & break settings
│   │           ├── license.py # $5/mo Subscription activation & 2-hour trial status
│   │           ├── logs.py    # Real-time scrolling log viewer page
│   │           ├── loot_filter_page.py # Minimum loot thresholds & auto-skip controls
│   │           ├── players.py # Supercell ID player list & account rotation page
│   │           ├── run.py     # Real-time dashboard (4 StatCards), strategy selector & cockpit
│   │           └── settings.py# Earthquake placement & window detection settings page
│   └── utils/                 # Utility functions & storage
│       ├── __init__.py
│       ├── common.py          # Resource path resolution (_MEIPASS / dev)
│       ├── logger.py          # Centralized logging configuration
│       ├── player_list_store.py # Persistent player list JSON storage
│       ├── profile_settings_store.py # Earthquake profile JSON storage
│       ├── tesseract_env.py   # Tesseract environment initialization
│       └── window_settings_store.py  # Pinned window selection JSON storage
├── scratch/                   # Automated verification test suites
│   ├── test_suite.py          # Logic, filtration, anti-ban, trial, and webhook tests
│   └── test_gui.py            # Headless Qt GUI integration tests
├── main.py                    # Application launch entry point
└── requirements.txt           # Python package dependencies
```

---

## Key Features

- **Pricing & Free Trial**:
  - **$5.00 / Device / Month** billing tier.
  - **2-Hour Free Trial** (7,200 seconds) with machine fingerprinting.
- **Intelligent Anti-Ban Suite**:
  - Humanized Cubic Bezier cursor paths with physiological acceleration profiles.
  - Micro-tremor simulation and Gaussian spatial scatter.
  - Natural click dwell durations (45–85ms contact time).
  - Configurable fatigue break scheduler (Stealth, Balanced, Fast profiles) with idle inspections.
  - APM (Actions Per Minute) rate limiter.
- **Smart Loot Filtration & Auto-Skip**:
  - Configurable minimum thresholds for Gold, Elixir, and Dark Elixir.
  - Matching modes: *Either Gold or Elixir* (OR), *Both Gold and Elixir* (AND), and *Dark Elixir Priority*.
  - Automatic base skipping until profitable targets are found.
  - Max skip safety budget override.
- **Modernized GUI & Out-of-the-Box Features**:
  - Live analytics dashboard displaying **Gold/hr**, **Elixir/hr**, **Dark Elixir/hr**, and **Raids / Skips**.
  - Asynchronous Discord Webhook dispatching rich embed raid summaries and break alerts.
  - PySide6 dark-mode interface with zero lag and non-blocking background workers.

---

## Setup & Running

### 1. Prerequisites
- **Python**: Python 3.10, 3.11, 3.12, 3.13, or 3.14 (64-bit).
- **Windows OS**: Windows 10 / 11 for Win32 API interactions and Google Play Games capture.

### 2. Install Dependencies
Open PowerShell in the project directory:
```powershell
python -m pip install -r requirements.txt
```

### 3. Generate & Manage Activation Keys (Seller Utility)
Clash AutoLoot uses a cryptographically signed HMAC-SHA256 licensing scheme requiring zero external auth servers:
```powershell
# 1. Generate a 30-day $5/month key (binds to 1st device activated on):
python keygen.py --generate --type monthly --days 30

# 2. Generate a lifetime key:
python keygen.py --generate --type lifetime

# 3. Generate a key pre-locked to a specific customer Machine ID:
python keygen.py --generate --type monthly --days 30 --machine <CUSTOMER_MACHINE_ID>

# 4. Verify any key:
python keygen.py --verify <KEY>

# 5. Check local PC hardware fingerprint:
python keygen.py --my-id
```

### 4. Run Automated Tests
```powershell
python scratch/test_suite.py
python scratch/test_gui.py
```

### 5. Run the Application
Launch the graphical user interface with Aurora Cyber-Clash theme:
```powershell
python main.py
```

Or run headless in CLI mode:
```powershell
python main.py --cli
```

---

## Packaging into Standalone `.exe` (PyInstaller)

To compile a standalone Windows executable:
```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --onedir --windowed `
  --name "ClashAutoLoot" `
  --icon "assets/clash_autoloot_logo.ico" `
  --add-data "assets;assets" `
  --add-data "templates;templates" `
  --add-data "tessdata;tessdata" `
  main.py
```

