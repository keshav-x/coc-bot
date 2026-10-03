"""Configuration loader for the ApexClash Pro Sales Bot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
EXAMPLE_CONFIG_PATH = Path(__file__).resolve().parent / "config.example.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "discord_bot_token": "YOUR_DISCORD_BOT_TOKEN_HERE",
    "admin_discord_id": 0,
    "phonepe_upi_id": "cockingkeshav@ybl",
    "payee_name": "ApexClash Pro",
    # paypal.me link used as direct payment link
    "paypal_me_url": "https://paypal.me/cockingkeshav",
    # Optional: PayPal Orders API (for 100% automated instantaneous PayPal capture)
    "paypal_client_id": "",
    "paypal_client_secret": "",
    "paypal_mode": "live",
    # Optional: Revocation synchronization via GitHub Gist
    # When you revoke an order in Discord, the bot automatically publishes the revoked key list to this Gist.
    # The desktop bot checks this Gist URL periodically to block blacklisted keys.
    "revocation_gist_id": "",
    "github_token": "",
    # Auto-revocation setting: set to True only if you want unconfirmed orders to auto-expire
    "auto_revoke_unconfirmed": False,
    "upi_approval_window_seconds": 1800,
    "pricing": {
        "weekly": {
            "name": "Weekly Pass",
            "tier_code": "W07",
            "days": 7,
            "inr": 99,
            "usd": 1.99,
            "description": "7 Days Full VIP Access",
        },
        "monthly": {
            "name": "Monthly Pass",
            "tier_code": "M30",
            "days": 30,
            "inr": 249,
            "usd": 4.99,
            "description": "30 Days Full VIP Access (Most Popular)",
        },
        "annual": {
            "name": "Annual Pass",
            "tier_code": "Y36",
            "days": 365,
            "inr": 799,
            "usd": 14.99,
            "description": "365 Days Access (Best Value)",
        },
        "lifetime": {
            "name": "Lifetime VIP",
            "tier_code": "LIFE",
            "days": 0,
            "inr": 1299,
            "usd": 24.99,
            "description": "Permanent VIP Access (Never Expires)",
        },
    },
}


def load_config() -> Dict[str, Any]:
    if CONFIG_PATH.is_file():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            return DEFAULT_CONFIG
    return DEFAULT_CONFIG


def save_example_config() -> None:
    if not EXAMPLE_CONFIG_PATH.is_file():
        with open(EXAMPLE_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
