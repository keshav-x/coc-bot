"""License key validation for Clash Auto Loot.

Components
----------
HardwareFingerprint  - Stable 32-hex machine ID (Windows MachineGuid only).
LicenseClient        - HTTP calls to the validation API.
LicenseState         - Enum of all possible client states.
LicenseManager       - State machine + background scheduler. Singleton.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import threading
import time
from datetime import date, datetime
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional

if sys.platform == "win32":
    try:
        import winreg
    except ImportError:
        winreg = None
else:
    winreg = None

import requests

logger = logging.getLogger(__name__)

_API_BASE = ""
_VALIDATE_URL = ""
_RECHECK_INTERVAL_S = 10800
_RETRY_INTERVAL_S = 30
_RETRY_MAX_S = 900

# URL of GitHub raw file containing revoked keys or transaction IDs (one per line).
import os as _os
_REVOCATION_GIST_URL: str = _os.environ.get(
    "APEXCLASH_REVOCATION_URL",
    "https://raw.githubusercontent.com/keshav-x/coc-bot/main/docs/revoked.txt",
)
_REVOCATION_CACHE: set[str] = set()
_REVOCATION_CACHE_TS: float = 0.0
_REVOCATION_CACHE_TTL_S: int = 1800  # re-download at most once per 30 minutes


class LicenseState(Enum):
    EMPTY = auto()
    VALIDATING = auto()
    VALID = auto()
    INVALID = auto()
    STALE = auto()
    RETRYING = auto()
    UNREACHABLE = auto()


_REASON_MESSAGES: dict[str, str] = {
    "ok": "Licensed.",
    "not_found": "Verification failed. Please check your license key or Transaction ID / UTR.",
    "revoked": "This license key or transaction ID has been revoked by the developer.",
    "expired": "This subscription license has expired. Renew your pass or purchase a lifetime key.",
    "machine_mismatch": "This license key is already activated on another machine.",
    "invalid_format": "Invalid format. Enter a CAL- key, TXN- key, or your 12-digit PhonePe UTR / PayPal Txn ID.",
    "network_unreachable": "Could not reach the verification service. Please check your internet connection.",
    "empty": "Please enter your license key or Transaction ID, then click Check Key.",
}


class HardwareFingerprint:
    _cache: Optional[str] = None

    @classmethod
    def compute(cls) -> str:
        if cls._cache is not None:
            return cls._cache
        cls._cache = cls._build()
        return cls._cache

    @classmethod
    def _build(cls) -> str:
        digest = hashlib.sha256(cls._machine_guid().encode()).hexdigest()[:32]
        logger.debug("Hardware fingerprint computed (first 8: %s...)", digest[:8])
        return digest

    @classmethod
    def _machine_guid(cls) -> str:
        if sys.platform == "win32" and winreg is not None:
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Cryptography",
                )
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
                winreg.CloseKey(key)
                return str(value).strip()
            except Exception:
                pass

        # Linux / macOS machine-id fallbacks
        for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                p = Path(path)
                if p.is_file():
                    mid = p.read_text(encoding="utf-8").strip()
                    if mid:
                        return mid
            except Exception:
                pass

        try:
            import uuid
            return str(uuid.getnode())
        except Exception:
            return "<unavailable>"


from app.services.crypto_license import CryptoLicenseEngine


def _check_revocation(key: str) -> bool:
    """Downloads the GitHub raw revocation list and checks if key or txn_id is revoked.

    Caches the list for _REVOCATION_CACHE_TTL_S seconds.
    Silently returns False on any network error (offline-first principle).
    """
    global _REVOCATION_CACHE, _REVOCATION_CACHE_TS

    if not _REVOCATION_GIST_URL:
        return False

    now = time.monotonic()
    if now - _REVOCATION_CACHE_TS > _REVOCATION_CACHE_TTL_S or not _REVOCATION_CACHE:
        try:
            resp = requests.get(_REVOCATION_GIST_URL, timeout=5)
            if resp.status_code == 200:
                _REVOCATION_CACHE = {
                    line.strip().upper()
                    for line in resp.text.splitlines()
                    if line.strip() and not line.startswith("#")
                }
                _REVOCATION_CACHE_TS = now
                logger.debug(
                    "Revocation list refreshed: %d revoked item(s)", len(_REVOCATION_CACHE)
                )
        except Exception as exc:
            logger.debug("Revocation list fetch skipped (offline?): %s", exc)

    norm = key.strip().upper()
    if norm in _REVOCATION_CACHE:
        return True

    # If it is a TXN- key, check the embedded transaction id
    if norm.startswith("TXN-"):
        parts = norm.split("-")
        if len(parts) >= 4 and parts[3] in _REVOCATION_CACHE:
            return True

    return False


def _get_activation_webhook_url() -> str:
    url = _os.environ.get("APEXCLASH_WEBHOOK_URL", "").strip()
    if url:
        return url
    for candidate in (
        Path(__file__).resolve().parent.parent.parent / "sales_bot" / "config.json",
        Path("sales_bot/config.json"),
    ):
        try:
            if candidate.is_file():
                data = json.loads(candidate.read_text(encoding="utf-8"))
                val = str(data.get("activation_webhook_url", "")).strip()
                if val and val.startswith("http"):
                    return val
        except Exception:
            pass
    return ""


def _get_telegram_config() -> tuple[str, str]:
    token = _os.environ.get("APEXCLASH_TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = _os.environ.get("APEXCLASH_TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        return token, chat_id

    for candidate in (
        Path(__file__).resolve().parent.parent.parent / "sales_bot" / "config.json",
        Path("sales_bot/config.json"),
    ):
        try:
            if candidate.is_file():
                data = json.loads(candidate.read_text(encoding="utf-8"))
                cfg_token = str(data.get("telegram_bot_token", "")).strip()
                cfg_chat = str(data.get("telegram_chat_id", "")).strip()
                if cfg_token and cfg_chat:
                    return cfg_token, cfg_chat
        except Exception:
            pass
    return "", ""


def send_activation_alert(
    txn_id: str,
    hw_id: str,
    tier: str,
    license_key: str,
    provider: str = "",
) -> None:
    webhook_url = _get_activation_webhook_url()
    tg_token, tg_chat = _get_telegram_config()

    if not webhook_url and not (tg_token and tg_chat):
        return

    def _worker():
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        prov_str = provider.upper() if provider else "UPI / PayPal"

        # 1. Send Discord Webhook Alert if configured
        if webhook_url:
            try:
                content = (
                    f"🚨 **New ApexClash Pro Activation Alert!**\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"• **UTR / Txn ID:** `{txn_id}`\n"
                    f"• **Generated Key:** `{license_key}`\n"
                    f"• **Payment Method:** {prov_str}\n"
                    f"• **Plan Activated:** {tier}\n"
                    f"• **Device ID:** `{hw_id}`\n"
                    f"• **Timestamp:** {now_str}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"👉 **Action Required:** Check your PhonePe / PayPal statement.\n"
                    f"• If received: ✅ Do nothing (valid customer).\n"
                    f"• If UNPAID (fake ID): ❌ Run:\n"
                    f"  `python revoke.py {txn_id} \"fake payment\"` & `git push`"
                )
                payload = {
                    "content": content,
                    "username": "ApexClash Security Bot",
                }
                requests.post(webhook_url, json=payload, timeout=5)
            except Exception as exc:
                logger.debug("Failed to send Discord webhook alert: %s", exc)

        # 2. Send Telegram Alert if configured
        if tg_token and tg_chat:
            try:
                tg_text = (
                    f"🚨 <b>New ApexClash Pro Activation!</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💳 <b>UTR / Txn ID:</b> <code>{txn_id}</code>\n"
                    f"🔑 <b>Generated Key:</b> <code>{license_key}</code>\n"
                    f"📦 <b>Plan:</b> {tier}\n"
                    f"📱 <b>Method:</b> {prov_str}\n"
                    f"💻 <b>Device ID:</b> <code>{hw_id}</code>\n"
                    f"⏰ <b>Time:</b> {now_str}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👉 <b>Action:</b> Check PhonePe / PayPal.\n"
                    f"• If received: ✅ Valid payment.\n"
                    f"• If UNPAID (fake ID): ❌ Revoke:\n"
                    f"<code>python revoke.py {txn_id} fake</code>"
                )
                tg_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
                requests.post(
                    tg_url,
                    json={
                        "chat_id": tg_chat,
                        "text": tg_text,
                        "parse_mode": "HTML",
                    },
                    timeout=5,
                )
            except Exception as exc:
                logger.debug("Failed to send Telegram alert: %s", exc)

    threading.Thread(target=_worker, daemon=True, name="ActivationAlertWorker").start()


class LicenseClient:
    def __init__(self, api_base: str = _API_BASE) -> None:
        self._api_base = api_base

    def validate(self, license_key: str, bot_version: str = "1.3.1") -> dict:
        """Validates license_key cryptographically via CryptoLicenseEngine.

        Steps
        ─────
        1. Accepts CAL- keys, TXN- keys, or raw 12-digit UTRs / PayPal Transaction IDs directly.
        2. Offline Ed25519 signature + expiry check (always).
        3. Revocation check against remote revoked list.

        Returns parsed dict matching {"ok": bool, "valid": bool, "expires_at": str, "tier": str}
        or {"ok": False, "valid": False, "reason": str}.
        """
        normalized_key = license_key.strip()
        if not normalized_key:
            return {"ok": False, "valid": False, "reason": "empty"}

        hw_id = HardwareFingerprint.compute()

        # If user directly entered a raw Transaction ID / UTR instead of a formatted key
        from app.services.crypto_license import (
            TIER_MONTHLY,
            generate_txn_license,
            is_known_test_id,
            validate_txn_id,
        )

        is_txn, clean_id, provider = validate_txn_id(normalized_key)
        if is_txn and not normalized_key.startswith("CAL-") and not normalized_key.startswith("TXN-"):
            if is_known_test_id(clean_id):
                return {"ok": False, "valid": False, "reason": "not_found"}
            # Auto-mint a 30-day Monthly Pass bound to this machine
            normalized_key = generate_txn_license(
                clean_id, tier=TIER_MONTHLY, machine_id=hw_id, days=30
            )
            # Dispatch instant Discord alert to developer
            send_activation_alert(clean_id, hw_id, "Monthly Pass (₹249 / $4.99)", normalized_key, provider)

        saved_bound = load_saved_bound_machine()
        res = CryptoLicenseEngine.verify_key(
            key=normalized_key,
            current_machine_id=hw_id,
            saved_bound_machine=saved_bound,
        )

        if not res.is_valid:
            return {"ok": False, "valid": False, "reason": res.reason}

        # ── Revocation check (soft, offline-first) ─────────────────────────────
        if _check_revocation(normalized_key):
            logger.warning("Key or Transaction ID is in revocation list — marking INVALID.")
            return {"ok": False, "valid": False, "reason": "revoked"}

        # Save machine binding
        save_key(normalized_key, bound_machine=hw_id)
        return {
            "ok": True,
            "valid": True,
            "expires_at": res.expiry_date_str if res.expiry_date_str else "Never",
            "tier": res.tier,
            "license_key": normalized_key,
        }

    def unpair(self, license_key: str, bot_version: str = "1.3.1") -> dict:
        """Unpairs the machine from this key locally."""
        clear_saved_key()
        return {"ok": True}

    def portal(self, license_key: str, bot_version: str = "1.3.1") -> dict:
        """Returns the checkout / billing portal URL."""
        from app.ui.qt._constants import SUBSCRIBE_CHECKOUT_URL
        return {"ok": True, "url": SUBSCRIBE_CHECKOUT_URL}


def _key_file() -> Path:
    from app.utils.common import ensure_dir, get_user_app_data_dir

    d = get_user_app_data_dir()
    ensure_dir(d)
    return d / "license.json"


def load_saved_key() -> str:
    try:
        data = json.loads(_key_file().read_text(encoding="utf-8"))
        return str(data.get("license_key", "")).strip()
    except Exception:
        return ""


def load_saved_bound_machine() -> Optional[str]:
    try:
        data = json.loads(_key_file().read_text(encoding="utf-8"))
        val = data.get("bound_machine")
        return str(val).strip() if val else None
    except Exception:
        return None


def clear_saved_key() -> None:
    try:
        path = _key_file()
        if path.exists():
            path.unlink()
    except OSError as exc:
        logger.warning("Could not remove license file: %s", exc)


def save_key(key: str, bound_machine: Optional[str] = None) -> None:
    try:
        normalized = key.strip()
        payload = {
            "license_key": normalized,
            "bound_machine": bound_machine or HardwareFingerprint.compute(),
            "saved_at": int(time.time()),
        }
        _key_file().write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Could not save license key: %s", exc)


StateCallback = Callable[[LicenseState, str], None]


class LicenseManager:
    """Singleton license state machine with background scheduler.

