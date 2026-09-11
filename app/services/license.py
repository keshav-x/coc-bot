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
import threading
import time
import winreg
from enum import Enum, auto
from pathlib import Path
from datetime import date, datetime
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

_API_BASE = "https://clashautoloot.duckdns.org"
_VALIDATE_URL = f"{_API_BASE}/v1/validate"
_RECHECK_INTERVAL_S = 10800
_RETRY_INTERVAL_S = 30
_RETRY_MAX_S = 900


class LicenseState(Enum):
    EMPTY = auto()
    VALIDATING = auto()
    VALID = auto()
    INVALID = auto()
    STALE = auto()
    RETRYING = auto()
    UNREACHABLE = auto()


_REASON_MESSAGES: dict[str, str] = {
    "not_found": "License key is invalid.",
    "revoked": "This license key has been revoked.",
    "expired": "This subscription license has expired. Renew your subscription or purchase a lifetime key.",
    "machine_mismatch": "This license key is already activated on another machine.",
    "invalid_format": "License key format is invalid. Use the exact key from your email (CLASH-…, letters and digits only).",
    "network_unreachable": "Could not reach the license server. Please check your internet connection.",
    "empty": "Please enter a license key and click Check Key.",
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
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
            )
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            winreg.CloseKey(key)
            return str(value).strip()
        except Exception:
            return "<unavailable>"


from app.services.crypto_license import CryptoLicenseEngine


class LicenseClient:
    def __init__(self, api_base: str = _API_BASE) -> None:
        self._api_base = api_base

    def validate(self, license_key: str, bot_version: str = "1.0.0") -> dict:
        """Validates license_key cryptographically via CryptoLicenseEngine.
        Returns parsed dict matching {"ok": bool, "expires_at": str, "tier": str}
        or {"ok": False, "reason": str}.
        """
        normalized_key = license_key.strip().upper()
        if not normalized_key:
            return {"ok": False, "reason": "empty"}

        hw_id = HardwareFingerprint.compute()
        saved_bound = load_saved_bound_machine()
        res = CryptoLicenseEngine.verify_key(
            key=normalized_key,
            current_machine_id=hw_id,
            saved_bound_machine=saved_bound,
        )

        if not res.is_valid:
            return {"ok": False, "reason": res.reason}

        # Save machine binding
        save_key(normalized_key, bound_machine=hw_id)
        return {
            "ok": True,
            "expires_at": res.expiry_date_str if res.expiry_date_str else "Never",
            "tier": res.tier,
        }

    def unpair(self, license_key: str, bot_version: str = "1.0.0") -> dict:
        """Unpairs the machine from this key locally."""
        clear_saved_key()
        return {"ok": True}

    def portal(self, license_key: str, bot_version: str = "1.0.0") -> dict:
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
        return str(data.get("license_key", "")).strip().upper()
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
        normalized = key.strip().upper()
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

    def __init__(self, bot_version: str = "1.0.0") -> None:
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
        return _REASON_MESSAGES.get(self.reason, "License key is invalid.")

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
            self._license_key = license_key.strip().upper()
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
            stripped = new_key.strip().upper()
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
        stripped = license_key.strip().upper()
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
        stripped = license_key.strip().upper()
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
            if result.get("valid"):
                with self._lock:
                    persisted = self._license_key.strip().upper()
                    self._apply_state_locked(
                        LicenseState.VALID,
                        "ok",
                        expires_at=result.get("expires_at"),
                    )
                save_key(persisted)
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
