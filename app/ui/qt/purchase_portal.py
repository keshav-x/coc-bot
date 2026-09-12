"""Official Purchase Portal Generator & Browser Launcher for ApexClash Pro.

Generates a standalone, ultra-rich interactive HTML checkout website and launches
the user's default web browser with dynamic pack selection, payment method options,
and instant contact integration (Gmail, Reddit, Discord).
"""

from __future__ import annotations

import base64
import html
import io
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional

from PIL import Image

from app.ui.qt._constants import (
    CONTACT_DISCORD,
    CONTACT_EMAIL,
    CONTACT_REDDIT,
)
from app.utils.common import ensure_dir, get_resource_path, get_user_app_data_dir

_LOGO_CACHE_B64: Optional[str] = None


def get_logo_b64() -> str:
    """Return base64-encoded PNG string of the official ApexClash logo."""
    global _LOGO_CACHE_B64
    if _LOGO_CACHE_B64 is not None:
        return _LOGO_CACHE_B64

    for logo_rel in ("assets/apex_clash_logo.png", "assets/clash_autoloot_logo.png"):
        p = get_resource_path(logo_rel)
        if p.is_file():
            try:
                img = Image.open(p)
                img.thumbnail((200, 200), Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG", optimize=True)
                _LOGO_CACHE_B64 = base64.b64encode(buf.getvalue()).decode("ascii")
                return _LOGO_CACHE_B64
            except Exception:
                pass
    return ""


def generate_purchase_html(machine_id: str, default_tier: str = "monthly") -> str:
    """Generate high-aesthetic, interactive dark-mode Cyber HTML checkout website."""
    logo_b64 = get_logo_b64()
    logo_src = f"data:image/png;base64,{logo_b64}" if logo_b64 else ""
    encoded_hw = html.escape(machine_id)
    norm_tier = default_tier.lower()
    if "life" in norm_tier:
        initial_pack = "lifetime"
    elif "week" in norm_tier:
        initial_pack = "weekly"
    elif "annu" in norm_tier or "year" in norm_tier:
        initial_pack = "annual"
    else:
        initial_pack = "monthly"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ApexClash Pro — Official Purchase & Activation Portal</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg: #070b14;
      --card-bg: rgba(15, 23, 42, 0.75);
      --card-border: rgba(255, 255, 255, 0.08);
      --primary: #38bdf8;
      --primary-glow: rgba(56, 189, 248, 0.25);
      --accent-green: #10b981;
      --accent-green-glow: rgba(16, 185, 129, 0.25);
      --accent-gold: #f59e0b;
      --accent-gold-glow: rgba(245, 158, 11, 0.25);
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --surface-hi: #1e293b;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      background-image: 
        radial-gradient(at 0% 0%, rgba(56, 189, 248, 0.12) 0px, transparent 50%),
        radial-gradient(at 100% 100%, rgba(16, 185, 129, 0.08) 0px, transparent 50%),
        radial-gradient(at 50% 50%, rgba(15, 23, 42, 0.5) 0px, transparent 100%);
      color: var(--text);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 30px 16px 60px;
      -webkit-font-smoothing: antialiased;
    }}

    .container {{
      max-width: 880px;
      width: 100%;
    }}

    /* Top Brand Nav */
    .nav-bar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 24px;
      padding: 12px 20px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      backdrop-filter: blur(16px);
    }}
    .brand-left {{
      display: flex;
      align-items: center;
      gap: 14px;
    }}
    .brand-logo {{
      width: 44px;
      height: 44px;
      border-radius: 10px;
      box-shadow: 0 0 15px rgba(56, 189, 248, 0.3);
      object-fit: cover;
    }}
    .brand-text {{
      display: flex;
      flex-direction: column;
    }}
    .brand-name {{
      font-size: 17px;
      font-weight: 800;
      letter-spacing: -0.5px;
      background: linear-gradient(135deg, #ffffff 40%, #94a3b8 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .brand-sub {{
      font-size: 10px;
      color: var(--primary);
      font-weight: 700;
      letter-spacing: 1px;
      text-transform: uppercase;
    }}
    .status-pill {{
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 11px;
      font-weight: 700;
      color: var(--accent-green);
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.25);
      border-radius: 20px;
      padding: 5px 12px;
    }}
    .status-dot {{
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--accent-green);
      box-shadow: 0 0 8px var(--accent-green);
      animation: pulse 2s infinite;
    }}
    @keyframes pulse {{
      0% {{ opacity: 0.6; }}
      50% {{ opacity: 1; transform: scale(1.1); }}
      100% {{ opacity: 0.6; }}
    }}

    /* Hero */
    .hero {{
      text-align: center;
      margin-bottom: 28px;
    }}
    .hero-badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(56, 189, 248, 0.1);
      border: 1px solid rgba(56, 189, 248, 0.25);
      color: var(--primary);
      padding: 4px 14px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 700;
      margin-bottom: 12px;
    }}
    .hero h1 {{
      font-size: 32px;
      font-weight: 900;
      line-height: 1.2;
      letter-spacing: -0.5px;
      margin-bottom: 8px;
    }}
    .hero h1 span.gradient {{
      background: linear-gradient(135deg, #38bdf8 20%, #10b981 80%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    .hero p {{
      color: var(--text-muted);
      font-size: 14px;
      max-width: 580px;
      margin: 0 auto;
      line-height: 1.5;
    }}

    /* Section Headings */
    .section-title {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 15px;
      font-weight: 700;
      color: #e2e8f0;
      margin-bottom: 12px;
      letter-spacing: -0.2px;
    }}
    .section-title .step {{
      background: var(--surface-hi);
      color: var(--primary);
      width: 22px;
      height: 22px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 11px;
      font-weight: 800;
    }}

    /* Card Wrapper */
    .box {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 16px;
      backdrop-filter: blur(16px);
      padding: 22px;
      margin-bottom: 24px;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
    }}

    /* Hardware ID Box */
    .hw-container {{
      display: flex;
      align-items: center;
      gap: 12px;
      background: #090e17;
      border: 1px solid #1e293b;
      border-radius: 10px;
      padding: 10px 14px;
      margin-bottom: 6px;
      transition: all 0.2s;
    }}
    .hw-container:hover {{
      border-color: #38bdf8;
    }}
    .hw-text {{
      font-family: 'JetBrains Mono', 'Courier New', monospace;
      font-size: 13px;
      font-weight: 600;
      color: #38bdf8;
      flex: 1;
      word-break: break-all;
    }}
    .btn-copy-id {{
      background: var(--surface-hi);
      color: #f8fafc;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 8px 14px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
      white-space: nowrap;
    }}
    .btn-copy-id:hover {{
      background: #334155;
      border-color: #64748b;
    }}
    .hw-hint {{
      font-size: 11px;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .copy-toast {{
      color: var(--accent-green);
      font-weight: 700;
      font-size: 11px;
      min-height: 16px;
    }}

    /* Interactive Pack Selection Grid */
    .pack-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
      margin-bottom: 16px;
    }}
    @media (max-width: 768px) {{
      .pack-grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}
    @media (max-width: 480px) {{
      .pack-grid {{ grid-template-columns: 1fr; }}
    }}

    .pack-card {{
      background: #0d1524;
      border: 2px solid #1e293b;
      border-radius: 14px;
      padding: 16px 14px;
      text-align: left;
      cursor: pointer;
      position: relative;
      transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      user-select: none;
    }}
    .pack-card:hover {{
      transform: translateY(-4px);
      border-color: #475569;
      background: #111b2e;
    }}
    .pack-card.selected {{
      border-color: var(--primary);
      background: rgba(56, 189, 248, 0.08);
      box-shadow: 0 0 25px var(--primary-glow), inset 0 0 15px rgba(56, 189, 248, 0.08);
    }}
    .pack-card.featured.selected {{
      border-color: var(--accent-green);
      background: rgba(16, 185, 129, 0.08);
      box-shadow: 0 0 25px var(--accent-green-glow), inset 0 0 15px rgba(16, 185, 129, 0.08);
    }}
    .pack-card.vip.selected {{
      border-color: var(--accent-gold);
      background: rgba(245, 158, 11, 0.08);
      box-shadow: 0 0 28px var(--accent-gold-glow), inset 0 0 18px rgba(245, 158, 11, 0.1);
    }}

    .pack-top {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 8px;
    }}
    .pack-badge {{
      font-size: 10px;
      font-weight: 800;
      text-transform: uppercase;
      padding: 3px 7px;
      border-radius: 6px;
      letter-spacing: 0.5px;
    }}
    .badge-blue {{ background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); }}
    .badge-green {{ background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.4); }}
    .badge-gold {{ background: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.4); }}

    .radio-circle {{
      width: 18px;
      height: 18px;
      border-radius: 50%;
      border: 2px solid #475569;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s;
    }}
    .pack-card.selected .radio-circle {{
      border-color: var(--primary);
      background: var(--primary);
    }}
    .pack-card.featured.selected .radio-circle {{
      border-color: var(--accent-green);
      background: var(--accent-green);
    }}
    .pack-card.vip.selected .radio-circle {{
      border-color: var(--accent-gold);
      background: var(--accent-gold);
    }}
    .radio-dot {{
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #000;
      opacity: 0;
      transition: opacity 0.2s;
    }}
    .pack-card.selected .radio-dot {{
      opacity: 1;
    }}

    .pack-name {{
      font-size: 14px;
      font-weight: 700;
      color: #cbd5e1;
      margin-bottom: 2px;
    }}
    .pack-price {{
      font-size: 24px;
      font-weight: 900;
      color: #ffffff;
      margin-bottom: 4px;
      letter-spacing: -0.5px;
    }}
    .pack-sub {{
      font-size: 11px;
      color: var(--text-muted);
      margin-bottom: 12px;
    }}
    .pack-features {{
      list-style: none;
      font-size: 11px;
      color: #94a3b8;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      padding-top: 10px;
    }}
    .pack-features li {{
      margin-bottom: 5px;
      display: flex;
      align-items: center;
      gap: 5px;
    }}
    .pack-features li::before {{
      content: '✓';
      color: var(--accent-green);
      font-weight: bold;
    }}

    /* Payment Method Chips */
    .payments-row {{
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 8px;
    }}
    .pay-chip {{
      background: #090e17;
      border: 1px solid #1e293b;
      border-radius: 8px;
      padding: 8px 14px;
      font-size: 12px;
      font-weight: 600;
      color: #cbd5e1;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
      user-select: none;
    }}
    .pay-chip:hover {{
      border-color: #475569;
      background: #111b2e;
    }}
    .pay-chip.selected {{
      border-color: var(--accent-green);
      background: rgba(16, 185, 129, 0.12);
      color: #ffffff;
      box-shadow: 0 0 12px rgba(16, 185, 129, 0.2);
    }}

    /* Live Summary Box */
    .summary-box {{
      background: #090e17;
      border: 1px solid #1e293b;
      border-radius: 12px;
      padding: 16px 18px;
      margin-bottom: 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .sum-left {{
      display: flex;
      flex-direction: column;
      gap: 3px;
    }}
    .sum-label {{
      font-size: 11px;
      color: var(--text-muted);
      text-transform: uppercase;
      font-weight: 700;
      letter-spacing: 0.5px;
    }}
    .sum-title {{
      font-size: 16px;
      font-weight: 800;
      color: #ffffff;
    }}
    .sum-detail {{
      font-size: 12px;
      color: var(--accent-green);
      font-weight: 600;
    }}
    .sum-right {{
      text-align: right;
    }}
    .sum-total {{
      font-size: 26px;
      font-weight: 900;
      color: var(--primary);
    }}

    /* Action Buttons */
    .actions-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: 12px;
    }}
    @media (max-width: 600px) {{
      .actions-grid {{ grid-template-columns: 1fr; }}
    }}
    .btn-action {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      padding: 14px 18px;
      border-radius: 10px;
      text-decoration: none;
      font-size: 14px;
      font-weight: 700;
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      cursor: pointer;
      border: none;
      text-align: center;
    }}
    .btn-action:hover {{
      transform: translateY(-2px);
      box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3);
    }}
    .btn-gmail {{
      background: linear-gradient(135deg, #ea4335, #c5221f);
      color: #ffffff;
    }}
    .btn-gmail:hover {{
      box-shadow: 0 8px 20px rgba(234, 67, 53, 0.35);
    }}
    .btn-reddit {{
      background: linear-gradient(135deg, #ff4500, #cc3700);
      color: #ffffff;
    }}
    .btn-reddit:hover {{
      box-shadow: 0 8px 20px rgba(255, 69, 0, 0.35);
    }}
    .btn-discord {{
      background: linear-gradient(135deg, #5865f2, #4752c4);
      color: #ffffff;
    }}
    .btn-discord:hover {{
      box-shadow: 0 8px 20px rgba(88, 101, 242, 0.35);
    }}
    .btn-copy-order {{
      background: var(--surface-hi);
      color: #f1f5f9;
      border: 1px solid #475569;
    }}
    .btn-copy-order:hover {{
      background: #334155;
    }}

    /* Guarantee bar */
    .guarantees {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
      margin-top: 14px;
      padding-top: 14px;
      border-top: 1px solid rgba(255, 255, 255, 0.06);
    }}
    @media (max-width: 600px) {{
      .guarantees {{ grid-template-columns: 1fr; }}
    }}
    .guarantee-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 11px;
      color: #94a3b8;
    }}
    .guarantee-item strong {{
      color: #e2e8f0;
    }}

    .footer {{
      text-align: center;
      font-size: 11px;
      color: #475569;
      margin-top: 24px;
      line-height: 1.6;
    }}
  </style>
