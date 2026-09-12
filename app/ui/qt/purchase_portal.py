"""Official Purchase Portal Generator & Browser Launcher for ApexClash Pro.

Generates a standalone, rich HTML checkout page and launches the user's
default web browser with one-click direct contact options (Gmail, Reddit, Discord).
"""

from __future__ import annotations

import html
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Optional

from app.ui.qt._constants import (
    CONTACT_DISCORD,
    CONTACT_EMAIL,
    CONTACT_REDDIT,
    PLAN_PRICE_ANNUAL,
    PLAN_PRICE_LIFETIME,
    PLAN_PRICE_MONTHLY,
    PLAN_PRICE_WEEKLY,
)
from app.utils.common import ensure_dir, get_user_app_data_dir


def generate_purchase_html(machine_id: str, selected_tier: str = "Monthly Pass ($3.00)") -> str:
    """Return responsive dark-mode cyber HTML for the purchase portal."""
    encoded_hw = html.escape(machine_id)
    subject = urllib.parse.quote(f"ApexClash Pro Purchase Request - {selected_tier}")
    body = urllib.parse.quote(
        f"Hi Keshav,\n\n"
        f"I would like to purchase an ApexClash Pro license key.\n\n"
        f"Selected Pass: {selected_tier}\n"
        f"Device ID: {machine_id}\n"
        f"Preferred Payment: PayPal / Crypto (USDT/BTC) / UPI / Card\n\n"
        f"Thank you!"
    )
    gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={CONTACT_EMAIL}&su={subject}&body={body}"
    mailto_url = f"mailto:{CONTACT_EMAIL}?subject={subject}&body={body}"
    reddit_msg_url = (
        f"https://www.reddit.com/message/compose/?to={CONTACT_REDDIT}"
        f"&subject={urllib.parse.quote('ApexClash Pro Purchase')}"
        f"&message={urllib.parse.quote(f'Hi, I would like to buy ApexClash Pro ({selected_tier}). My Device ID is: {machine_id}')}"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ApexClash Pro — Official Purchase & Activation</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }}
    body {{ background: #0b0f19; color: #f1f5f9; min-height: 100vh; display: flex; flex-direction: column; align-items: center; padding: 40px 20px; }}
    .container {{ max-width: 760px; width: 100%; }}
    .header {{ text-align: center; margin-bottom: 30px; }}
    .badge {{ display: inline-block; background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 20px; padding: 4px 14px; font-size: 12px; font-weight: bold; margin-bottom: 12px; }}
    h1 {{ font-size: 28px; font-weight: 800; color: #ffffff; margin-bottom: 8px; letter-spacing: -0.5px; }}
    h1 span {{ background: linear-gradient(135deg, #38bdf8, #22c55e); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
    .subtitle {{ color: #94a3b8; font-size: 14px; line-height: 1.5; }}
    .card {{ background: #131c2e; border: 1px solid #1e293b; border-radius: 14px; padding: 24px; margin-bottom: 24px; box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3); }}
    .card h2 {{ font-size: 16px; font-weight: 700; color: #e2e8f0; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }}
    
    .hw-box {{ display: flex; gap: 10px; align-items: center; background: #090e17; border: 1px solid #334155; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; }}
    .hw-code {{ font-family: 'Courier New', monospace; font-size: 14px; color: #38bdf8; font-weight: bold; flex: 1; word-break: break-all; }}
    .copy-btn {{ background: #1e293b; color: #f8fafc; border: 1px solid #475569; border-radius: 6px; padding: 8px 14px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s; white-space: nowrap; }}
    .copy-btn:hover {{ background: #334155; border-color: #64748b; }}
    .copy-feedback {{ font-size: 11px; color: #22c55e; min-height: 16px; font-weight: bold; margin-bottom: 12px; }}

    .pricing-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .tier-card {{ background: #0d1524; border: 1px solid #1e293b; border-radius: 10px; padding: 14px; text-align: center; position: relative; transition: all 0.2s; }}
    .tier-card.featured {{ border-color: #22c55e; background: rgba(34, 197, 94, 0.05); }}
    .tier-card.vip {{ border-color: #f59e0b; background: rgba(245, 158, 11, 0.05); }}
    .tier-badge {{ font-size: 9px; font-weight: bold; text-transform: uppercase; padding: 2px 6px; border-radius: 4px; margin-bottom: 6px; display: inline-block; }}
    .tier-badge.gold {{ background: rgba(245, 158, 11, 0.2); color: #f59e0b; }}
    .tier-badge.green {{ background: rgba(34, 197, 94, 0.2); color: #22c55e; }}
    .tier-badge.blue {{ background: rgba(56, 189, 248, 0.2); color: #38bdf8; }}
    .tier-title {{ font-size: 13px; font-weight: 600; color: #cbd5e1; margin-bottom: 4px; }}
    .tier-price {{ font-size: 20px; font-weight: 800; color: #ffffff; margin-bottom: 4px; }}
    .tier-sub {{ font-size: 11px; color: #64748b; }}

    .btn-row {{ display: flex; flex-direction: column; gap: 10px; }}
    .action-btn {{ display: flex; align-items: center; justify-content: center; gap: 10px; padding: 12px 18px; border-radius: 8px; text-decoration: none; font-size: 14px; font-weight: bold; transition: all 0.2s; cursor: pointer; text-align: center; }}
    .btn-gmail {{ background: #ea4335; color: #ffffff; }}
    .btn-gmail:hover {{ background: #d93025; transform: translateY(-1px); }}
    .btn-reddit {{ background: #ff4500; color: #ffffff; }}
    .btn-reddit:hover {{ background: #e03d00; transform: translateY(-1px); }}
    .btn-discord {{ background: #5865f2; color: #ffffff; }}
    .btn-discord:hover {{ background: #4752c4; transform: translateY(-1px); }}
    .btn-mailto {{ background: #1e293b; color: #94a3b8; border: 1px solid #334155; font-size: 12px; }}
    .btn-mailto:hover {{ background: #334155; color: #ffffff; }}

    .contact-list {{ font-size: 13px; color: #cbd5e1; line-height: 1.8; }}
    .contact-list strong {{ color: #ffffff; }}
    .contact-list a {{ color: #38bdf8; text-decoration: none; font-weight: 600; }}
    .contact-list a:hover {{ text-decoration: underline; }}
    
    .payments {{ margin-top: 14px; padding-top: 14px; border-top: 1px solid #1e293b; font-size: 12px; color: #94a3b8; }}
    .payments strong {{ color: #cbd5e1; }}

    .footer {{ text-align: center; font-size: 11px; color: #475569; margin-top: 20px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="badge">🛡️ OFFICIAL PURCHASE PORTAL</div>
      <h1>ApexClash <span>Pro</span></h1>
      <p class="subtitle">Instant Cryptographic Key Delivery • PayPal, Crypto, UPI & Cards Accepted</p>
    </div>

    <div class="card">
      <h2>🔑 1. Your Hardware Device ID</h2>
      <p style="font-size: 12px; color: #94a3b8; margin-bottom: 10px;">
        This identifier binds your license securely to your PC. Provide this ID when purchasing:
      </p>
      <div class="hw-box">
        <div class="hw-code" id="hw-val">{encoded_hw}</div>
        <button class="copy-btn" onclick="copyHw()">📋 Copy ID</button>
      </div>
      <div class="copy-feedback" id="copy-fb"></div>
    </div>

    <div class="card">
      <h2>💎 2. Access Passes & Official Pricing</h2>
      <div class="pricing-grid">
        <div class="tier-card">
          <div class="tier-badge blue">Weekly</div>
          <div class="tier-title">Weekly Pass</div>
          <div class="tier-price">$1.00</div>
          <div class="tier-sub">7 Days Access</div>
        </div>
        <div class="tier-card featured">
          <div class="tier-badge green">Popular</div>
          <div class="tier-title">Monthly Pass</div>
          <div class="tier-price">$3.00</div>
          <div class="tier-sub">30 Days Access</div>
        </div>
        <div class="tier-card">
          <div class="tier-badge blue">Annual</div>
          <div class="tier-title">Annual Pass</div>
          <div class="tier-price">$10.00</div>
          <div class="tier-sub">365 Days Access</div>
        </div>
        <div class="tier-card vip">
          <div class="tier-badge gold">Best Value</div>
          <div class="tier-title">Lifetime VIP</div>
          <div class="tier-price">$15.00</div>
          <div class="tier-sub">Permanent Access</div>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>🚀 3. Contact Developer for Instant Key Delivery</h2>
      <p style="font-size: 12px; color: #94a3b8; margin-bottom: 16px;">
        Click any button below to reach the developer directly with your Device ID pre-filled:
      </p>
      <div class="btn-row">
        <a class="action-btn btn-gmail" href="{gmail_url}" target="_blank">
          📧 Open in Gmail (Web Browser)
        </a>
        <a class="action-btn btn-reddit" href="{reddit_msg_url}" target="_blank">
          💬 Send Direct Message on Reddit (u/{CONTACT_REDDIT})
        </a>
        <a class="action-btn btn-discord" href="https://discord.com/app" target="_blank" onclick="copyDiscord();">
          💬 Open Discord (Developer: {CONTACT_DISCORD})
        </a>
        <a class="action-btn btn-mailto" href="{mailto_url}">
          ✉️ Open in Default Mail Client (mailto:)
        </a>
      </div>

      <div class="payments">
        <strong>Accepted Payment Methods:</strong> PayPal, UPI, Crypto (USDT, BTC, LTC, ETH), Credit / Debit Cards.<br>
        <strong>Direct Contacts:</strong> Email: <a href="mailto:{CONTACT_EMAIL}" style="color: #38bdf8;">{CONTACT_EMAIL}</a> | Discord: <strong style="color: #22c55e;">{CONTACT_DISCORD}</strong> | Reddit: <strong style="color: #f59e0b;">u/{CONTACT_REDDIT}</strong>
      </div>
    </div>

    <div class="footer">
      ApexClash Pro • Offline Cryptographic Licensing Suite • All rights reserved
    </div>
  </div>

  <script>
    function copyHw() {{
      const txt = document.getElementById('hw-val').innerText.trim();
      navigator.clipboard.writeText(txt).then(() => {{
        const fb = document.getElementById('copy-fb');
        fb.innerText = '✓ Device ID copied to clipboard!';
        setTimeout(() => {{ fb.innerText = ''; }}, 3000);
      }}).catch(() => {{
        alert('Device ID: ' + txt);
      }});
    }}
    function copyDiscord() {{
      navigator.clipboard.writeText('{CONTACT_DISCORD}').then(() => {{
        alert('Discord ID "{CONTACT_DISCORD}" copied to clipboard! Message this user on Discord to buy your key.');
      }});
    }}
  </script>
</body>
</html>
"""


def open_purchase_portal(machine_id: str, selected_tier: str = "Monthly ($3/mo)") -> str:
    """Write checkout page to disk and open it in the user's default browser.

    Returns the file URI that was opened.
    """
    app_data = get_user_app_data_dir()
    ensure_dir(app_data)
    html_file = app_data / "purchase.html"
    content = generate_purchase_html(machine_id, selected_tier)
    html_file.write_text(content, encoding="utf-8")
    
    file_uri = html_file.resolve().as_uri()
    webbrowser.open(file_uri)
    return file_uri
