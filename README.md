<div align="center">

<img src="assets/apex_clash_logo.png" alt="ApexClash Pro Logo" width="160" style="border-radius: 24px; box-shadow: 0 8px 32px rgba(0, 229, 255, 0.25);" />

# ⚔️ ApexClash Pro
### *The Next-Generation Autonomous Combat, Farming & Anti-Ban Suite for Clash of Clans*

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D4?style=for-the-badge&logo=windows&logoColor=white)](https://microsoft.com/windows)
[![GUI](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://qt.io)
[![Computer Vision](https://img.shields.io/badge/Vision-OpenCV%20%2B%20Tesseract-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org)
[![Anti-Ban](https://img.shields.io/badge/Security-Humanized%20B%C3%A9zier%203.0-00E5FF?style=for-the-badge)](https://github.com/keshav-x/coc-bot)
[![License](https://img.shields.io/badge/License-Proprietary%20%2F%20Commercial-FFB300?style=for-the-badge)](https://github.com/keshav-x/coc-bot)

<p align="center">
  <b>High-Precision Game Automation</b> • <b>Zero-Lag Modern Qt Cockpit</b> • <b>Undetectable Behavioral Physics</b> • <b>Cryptographic Key Activation</b>
</p>

</div>

---

## 📖 Table of Contents
- [✨ Key Features](#-key-features)
- [🛡️ Anti-Ban Engine 3.0](#️-anti-ban-engine-30)
- [💰 Smart Loot Filtration](#-smart-loot-filtration)
- [⚔️ Combat Strategies](#️-combat-strategies)
- [🚀 Quickstart Guide](#-quickstart-guide)
- [🎮 Game & Emulator Setup](#-game--emulator-setup)
- [🔑 Activation Key System](#-activation-key-system)
- [📊 Cockpit & Discord Webhooks](#-cockpit--discord-webhooks)
- [🧪 Verification & Tests](#-verification--tests)
- [📦 Compiling to Standalone `.exe`](#-compiling-to-standalone-exe)
- [📁 Project Architecture](#-project-architecture)
- [⚖️ Disclaimer](#️-disclaimer)

---

## ✨ Key Features

- **🎯 Sub-Pixel Precision Direct Win32 Input**: Automatic client area offset calibration (`GetClientRect` & `ClientToScreen`) eliminates title bar offsets across all window modes, Google Play Games PC, and emulators.
- **🛡️ Undetectable Humanized Movement**: Physiological cubic Bézier trajectories, Gaussian spatial micro-scatter (±2px), realistic contact dwell (45–85ms), and randomized APM throttling.
- **💰 Smart Loot Filtration & Auto-Skip**: Real-time battle HUD optical character recognition (OCR). Dynamically skips unprofitable targets until configurable Gold, Elixir, and Dark Elixir thresholds are satisfied.
- **⚔️ Masterclass Combat Algorithms**: High-performance multi-finger perimeter waves (no camera dragging or map panning), intelligent bottom-bar troop auto-fallback, delayed hero ability timing, and defensive cluster spell penetration.
- **🌙 Aurora Dark Theme Cockpit**: Responsive PySide6 UI featuring live StatCards (**Gold/hr**, **Elixir/hr**, **DE/hr**, **Raids Completed**, **Bases Skipped**), real-time scrolling logs, and custom telemetry history.
- **📢 Discord Webhooks & Desktop Notifications**: Instant rich embed raid reports, loot summaries, and break alerts sent directly to your Discord server or Windows Action Center.
- **🔐 Hardware-Locked Licensing System**: Cryptographically signed HMAC-SHA256 activation with automated 2-hour free trials and 1-device monthly/lifetime binding.

---

## 🛡️ Anti-Ban Engine 3.0

ApexClash Pro incorporates state-of-the-art behavioral simulation engineered to bypass heuristic detection:

| Anti-Ban Component | Implementation Specification |
|:---|:---|
| **Trajectory Modeling** | Cubic Bézier curves with randomized control point inflection and ease-in/ease-out acceleration |
| **Spatial Dispersion** | Human hand jitter modeled with Gaussian normal distribution ($\sigma = 2.0\text{px}$) |
| **Contact Dwell** | Realistic physical mouse press duration varying between $45\text{ms}$ and $85\text{ms}$ |
| **APM Governor** | Dynamic Actions-Per-Minute limiter preventing repetitive robotic bursts |
| **Fatigue Scheduler** | Automated break intervals with randomized duration and human-like idle village inspections |
| **Stealth Profiles** | Pre-calibrated **Stealth**, **Balanced**, and **Fast** operating profiles |

---

## 💰 Smart Loot Filtration

Never waste troops on empty bases. The integrated vision engine inspects enemy storage levels in matchmaking before committing:

```
[Matchmaking Search] ──► [Inspect Top-Left HUD] ──► [Evaluate Thresholds]
                                                             │
                  ┌──────────────────────────────────────────┴──────────────────────────────────────────┐
                  ▼                                                                                     ▼
    [Criteria Met: Gold ≥ 500k, Elixir ≥ 500k]                                        [Below Thresholds: Gold < 500k]
                  │                                                                                     │
                  ▼                                                                                     ▼
       Deploy Combat Strategy                                                            Click 'Next' & Record Skip
```

- **OR Mode**: Attacks if **either** Gold or Elixir satisfies your quota.
- **AND Mode**: Requires **both** Gold and Elixir to be met simultaneously.
- **Dark Elixir Priority**: Specifically hunts for Dark Elixir reservoirs.
- **Max Skips Safety Override**: Attacks the best available base after reaching a search budget limit.

---

## ⚔️ Combat Strategies

### 1. 🟢 Sneaky Goblins (High-Velocity Resource Sniping)
- **Deployment**: Surgical 4-quadrant diamond perimeter taps along all boundaries (`left->top`, `top->right`, `right->bottom`, `bottom->left`).
- **Objective**: Rapidly extracts outer resource collectors and drills, penetrates compartments, and secures the Town Hall.
- **No Map-Panning**: Tap-based multi-wave deployment ensures the emulator camera stays locked in place.

### 2. ⚡ Electro Dragons (Chain Lightning Front)
- **Deployment**: Wide, evenly-spaced perimeter arc along the defense front line.
- **Objective**: Destroys high-density defensive clusters and core installations with bouncing lightning strikes.

### 3. 🪓 Valkyries & Super Minions (Core Penetration)
- **Deployment**: Fast perimeter funneling followed by concentrated core assault with Earthquake wall destruction.

### 4. 👑 Tactical Hero Ability Timing
- Deploys Barbarian King, Archer Queen, Grand Warden, and Royal Champion at designated funnel points.
- **Delayed Ability Activation (8–12s)**: Hero abilities are held until troops breach the outer defense ring, unleashing King Iron Fist, Queen Royal Cloak, and Warden Eternal Tome precisely when defenses focus fire.

### 5. 🔄 Intelligent Auto-Troop Fallback
- If a specific troop icon isn't matched due to visual skins or custom armies, ApexClash Pro automatically detects and selects alternative available troops or defaults to **Troop Slot 1**. Attacks are **never aborted** due to missing templates.

---

## 🚀 1-Click Installation & Launch Guide

### 🪟 Windows (1-Click Run)
- **Standalone Binary**: Download `ApexClashPro-Windows-x64.zip` from [Releases](https://github.com/keshav-x/coc-bot/releases), extract, and double-click `ApexClashPro.exe`.
- **From Source**: Double-click `start_windows.bat` — it automatically creates the environment, installs packages, and launches the app!

### 🐧 Linux & 🍓 Raspberry Pi (1-Click Setup)
Supports all Debian/Ubuntu flavors, Fedora, Arch, and **Raspberry Pi OS (ARM64 / aarch64 / armv7l)**:
```bash
# 1. Download and extract ApexClashPro-Linux-RaspberryPi-Universal.tar.gz
tar -xzf ApexClashPro-Linux-RaspberryPi-Universal.tar.gz
cd ApexClashPro

# 2. Run the 1-Click Installer (Installs system deps, venv, and Desktop shortcut):
./install_linux.sh
```
*After install, simply double-click the **ApexClash Pro** desktop icon or run `./start_linux.sh`!*

### 🍎 macOS (1-Click Finder Launch)
- Download `ApexClashPro-macOS-Universal.zip` from [Releases](https://github.com/keshav-x/coc-bot/releases).
- Extract and **double-click** `start_mac.command` directly in macOS Finder!
- It automatically configures the environment, installs requirements, and boots the application.

---

## 🎮 Game & Emulator Setup

ApexClash Pro is engineered to work out of the box with the most popular Windows game clients:

1. **Supported Clients**:
   - **Google Play Games on PC** *(Recommended official client)*
   - **BlueStacks 5**
   - **LDPlayer 9**
   - **MuMu Player / Nox**
2. **Display Settings**:
   - Set game resolution to **1920×1080** (16:9) or **1920×1200** (16:10).
   - Set game language to **English**.
3. **Window Selection**:
   - Launch Clash of Clans.
   - In ApexClash Pro, navigate to **Settings → Game Window** to select or auto-detect your game window.

---

## 🔑 Access Passes & Purchase Information

ApexClash Pro includes a **2-Hour Free Trial** automatically activated on first launch — test all features risk-free with zero setup or registration required.

To continue unlimited farming after your trial, purchase an activation key directly from the developer:

| Pass Tier | Price | Duration | Features |
| :--- | :--- | :--- | :--- |
| **Weekly Pass** | **$1.00** | 7 Days | Full Access, Autonomous Farming, Smart Loot Filter |
| **Monthly Pass** | **$3.00** | 30 Days | Full Access, Autonomous Farming, Smart Loot Filter |
| **Annual Pass** | **$10.00** | 365 Days | Full Access, All Updates, Priority Support |
| **Lifetime Pass** | **$15.00** | Lifetime | Permanent VIP Access, All Future Updates, Priority Support |

### 🛒 How to Purchase
1. Launch ApexClash Pro and navigate to the **License** page.
2. Click **📋 Copy HW ID** to copy your unique PC Hardware Fingerprint.
3. Contact the developer via any of the channels below with your Machine ID:
   - 📧 **Email**: [cockingkeshav@gmail.com](mailto:cockingkeshav@gmail.com)
   - 💬 **Discord**: `matrix0456`
   - 🌐 **Reddit**: `u/post_matrix`
4. Accepted payment methods: **PayPal, Crypto (USDT / BTC / LTC), UPI, Cards**.
5. Your activation key is signed with private Ed25519 asymmetric cryptography and delivered instantly upon payment!

---

## 📊 Cockpit & Discord Webhooks

Stay updated on your farming progress from anywhere:

- **Live StatCards**: Displays real-time estimated hourly loot velocity and raid counts.
- **Discord Webhooks**: Configure your webhook URL under **Settings → Webhook** to receive automatic raid completion embeds, loot snapshots, and break notifications.
- **Native Desktop Notifications**: Windows Action Center banners alert you when mega raids are completed or scheduled breaks begin.

---

## 🧪 Verification & Tests

ApexClash Pro ships with automated test suites verifying all core modules:

```powershell
# Run full logic, trial, anti-ban, and filtration tests:
python scratch/test_suite.py

# Run coordinate calibration, precision scatter, and combat strategy tests:
python scratch/test_attack_logic.py

# Run headless PySide6 GUI integration test:
python scratch/test_gui.py
```

---

## 📦 Compiling to Standalone `.exe`

To package ApexClash Pro into a portable Windows executable:

```powershell
python -m pip install pyinstaller
pyinstaller --noconfirm --onedir --windowed `
  --name "ApexClashPro" `
  --icon "assets/apex_clash_logo.ico" `
  --add-data "assets;assets" `
  --add-data "templates;templates" `
  --add-data "tessdata;tessdata" `
  main.py
```

The compiled binary will be generated under `dist/ApexClashPro/ApexClashPro.exe`.

---

## 📁 Project Architecture

```
coc-bot/
├── assets/                       # High-resolution logos & ICO files
│   ├── apex_clash_logo.png
│   └── apex_clash_logo.ico
├── templates/                    # Computer vision matching templates
│   ├── 16_9/                     # 16:9 reference graphics
│   ├── 16_10/                    # 16:10 reference graphics
│   └── icons/                    # Resource icons (Gold, Elixir, Dark Elixir)
├── app/
│   ├── core/                     # Bot execution & strategy logic
│   │   ├── bot.py                # Main state loop & village navigation
│   │   ├── loot_filter.py        # Smart Loot Filtration engine
│   │   ├── run_plan.py           # Multi-account rotation plan
│   │   ├── strategies.py         # Multi-wave combat algorithms
│   │   └── watchdog.py           # Auto-recovery watchdog
│   ├── services/                 # Hardware & system service bridges
│   │   ├── antiban.py            # Bézier paths, Gaussian jitter & breaks
│   │   ├── input.py              # Win32 PostMessage mouse dispatch
│   │   ├── license.py            # Cryptographic key validation
│   │   ├── notifications.py      # Native Windows notifications
│   │   ├── trial.py              # 2-hour free trial tracker
│   │   ├── vision.py             # OpenCV template matching & OCR
│   │   ├── webhook.py            # Discord embed webhook dispatcher
│   │   └── window.py             # Win32 client area capture & cropping
│   └── ui/qt/                    # PySide6 desktop GUI
│       ├── branding.py           # Brand identities & logo loaders
│       ├── main_window.py        # Sidebar & central stack coordinator
│       ├── theme.py              # Design tokens & Aurora Cyber palette
│       ├── widgets.py            # Custom cards, buttons, & toggles
│       └── pages/                # Individual app pages
├── main.py                       # Application bootstrap
└── requirements.txt              # Project dependencies
```

---

## ⚖️ Disclaimer

*ApexClash Pro is developed solely for educational, reverse-engineering, and computer vision research purposes. Clash of Clans is a registered trademark of Supercell Oy. This project is not affiliated with, endorsed, or sponsored by Supercell. Users are responsible for complying with all applicable terms of service.*
