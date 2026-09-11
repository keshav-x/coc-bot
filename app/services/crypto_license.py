"""Cryptographic activation and license validation engine for Clash AutoLoot.

Provides:
- Standalone HMAC-SHA256 license key generation and mathematical verification.
- 1-Device hardware fingerprint binding.
- Anti-tampering local 2-hour free trial wallet.
- Tier support: Monthly ($5/mo, 30 days), Quarterly, Annual, Lifetime.
- Zero external server dependencies required.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from app.utils.common import ensure_dir, get_user_app_data_dir
from app.utils.logger import setup_logger

logger = setup_logger("CryptoLicense")

# Official Public Verification Key for Clash AutoLoot (Ed25519)
# The matching Private Key is kept offline by the developer to sign valid licenses.
PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEApHskl5I35iw8dPqMWQDbRy1B0tguVjJPT40pC9ySDBo=
-----END PUBLIC KEY-----"""

LICENSE_PREFIX = "CAL"
TIER_WEEKLY = "W07"    # 7 Days ($1.00)
TIER_MONTHLY = "M30"   # 30 Days ($3.00)
TIER_ANNUAL = "Y36"    # 365 Days ($10.00)
TIER_LIFETIME = "LIFE" # Permanent VIP ($15.00)

TRIAL_TOTAL_SECONDS = 7200  # 2 Hours


