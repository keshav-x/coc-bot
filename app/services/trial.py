"""Trial runtime wallet for Clash Auto Loot.

Calls POST /v1/trial/heartbeat on the license API server.
elapsed_seconds=0 is a read-only probe (no debit).
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from .license import HardwareFingerprint

logger = logging.getLogger(__name__)

_API_BASE = ""
_HEARTBEAT_URL = ""

TRIAL_TOTAL_SECONDS: int = 7200
TRIAL_HEARTBEAT_INTERVAL_MS: int = 60000
_LOCAL_ELAPSED_CAP: int = 125


class TrialResult:
    def __init__(
        self,
        ok: bool = False,
        remaining_seconds: int = 0,
        used_seconds: int = 0,
        reason: str = "",
    ):
        self.ok = ok
        self.remaining_seconds = remaining_seconds
        self.used_seconds = used_seconds
        self.reason = reason

    def allowed(self) -> bool:
        return bool(self.ok and self.remaining_seconds > 0)


from app.services.crypto_license import LocalTrialVault, TRIAL_TOTAL_SECONDS


class TrialClient:
    def __init__(self, api_base: str = _API_BASE):
        self._api_base = api_base

    def heartbeat(self, elapsed_seconds: int = 0, bot_version: str = "") -> TrialResult:
        fp = HardwareFingerprint.compute()
        allowed, remaining, used = LocalTrialVault.tick(fp, elapsed_seconds)
        return TrialResult(
            ok=allowed,
            remaining_seconds=remaining,
            used_seconds=used,
            reason="" if allowed else "Trial period expired",
        )


_client: Optional[TrialClient] = None


def get_trial_client() -> TrialClient:
    global _client
    if _client is None:
        _client = TrialClient()
    return _client


def fetch_trial_status(bot_version: str = "") -> TrialResult:
    try:
        return get_trial_client().heartbeat(elapsed_seconds=0, bot_version=bot_version)
    except requests.RequestException as exc:
        logger.warning("Trial status fetch failed: %s", exc)
        return TrialResult(ok=False, remaining_seconds=0, reason="network_error")
    except Exception as exc:
        logger.warning("Trial status unexpected error: %s", exc)
        return TrialResult(ok=False, remaining_seconds=0, reason="error")


def send_trial_heartbeat(elapsed_seconds: int, bot_version: str = "") -> TrialResult:
    try:
        return get_trial_client().heartbeat(
            elapsed_seconds=elapsed_seconds, bot_version=bot_version
        )
    except requests.RequestException as exc:
        logger.warning("Trial heartbeat failed: %s", exc)
        return TrialResult(ok=False, remaining_seconds=0, reason="network_error")
    except Exception as exc:
        logger.warning("Trial heartbeat unexpected error: %s", exc)
        return TrialResult(ok=False, remaining_seconds=0, reason="error")