</head>
<body>
  <div class="container">
    <!-- Nav Bar -->
    <div class="nav-bar">
      <div class="brand-left">
        {f'<img src="{logo_src}" class="brand-logo" alt="ApexClash Logo">' if logo_src else '<div class="brand-logo" style="background:#38bdf8;"></div>'}
        <div class="brand-text">
          <span class="brand-name">ApexClash Pro</span>
          <span class="brand-sub">Official Activation Store</span>
        </div>
      </div>
      <div class="status-pill">
        <span class="status-dot"></span>
        <span>INSTANT DELIVERY ONLINE</span>
      </div>
    </div>

    <!-- Hero -->
    <div class="hero">
      <div class="hero-badge">⚡ INSTANT CRYPTOGRAPHIC KEYS</div>
      <h1>Select Your Access Pass for <span class="gradient">ApexClash Pro</span></h1>
      <p>Zero-gem spending protection, smart anti-ban Bézier heuristics, and automated wall upgrades. Keys are generated instantly upon payment confirmation.</p>
    </div>

    <!-- Step 1: Hardware ID -->
    <div class="box">
      <div class="section-title">
        <span class="step">1</span>
        <span>Your Unique Hardware Device ID</span>
      </div>
      <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 10px;">
        Each license is cryptographically signed for your machine. This ID is automatically included when contacting:
      </p>
      <div class="hw-container">
        <div class="hw-text" id="hw-id-val">{encoded_hw}</div>
        <button class="btn-copy-id" onclick="copyHwId()">
          <span>📋</span>
          <span id="btn-copy-txt">Copy ID</span>
        </button>
      </div>
      <div class="hw-hint">
        <span>Hardware fingerprint verified</span>
        <span class="copy-toast" id="hw-toast"></span>
      </div>
    </div>

    <!-- Step 2: Interactive Pack Selection -->
    <div class="box">
      <div class="section-title">
        <span class="step">2</span>
        <span>Select Your Access Pack</span>
      </div>
      <div class="pack-grid">
        <!-- Weekly -->
        <div class="pack-card" id="pack-weekly" onclick="selectPack('weekly', 'Weekly Pass', '$1.00', '7 Days Access')">
          <div class="pack-top">
            <span class="pack-badge badge-blue">Trial</span>
            <div class="radio-circle"><div class="radio-dot"></div></div>
          </div>
          <div>
            <div class="pack-name">Weekly Pass</div>
            <div class="pack-price">$1.00</div>
            <div class="pack-sub">7 Days Full VIP</div>
          </div>
          <ul class="pack-features">
            <li>Zero-Gem Guard</li>
            <li>Smart Anti-Ban</li>
            <li>Instant Key</li>
          </ul>
        </div>

        <!-- Monthly -->
        <div class="pack-card featured" id="pack-monthly" onclick="selectPack('monthly', 'Monthly Pass', '$3.00', '30 Days Access')">
          <div class="pack-top">
            <span class="pack-badge badge-green">Popular</span>
            <div class="radio-circle"><div class="radio-dot"></div></div>
          </div>
          <div>
            <div class="pack-name">Monthly Pass</div>
            <div class="pack-price">$3.00</div>
            <div class="pack-sub">30 Days Full VIP</div>
          </div>
          <ul class="pack-features">
            <li>Wall Upgrades</li>
            <li>Discord Webhook</li>
            <li>Regular Farming</li>
          </ul>
        </div>

        <!-- Annual -->
        <div class="pack-card" id="pack-annual" onclick="selectPack('annual', 'Annual Pass', '$10.00', '365 Days Access')">
          <div class="pack-top">
            <span class="pack-badge badge-blue">Best Value</span>
            <div class="radio-circle"><div class="radio-dot"></div></div>
          </div>
          <div>
            <div class="pack-name">Annual Pass</div>
            <div class="pack-price">$10.00</div>
            <div class="pack-sub">365 Days Full VIP</div>
          </div>
          <ul class="pack-features">
            <li>All Game Updates</li>
            <li>Continuous Loot</li>
            <li>Best Price/Month</li>
          </ul>
        </div>

        <!-- Lifetime -->
        <div class="pack-card vip" id="pack-lifetime" onclick="selectPack('lifetime', 'Lifetime VIP Pass', '$15.00', 'Permanent Access')">
          <div class="pack-top">
            <span class="pack-badge badge-gold">VIP Choice</span>
            <div class="radio-circle"><div class="radio-dot"></div></div>
          </div>
          <div>
            <div class="pack-name">Lifetime VIP</div>
            <div class="pack-price">$15.00</div>
            <div class="pack-sub">Permanent Access</div>
          </div>
          <ul class="pack-features">
            <li>Never Expires</li>
            <li>All Future Patches</li>
            <li>Priority Delivery</li>
          </ul>
        </div>
      </div>

      <!-- Payment Method -->
      <div style="font-size: 13px; font-weight: 700; color: #cbd5e1; margin-bottom: 8px;">
        Choose Preferred Payment Method:
      </div>
      <div class="payments-row">
        <div class="pay-chip selected" id="pay-paypal" onclick="selectPayment('PayPal')">
          <span>🅿️</span> <span>PayPal</span>
        </div>
        <div class="pay-chip" id="pay-upi" onclick="selectPayment('UPI')">
          <span>⚡</span> <span>UPI (GPay/PhonePe/Paytm)</span>
        </div>
        <div class="pay-chip" id="pay-crypto" onclick="selectPayment('Crypto')">
          <span>🪙</span> <span>Crypto (USDT / BTC / LTC)</span>
        </div>
        <div class="pay-chip" id="pay-card" onclick="selectPayment('Cards')">
          <span>💳</span> <span>Credit / Debit Cards</span>
        </div>
      </div>
    </div>

    <!-- Step 3: Live Order Summary & One-Click Contact -->
    <div class="box">
      <div class="section-title">
        <span class="step">3</span>
        <span>Order Summary & Instant Key Dispatch</span>
      </div>

      <div class="summary-box">
        <div class="sum-left">
          <div class="sum-label">Selected Access Pack</div>
          <div class="sum-title" id="sum-name">Monthly Pass</div>
          <div class="sum-detail" id="sum-meta">30 Days Access • Payment via PayPal</div>
        </div>
        <div class="sum-right">
          <div class="sum-label">Total Amount</div>
          <div class="sum-total" id="sum-price">$3.00</div>
        </div>
      </div>

      <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 14px;">
        Click below to send your order. Your Device ID and pack details will be automatically pre-filled:
      </p>

      <div class="actions-grid">
        <a class="btn-action btn-gmail" id="action-gmail" href="#" target="_blank">
          <span>📧</span>
          <span>Open in Gmail (Web Browser)</span>
        </a>

        <a class="btn-action btn-reddit" id="action-reddit" href="#" target="_blank">
          <span>💬</span>
          <span>Message on Reddit (u/{CONTACT_REDDIT})</span>
        </a>

        <button class="btn-action btn-discord" onclick="copyDiscordContact()">
          <span>💬</span>
          <span>Discord: {CONTACT_DISCORD} (Click to Copy)</span>
        </button>

        <button class="btn-action btn-copy-order" onclick="copyCompleteOrder()">
          <span id="copy-order-icon">📋</span>
          <span id="copy-order-txt">Copy Order Template</span>
        </button>
      </div>

      <div style="text-align: center; margin-top: 10px;">
        <a id="action-mailto" href="#" style="color: #64748b; font-size: 11px; text-decoration: underline;">
          Or open in default desktop email client (mailto:)
        </a>
      </div>

      <div class="guarantees">
        <div class="guarantee-item">
          <span>🛡️</span>
          <span><strong>Zero-Gem Guard:</strong> Strictly vetoes gem dialogs</span>
        </div>
        <div class="guarantee-item">
          <span>🔒</span>
          <span><strong>Ed25519 Security:</strong> Verified 100% offline</span>
        </div>
        <div class="guarantee-item">
          <span>⚡</span>
          <span><strong>Fast Delivery:</strong> Instant response from dev</span>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div class="footer">
      ApexClash Pro • Autonomous Combat Suite • Developer: {CONTACT_EMAIL} • Discord: {CONTACT_DISCORD} • Reddit: u/{CONTACT_REDDIT}<br>
      © 2026 ApexClash Pro. All rights reserved.
    </div>
  </div>

  <script>
    const MACHINE_ID = '{encoded_hw}';
    const DEVELOPER_EMAIL = '{CONTACT_EMAIL}';
    const DEVELOPER_REDDIT = '{CONTACT_REDDIT}';
    const DEVELOPER_DISCORD = '{CONTACT_DISCORD}';

    let currentPack = {{
      key: '{initial_pack}',
      name: 'Monthly Pass',
      price: '$3.00',
      duration: '30 Days Access'
    }};
    let currentPayment = 'PayPal';

    const PACKS = {{
      weekly: {{ name: 'Weekly Pass', price: '$1.00', duration: '7 Days Access' }},
      monthly: {{ name: 'Monthly Pass', price: '$3.00', duration: '30 Days Access' }},
      annual: {{ name: 'Annual Pass', price: '$10.00', duration: '365 Days Access' }},
      lifetime: {{ name: 'Lifetime VIP Pass', price: '$15.00', duration: 'Permanent VIP Access' }}
    }};

    function selectPack(key) {{
      if (!PACKS[key]) return;
      currentPack = {{ key, ...PACKS[key] }};
      
      // Update UI cards
      document.querySelectorAll('.pack-card').forEach(card => card.classList.remove('selected'));
      const activeCard = document.getElementById('pack-' + key);
      if (activeCard) activeCard.classList.add('selected');

      updateLiveSummary();
    }}

    function selectPayment(method) {{
      currentPayment = method;
      document.querySelectorAll('.pay-chip').forEach(chip => chip.classList.remove('selected'));
      const chipId = 'pay-' + method.toLowerCase().replace(/[^a-z]/g, '');
      const activeChip = document.getElementById(chipId);
      if (activeChip) activeChip.classList.add('selected');

      updateLiveSummary();
    }}

    function updateLiveSummary() {{
      document.getElementById('sum-name').innerText = currentPack.name;
      document.getElementById('sum-meta').innerText = currentPack.duration + ' • Payment via ' + currentPayment;
      document.getElementById('sum-price').innerText = currentPack.price;

      // Update action links
      const subject = encodeURIComponent('ApexClash Pro Purchase Request - ' + currentPack.name);
      const body = encodeURIComponent(
        'Hi Keshav,\\n\\n' +
        'I would like to purchase ApexClash Pro.\\n\\n' +
        'Plan Selected: ' + currentPack.name + ' (' + currentPack.price + ')\\n' +
        'My Device ID: ' + MACHINE_ID + '\\n' +
        'Preferred Payment: ' + currentPayment + '\\n\\n' +
        'Thank you!'
      );

      const gmailLink = document.getElementById('action-gmail');
      if (gmailLink) {{
        gmailLink.href = 'https://mail.google.com/mail/?view=cm&fs=1&to=' + DEVELOPER_EMAIL + '&su=' + subject + '&body=' + body;
      }}

      const redditLink = document.getElementById('action-reddit');
      if (redditLink) {{
        redditLink.href = 'https://www.reddit.com/message/compose/?to=' + DEVELOPER_REDDIT + 
          '&subject=' + subject + 
          '&message=' + encodeURIComponent('Hi Keshav, I would like to buy ' + currentPack.name + ' (' + currentPack.price + '). My Device ID is: ' + MACHINE_ID + ' (Payment via ' + currentPayment + ')');
      }}

      const mailtoLink = document.getElementById('action-mailto');
      if (mailtoLink) {{
        mailtoLink.href = 'mailto:' + DEVELOPER_EMAIL + '?subject=' + subject + '&body=' + body;
      }}
    }}

    function copyHwId() {{
      navigator.clipboard.writeText(MACHINE_ID).then(() => {{
        const toast = document.getElementById('hw-toast');
        const btnTxt = document.getElementById('btn-copy-txt');
        toast.innerText = '✓ Device ID copied!';
        btnTxt.innerText = 'Copied!';
        setTimeout(() => {{
          toast.innerText = '';
          btnTxt.innerText = 'Copy ID';
        }}, 2500);
      }}).catch(() => {{
        alert('Device ID: ' + MACHINE_ID);
      }});
    }}

    function copyDiscordContact() {{
      navigator.clipboard.writeText(DEVELOPER_DISCORD).then(() => {{
        alert('Discord handle "' + DEVELOPER_DISCORD + '" copied to clipboard! Send a direct message or friend request on Discord.');
      }}).catch(() => {{
        alert('Discord ID: ' + DEVELOPER_DISCORD);
      }});
    }}

    function copyCompleteOrder() {{
      const orderText = 
        'ApexClash Pro Purchase Request\\n' +
        '==============================\\n' +
        'Pass: ' + currentPack.name + ' (' + currentPack.price + ')\\n' +
        'Device ID: ' + MACHINE_ID + '\\n' +
        'Payment: ' + currentPayment + '\\n' +
        'Developer: ' + DEVELOPER_EMAIL + ' / Discord: ' + DEVELOPER_DISCORD;
      
      navigator.clipboard.writeText(orderText).then(() => {{
        const btnTxt = document.getElementById('copy-order-txt');
        const btnIcon = document.getElementById('copy-order-icon');
        btnTxt.innerText = 'Order Copied to Clipboard!';
        btnIcon.innerText = '✓';
        setTimeout(() => {{
          btnTxt.innerText = 'Copy Order Template';
          btnIcon.innerText = '📋';
        }}, 3000);
      }}).catch(() => {{
        alert(orderText);
      }});
    }}

    // Initial activation
    selectPack('{initial_pack}');
  </script>