@dataclass
class LicenseValidationResult:
    is_valid: bool
    reason: str  # "valid", "expired", "machine_mismatch", "invalid_format", "tampered", "empty"
    tier: str = ""
    expires_at_timestamp: Optional[int] = None
    bound_machine_id: Optional[str] = None

    @property
    def expiry_date_str(self) -> str:
        if not self.is_valid:
            return ""
        if self.tier == TIER_LIFETIME or self.expires_at_timestamp is None:
            return "Never"
        dt = datetime.fromtimestamp(self.expires_at_timestamp, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")


class CryptoLicenseEngine:
    @staticmethod
    def get_machine_id() -> str:
        """Returns the local machine hardware fingerprint for 1-device binding."""
        from app.services.license import HardwareFingerprint
        return HardwareFingerprint.compute()

    @classmethod
    def generate_key(
        cls,
        private_key_pem: str,
        tier: str = TIER_MONTHLY,
        days: int = 30,
        machine_id: Optional[str] = None,
    ) -> str:
        """Generates an unforgeable license key signed with the seller's offline Ed25519 Private Key.

        Format: CAL-[TIER]-[EXPDATE_OR_PERP]-[MACHINE_HASH]-[ED25519_SIG]
        """
        from Crypto.PublicKey import ECC
        from Crypto.Signature import eddsa

        if tier == TIER_LIFETIME:
            exp_code = "PERP"
            exp_ts = 0
        else:
            exp_ts = int(time.time()) + (days * 86400)
            exp_code = datetime.fromtimestamp(exp_ts, tz=timezone.utc).strftime("%Y%m%d")

        # Hardware binding segment
        if machine_id:
            m_hash = hashlib.sha256(machine_id.strip().encode()).hexdigest()[:8].upper()
        else:
            m_hash = "UNIV"  # Universal key that binds to first device activated on

        # Asymmetric digital signature over payload
        raw_payload = f"CAL:{tier}:{exp_code}:{m_hash}".encode("utf-8")
        priv_key = ECC.import_key(private_key_pem)
        signer = eddsa.new(priv_key, "rfc8032")
        sig = signer.sign(raw_payload)
        sig_b64 = base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")

        return f"{LICENSE_PREFIX}-{tier}-{exp_code}-{m_hash}-{sig_b64}"

    @classmethod
    def verify_key(
        cls,
        key: str,
        current_machine_id: str,
        saved_bound_machine: Optional[str] = None,
    ) -> LicenseValidationResult:
        """Validates key integrity via Ed25519 public key, hardware binding, and expiry."""
        if not key or not key.strip():
            return LicenseValidationResult(is_valid=False, reason="empty")

        parts = key.strip().split("-", 4)
        if len(parts) != 5 or parts[0].upper() != LICENSE_PREFIX:
            return LicenseValidationResult(is_valid=False, reason="invalid_format")

        tier = parts[1].upper()
        exp_code = parts[2].upper()
        m_hash = parts[3].upper()
        sig_b64 = parts[4]

        # Verify Ed25519 asymmetric signature with embedded Public Key
        raw_payload = f"CAL:{tier}:{exp_code}:{m_hash}".encode("utf-8")
        try:
            from Crypto.PublicKey import ECC
            from Crypto.Signature import eddsa

            pub_key = ECC.import_key(PUBLIC_KEY_PEM)
            verifier = eddsa.new(pub_key, "rfc8032")
            pad_len = (-len(sig_b64)) % 4
            sig_bytes = base64.urlsafe_b64decode((sig_b64 + "=" * pad_len).encode("ascii"))
            verifier.verify(raw_payload, sig_bytes)
        except Exception:
            return LicenseValidationResult(is_valid=False, reason="not_found")

        # Parse expiration timestamp
        if exp_code == "PERP":
            exp_ts = 0
        else:
            try:
                dt = datetime.strptime(exp_code, "%Y%m%d").replace(
                    hour=23, minute=59, second=59, tzinfo=timezone.utc
                )
                exp_ts = int(dt.timestamp())
            except ValueError:
                return LicenseValidationResult(is_valid=False, reason="invalid_format")

        # Verify Expiry
        now = int(time.time())
        if tier != TIER_LIFETIME and exp_ts > 0 and now > exp_ts:
            return LicenseValidationResult(
                is_valid=False,
                reason="expired",
                tier=tier,
                expires_at_timestamp=exp_ts,
            )

        # Verify Hardware Binding
        curr_m_hash = hashlib.sha256(current_machine_id.strip().encode()).hexdigest()[:8].upper()
        if m_hash != "UNIV":
            # Key was pre-locked to a specific machine ID
            if m_hash != curr_m_hash:
                return LicenseValidationResult(
                    is_valid=False,
                    reason="machine_mismatch",
                    tier=tier,
                    expires_at_timestamp=exp_ts,
                )
        else:
            # Universal key: check if already bound to another machine locally
            if saved_bound_machine and saved_bound_machine != current_machine_id:
                return LicenseValidationResult(
                    is_valid=False,
                    reason="machine_mismatch",
                    tier=tier,
                    expires_at_timestamp=exp_ts,
                )

        return LicenseValidationResult(
            is_valid=True,
            reason="valid",
            tier=tier,
            expires_at_timestamp=exp_ts if exp_ts > 0 else None,
            bound_machine_id=current_machine_id,
        )


class LocalTrialVault:
    """Anti-tamper local 2-Hour Free Trial wallet secured with hardware HMAC seals."""

    @staticmethod
    def _vault_path() -> Path:
        d = get_user_app_data_dir()
        ensure_dir(d)
        return d / "trial_vault.json"

    @classmethod
    def _compute_seal(cls, hw_id: str, used_seconds: int, total_seconds: int) -> str:
        raw = f"TRIAL:{hw_id}:{used_seconds}:{total_seconds}"
        return hmac.new(_SIGNING_SALT, raw.encode(), hashlib.sha256).hexdigest()[:16]

    @classmethod
    def load_or_init(cls, hw_id: str) -> dict:
        p = cls._vault_path()
        if not p.is_file():
            initial_data = {
                "hw_id": hw_id,
                "used_seconds": 0,
                "total_seconds": TRIAL_TOTAL_SECONDS,
                "last_tick": int(time.time()),
                "seal": cls._compute_seal(hw_id, 0, TRIAL_TOTAL_SECONDS),
            }
            p.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")
            return initial_data

        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            used = int(data.get("used_seconds", 0))
            total = int(data.get("total_seconds", TRIAL_TOTAL_SECONDS))
            expected_seal = cls._compute_seal(hw_id, used, total)
            if not hmac.compare_digest(data.get("seal", ""), expected_seal):
                logger.warning("Local trial vault seal mismatch (tampering detected).")
                # Penalty: cap at expired
                data["used_seconds"] = TRIAL_TOTAL_SECONDS
                data["seal"] = cls._compute_seal(hw_id, TRIAL_TOTAL_SECONDS, TRIAL_TOTAL_SECONDS)
                p.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data
        except Exception as e:
            logger.warning(f"Error reading trial vault: {e}")
            return {
                "hw_id": hw_id,
                "used_seconds": TRIAL_TOTAL_SECONDS,
                "total_seconds": TRIAL_TOTAL_SECONDS,
                "last_tick": int(time.time()),
                "seal": "",
            }

    @classmethod
    def tick(cls, hw_id: str, elapsed_seconds: int = 0) -> Tuple[bool, int, int]:
        """Debits elapsed_seconds from the trial vault.

        Returns (allowed: bool, remaining_seconds: int, used_seconds: int).
        """
        data = cls.load_or_init(hw_id)
        used = int(data.get("used_seconds", 0))
        total = int(data.get("total_seconds", TRIAL_TOTAL_SECONDS))

        # Debit elapsed
        capped_elapsed = min(max(0, elapsed_seconds), 120)
        new_used = min(total, used + capped_elapsed)

        data["used_seconds"] = new_used
        data["last_tick"] = int(time.time())
        data["seal"] = cls._compute_seal(hw_id, new_used, total)

        p = cls._vault_path()
        try:
            p.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Could not persist trial vault: {e}")

        remaining = max(0, total - new_used)
        allowed = remaining > 0
        return (allowed, remaining, new_used)