Thread-safety: state transitions happen on a background daemon thread.
UI callbacks are invoked from that thread; GUI code must marshal via
``app.after(0, ...)`` when updating widgets.
"""

    def __init__(self, bot_version: str = "1.3.1") -> None:
        self._bot_version = bot_version
        self._client = LicenseClient()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._recheck_event = threading.Event()
        self._state = LicenseState.EMPTY
        self._reason = "empty"
        self._license_key = ""
        self._expires_at_raw = None
        self._retry_start = 0.0
        self._on_state_change = None
        self._scheduler_thread = None

    @property
    def state(self) -> LicenseState:
        with self._lock:
            return self._state

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

    @property
    def user_message(self) -> str:
        with self._lock:
            if self._state == LicenseState.VALID:
                return "Licensed."
            return _REASON_MESSAGES.get(self._reason, "License key is invalid.")

    def license_expiry_subcaption(self) -> str:
        """UI line under 'Licensed.': 'Expires on: YYYY-MM-DD' or 'Never' (lifetime). Empty if not VALID."""
        with self._lock:
            if self._state != LicenseState.VALID:
                return ""
            raw = self._expires_at_raw
        if raw is None:
            return "Never"
        s = str(raw).strip()
        if not s:
            return "Never"
        try:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            if len(s) >= 10 and s[4] == "-" and s[7] == "-" and "T" not in s[:10]:
                d = date.fromisoformat(s[:10])
            else:
                d = datetime.fromisoformat(s).date()
            return f"Expires on: {d.isoformat()}"
        except Exception:
            if len(s) >= 10 and s[4] == "-" and s[7] == "-":
                return f"Expires on: {s[:10]}"
            return "Never"

    def set_on_state_change(self, callback: StateCallback) -> None:
        self._on_state_change = callback

    def start(self, license_key: str) -> None:
        """Load a key and start the background scheduler.

