"""Discord Webhook notification service for Clash AutoLoot.

Dispatches asynchronous rich embed notifications to a user-configured Discord channel:
- Raid completion summary (Gold, Elixir, Dark Elixir, Skips).
- Bot start / stop events.
- Anti-Ban break notifications.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import requests

from app.utils.common import ensure_dir, get_user_app_data_dir
from app.utils.logger import setup_logger

logger = setup_logger("Webhook")

WEBHOOK_CONFIG_FILENAME = "webhook.json"


@dataclass
class WebhookConfig:
    enabled: bool = False
    url: str = ""
    notify_on_raid: bool = True
    notify_on_break: bool = True
    notify_on_stop: bool = True


def get_webhook_config_path() -> Path:
    dest = get_user_app_data_dir() / WEBHOOK_CONFIG_FILENAME
    ensure_dir(dest.parent)
    return dest


def load_webhook_config() -> WebhookConfig:
    path = get_webhook_config_path()
    if not path.is_file():
        return WebhookConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return WebhookConfig()
        return WebhookConfig(
            enabled=bool(raw.get("enabled", False)),
            url=str(raw.get("url", "")).strip(),
            notify_on_raid=bool(raw.get("notify_on_raid", True)),
            notify_on_break=bool(raw.get("notify_on_break", True)),
            notify_on_stop=bool(raw.get("notify_on_stop", True)),
        )
    except Exception as e:
        logger.warning(f"Could not load webhook config: {e}")
        return WebhookConfig()


def save_webhook_config(config: WebhookConfig) -> None:
    path = get_webhook_config_path()
    try:
        path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not save webhook config: {e}")


def _send_async(payload: dict) -> None:
    cfg = load_webhook_config()
    if not cfg.enabled or not cfg.url:
        return

    def worker():
        try:
            requests.post(cfg.url, json=payload, timeout=8)
        except Exception as e:
            logger.debug(f"Webhook dispatch failed: {e}")

    threading.Thread(target=worker, daemon=True, name="WebhookWorker").start()


def notify_bot_started(plan_summary: str) -> None:
    cfg = load_webhook_config()
    if not cfg.enabled:
        return
    payload = {
        "embeds": [
            {
                "title": "⚔️ ApexClash Pro Started",
                "description": f"Bot initiated with plan: **{plan_summary}**",
                "color": 0x0EA5E9,
            }
        ]
    }
    _send_async(payload)


def notify_raid_complete(gold: int, elixir: int, dark_elixir: int, skips: int) -> None:
    cfg = load_webhook_config()
    if not cfg.enabled or not cfg.notify_on_raid:
        return
    payload = {
        "embeds": [
            {
                "title": "💰 Raid Completed Successfully",
                "color": 0x22C55E,
                "fields": [
                    {"name": "Gold Looted", "value": f"{gold:,}", "inline": True},
                    {"name": "Elixir Looted", "value": f"{elixir:,}", "inline": True},
                    {"name": "Dark Elixir", "value": f"{dark_elixir:,}", "inline": True},
                    {"name": "Bases Skipped", "value": str(skips), "inline": True},
                ],
            }
        ]
    }
    _send_async(payload)


def notify_break(duration_mins: int) -> None:
    cfg = load_webhook_config()
    if not cfg.enabled or not cfg.notify_on_break:
        return
    payload = {
        "embeds": [
            {
                "title": "☕ Anti-Ban Human Break",
                "description": f"Bot is taking a natural {duration_mins}-minute break to simulate human player rest.",
                "color": 0xF59E0B,
            }
        ]
    }
    _send_async(payload)


def notify_bot_stopped(reason: str = "User stopped") -> None:
    cfg = load_webhook_config()
    if not cfg.enabled or not cfg.notify_on_stop:
        return
    payload = {
        "embeds": [
            {
                "title": "🛑 ApexClash Pro Stopped",
                "description": f"Session ended. Reason: **{reason}**",
                "color": 0xEF4444,
            }
        ]
    }
    _send_async(payload)
