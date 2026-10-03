"""
Revocation service for ApexClash Pro.

Stores revoked keys in a local JSON file and optionally pushes the list
to a GitHub Gist so the in-app license validator can download it on each
revalidation cycle and block revoked keys — even though keys are signed
offline with Ed25519 (and thus cannot be "un-signed").

Flow
────
1. Admin runs /revoke <order_id> in Discord.
2. The order's license_key is added to revoked_keys.json.
3. The list is pushed to the configured GitHub Gist (if GITHUB_TOKEN is set).
4. On the user's PC, the LicenseClient fetches the Gist URL on each
   3-hour revalidation cycle.  If the key appears in the list, status → REVOKED.

revoked_keys.json schema
────────────────────────
{
  "ACB-XXXXX": {
    "key":        "CAL-M30-...",
    "reason":     "fraudulent_txn",
    "revoked_at": 1700000000
  },
  ...
}
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import requests as _requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False

logger = logging.getLogger("RevocationService")

REVOKED_DB_PATH = Path(__file__).resolve().parent / "revoked_keys.json"


# ── Local store ────────────────────────────────────────────────────────────────

def load_revoked() -> Dict[str, Any]:
    if REVOKED_DB_PATH.is_file():
        try:
            with open(REVOKED_DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_revoked(data: Dict[str, Any]) -> None:
    try:
        with open(REVOKED_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as exc:
        logger.error("Could not save revoked_keys.json: %s", exc)


def revoke_order(order_id: str, license_key: str, reason: str = "admin_revoke") -> None:
    """Add an order's key to the revocation database."""
    revoked = load_revoked()
    revoked[order_id] = {
        "key": license_key,
        "reason": reason,
        "revoked_at": int(time.time()),
    }
    save_revoked(revoked)
    logger.info("Key revoked for order %s (reason: %s)", order_id, reason)


def is_key_revoked(license_key: str) -> bool:
    """Returns True if this key is in the local revocation database."""
    revoked = load_revoked()
    key_clean = license_key.strip()
    return any(entry.get("key", "").strip() == key_clean for entry in revoked.values())


def get_all_revoked_keys() -> list[str]:
    """Returns a plain list of all revoked key strings (for Gist publishing)."""
    revoked = load_revoked()
    return [entry["key"] for entry in revoked.values() if entry.get("key")]


# ── GitHub Gist publisher (optional) ─────────────────────────────────────────

def push_revocation_gist(
    gist_id: str,
    github_token: str,
    filename: str = "apexclash_revoked.txt",
) -> bool:
    """
    Updates a GitHub Gist with the current revocation list.
    The in-app license validator downloads this file on each revalidation cycle.

    Returns True on success, False on failure.
    """
    if not _HAS_REQUESTS:
        logger.warning("requests not installed — cannot push revocation Gist.")
        return False
    if not gist_id or not github_token:
        logger.debug("Gist ID or token not configured — skipping Gist push.")
        return False

    keys = get_all_revoked_keys()
    content = "\n".join(keys) if keys else "# No revoked keys yet\n"

    try:
        resp = _requests.patch(
            f"https://api.github.com/gists/{gist_id}",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
            },
            json={"files": {filename: {"content": content}}},
            timeout=10,
        )
        if resp.status_code in (200, 201):
            logger.info("Revocation Gist updated: %d revoked key(s)", len(keys))
            return True
        logger.error("Gist update failed %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.error("Gist push exception: %s", exc)
    return False