Triggers an immediate validation in the background thread.
"""
        notify_empty = False
        with self._lock:
            self._license_key = license_key.strip()
            if not self._license_key:
                self._apply_state_locked(LicenseState.EMPTY, "empty")
                notify_empty = True
            else:
                self._state = LicenseState.VALIDATING
                self._reason = ""
        if notify_empty:
            self._notify_state_change(LicenseState.EMPTY, "empty")
        if self._scheduler_thread is None or not self._scheduler_thread.is_alive():
            self._stop_event.clear()
            self._scheduler_thread = threading.Thread(
                target=self._scheduler_loop,
                daemon=True,
                name="LicenseScheduler",
            )
            self._scheduler_thread.start()
        else:
            self._recheck_event.set()

    def recheck(self, new_key: Optional[str] = None) -> None:
        """Trigger an immediate re-validation from the UI thread.

If ``new_key`` is provided, updates working key only; ``license.json`` is written
after the server confirms ``valid`` (see ``_do_validate``). Empty key clears disk.
"""
        if new_key is not None:
            stripped = new_key.strip()
            if not stripped:
                clear_saved_key()
                with self._lock:
                    self._license_key = ""
                    self._apply_state_locked(LicenseState.EMPTY, "empty")
                self._notify_state_change(LicenseState.EMPTY, "empty")
                self._recheck_event.set()
                if self._scheduler_thread is None or not self._scheduler_thread.is_alive():
                    self.start("")
                return
            with self._lock:
                self._license_key = stripped
                self._state = LicenseState.VALIDATING
                self._reason = ""
            self._recheck_event.set()
            if self._scheduler_thread is None or not self._scheduler_thread.is_alive():
                self.start(self._license_key)
            return
        self._recheck_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._recheck_event.set()

    def mark_stale(self) -> None:
        """Called when user edits the key field; dot goes red until Check Key validates."""
        notify = None
        with self._lock:
            if self._state == LicenseState.VALID:
                self._apply_state_locked(LicenseState.STALE, "stale")
                notify = (LicenseState.STALE, "stale")
        if notify:
            self._notify_state_change(*notify)

    def try_unpair(self, license_key: str) -> tuple[bool, str]:
        """Remove this machine's hardware bind on the server. Returns (success, reason_code_or_empty)."""
        stripped = license_key.strip()
        if not stripped:
            return (False, "empty")
        try:
            out = self._client.unpair(stripped, self._bot_version)
            if bool(out.get("ok")):
                return (True, "")
            return (False, str(out.get("reason", "failed")))
        except requests.RequestException as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code == 422:
                return (False, "invalid_format")
            logger.warning("License unpair request failed: %s", exc)
            return (False, "network_unreachable")

    def try_portal_url(self, license_key: str) -> tuple[str, str]:
        """Ask the server for a Stripe customer-portal link. Returns (url, reason_code_or_empty)."""
        stripped = license_key.strip()
        if not stripped:
            return ("", "empty")
        try:
            out = self._client.portal(stripped, self._bot_version)
            url = str(out.get("url") or "")
            if bool(out.get("ok")) and url:
                return (url, "")
            return ("", str(out.get("reason", "failed")))
        except requests.RequestException as exc:
            resp = getattr(exc, "response", None)
            if resp is not None and resp.status_code == 422:
                return ("", "invalid_format")
            logger.warning("Billing portal request failed: %s", exc)
            return ("", "network_unreachable")

    def _apply_state_locked(
        self,
        state: LicenseState,
        reason: str,
        expires_at: Optional[object] = None,
    ) -> None:
        """Mutate state only. Caller must hold :attr:`_lock`; do not call UI from here."""
        self._state = state
        self._reason = reason
        if state == LicenseState.VALID:
            self._expires_at_raw = expires_at
        elif state != LicenseState.STALE:
            self._expires_at_raw = None

    def _notify_state_change(self, state: LicenseState, reason: str) -> None:
        """Invoke UI callback **without** holding :attr:`_lock` (avoids Tk/main-thread deadlock)."""
        cb = self._on_state_change
        if not cb:
            return
        try:
            cb(state, reason)
        except Exception:
            return

    def _do_validate(self) -> None:
        with self._lock:
            key = self._license_key
        if not key:
            with self._lock:
                self._apply_state_locked(LicenseState.EMPTY, "empty")
            self._notify_state_change(LicenseState.EMPTY, "empty")
            return

        with self._lock:
            self._state = LicenseState.VALIDATING
        if self._on_state_change:
            try:
                self._on_state_change(LicenseState.VALIDATING, "")
            except Exception:
                pass

        try:
            result = self._client.validate(key, self._bot_version)
            self._retry_start = 0.0
            if result.get("valid") or result.get("ok"):
                with self._lock:
                    resolved_key = result.get("license_key") or self._license_key.strip()
                    self._license_key = resolved_key
                    self._apply_state_locked(
                        LicenseState.VALID,
                        "ok",
                        expires_at=result.get("expires_at"),
                    )
                save_key(resolved_key)
                self._notify_state_change(LicenseState.VALID, "ok")
                return
            reason = result.get("reason", "invalid")
            with self._lock:
                self._apply_state_locked(LicenseState.INVALID, reason)
            self._notify_state_change(LicenseState.INVALID, reason)
            return
        except requests.RequestException as exc:
            if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code == 422:
                logger.warning("License validation rejected (422): %s", (exc.response.text or "")[:400])
                with self._lock:
                    self._apply_state_locked(LicenseState.INVALID, "invalid_format")
                self._notify_state_change(LicenseState.INVALID, "invalid_format")
                return
            logger.warning("License validation network error: %s", exc)
            now = time.monotonic()
            if self._retry_start == 0.0:
                self._retry_start = now
            elapsed = now - self._retry_start
            if elapsed >= _RETRY_MAX_S:
                with self._lock:
                    self._apply_state_locked(LicenseState.UNREACHABLE, "network_unreachable")
                self._notify_state_change(LicenseState.UNREACHABLE, "network_unreachable")
                return
            with self._lock:
                self._apply_state_locked(LicenseState.RETRYING, "network_retrying")
            self._notify_state_change(LicenseState.RETRYING, "network_retrying")
            return

    def _scheduler_loop(self) -> None:
        self._do_validate()
        while not self._stop_event.is_set():
            state = self.state
            if state == LicenseState.RETRYING:
                wait = _RETRY_INTERVAL_S
            else:
                wait = _RECHECK_INTERVAL_S
                self._retry_start = 0.0
            self._recheck_event.wait(timeout=wait)
            self._recheck_event.clear()
            if self._stop_event.is_set():
                return
            current_state = self.state
            if current_state == LicenseState.STALE:
                continue
            self._do_validate()
