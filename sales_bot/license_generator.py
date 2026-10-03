"""License Key Generation helper for sales and automation."""

from __future__ import annotations

import sys
from pathlib import Path

SALES_BOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SALES_BOT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.crypto_license import (
    TIER_ANNUAL,
    TIER_LIFETIME,
    TIER_MONTHLY,
    TIER_WEEKLY,
    CryptoLicenseEngine,
)

PRIVATE_KEY_PATH = PROJECT_ROOT / "private_key.pem"


def get_private_key() -> str:
    if not PRIVATE_KEY_PATH.is_file():
        raise FileNotFoundError(f"Private signing key not found at {PRIVATE_KEY_PATH}")
    return PRIVATE_KEY_PATH.read_text(encoding="utf-8").strip()


def generate_license_for_tier(tier_key: str, machine_id: str | None = None) -> str:
    """Generates a valid Ed25519 license key.
    If machine_id is None, generates a UNIV key that binds to the first PC on launch.
    """
    priv_key = get_private_key()
    tier_map = {
        "weekly": (TIER_WEEKLY, 7),
        "monthly": (TIER_MONTHLY, 30),
        "annual": (TIER_ANNUAL, 365),
        "lifetime": (TIER_LIFETIME, 0),
    }
    tier_code, days = tier_map.get(tier_key.lower(), (TIER_MONTHLY, 30))
    return CryptoLicenseEngine.generate_key(
        private_key_pem=priv_key,
        tier=tier_code,
        days=days,
        machine_id=machine_id,
    )