</body>
</html>
"""


STORE_URL = "https://keshav-x.github.io/coc-bot/"


def get_live_purchase_url(machine_id: str, selected_tier: str = "monthly") -> str:
    """Build the official live GitHub Pages checkout URL with pre-filled query params."""
    norm = selected_tier.lower()
    pack = "monthly"
    if "life" in norm:
        pack = "lifetime"
    elif "week" in norm:
        pack = "weekly"
    elif "annu" in norm or "year" in norm:
        pack = "annual"
    params = urllib.parse.urlencode({"hwid": machine_id, "pack": pack})
    return f"{STORE_URL}?{params}"


def open_purchase_portal(machine_id: str, selected_tier: str = "Monthly ($3/mo)") -> str:
    """Open the live GitHub Pages store, and write offline fallback purchase.html to disk."""
    app_data = get_user_app_data_dir()
    ensure_dir(app_data)
    html_file = app_data / "purchase.html"
    content = generate_purchase_html(machine_id, selected_tier)
    html_file.write_text(content, encoding="utf-8")

    live_url = get_live_purchase_url(machine_id, selected_tier)
    try:
        webbrowser.open(live_url)
        return live_url
    except Exception:
        file_uri = html_file.resolve().as_uri()
        webbrowser.open(file_uri)
        return file_uri
