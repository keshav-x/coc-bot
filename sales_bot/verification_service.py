"""
Transaction ID verification service for ApexClash Pro.

Strategy per payment method
─────────────────────────────────────────────────────────────────────────────
PayPal
  Step 1 — Format check   : 17 alphanumeric uppercase chars (e.g. 5LY36029PD1738444)
  Step 2 — Duplicate check: reject if this TXN ID was already used for another order
  Step 3 — API verify     : if client_id/secret configured, calls PayPal Captures API:
              GET /v2/payments/captures/{id}  → status COMPLETED + amount >= expected
            If API not configured → accepted optimistically, admin gets 1h approval window.

UPI / GPay / PhonePe
  Step 1 — Format check   : 10-25 digit numeric reference number
  Step 2 — Duplicate check: reject if already used
  Step 3 — Optimistic     : accepted immediately, admin gets 30-min revocation window.
            No public API exists that lets individuals verify UPI UTRs programmatically.

Revocation
  Any order can be revoked by the admin at any time via /revoke in Discord.
  Revoked keys are written to revoked_keys.json and optionally published to a
  GitHub Gist, which the in-app license validator checks on each revalidation cycle.
"""

from __future__ import annotations

import re
from typing import Tuple

# ── Transaction ID patterns ───────────────────────────────────────────────────

# PayPal: 17 uppercase alphanumeric (letters + digits)
# e.g. "5LY36029PD1738444", "8MC585209K746392H"
_PAYPAL_PATTERN = re.compile(r"^[0-9A-Z]{17}$")

# UPI UTR / Bank Reference: 10-25 digits (standard UPI bank reference is 12 digits)
_UPI_DIGITS_PATTERN = re.compile(r"^\d{10,25}$")

# PhonePe Transaction ID: usually starts with T or P followed by 14-30 alphanumeric characters
# e.g. "T2410031805123456789012"
_PHONEPE_TXN_PATTERN = re.compile(r"^[TPtp][0-9A-Za-z]{14,32}$")

# Google Pay / Paytm alphanumeric transaction/order ID
# e.g. "CICAgIDU4rOCw", "UPI427819283746"
_GENERIC_UPI_ALPHANUM_PATTERN = re.compile(r"^[0-9A-Za-z_-]{10,32}$")


def validate_paypal_txn_id(txn_id: str) -> Tuple[bool, str]:
    """
    Validates a PayPal Transaction / Capture ID.
    Returns (is_valid: bool, clean_id_or_error_message: str).
    """
    clean = txn_id.strip().upper().replace(" ", "")
    if not clean:
        return False, "Transaction ID is empty."
    if not _PAYPAL_PATTERN.match(clean):
        return (
            False,
            f"**Invalid PayPal Transaction ID format.**\n"
            f"PayPal IDs are exactly 17 uppercase letters/numbers.\n"
            f"Example: `5LY36029PD1738444`\n"
            f"You entered: `{txn_id[:30]}`\n\n"
            f"Where to find it: PayPal app → Activity → tap the payment → Transaction ID.",
        )
    return True, clean


def validate_upi_txn_id(txn_id: str) -> Tuple[bool, str]:
    """
    Validates a UPI UTR, PhonePe Transaction ID, or GPay reference.
    Returns (is_valid: bool, clean_id_or_error_message: str).
    """
    clean = txn_id.strip().replace(" ", "")
    if not clean:
        return False, "Transaction reference is empty."

    # 1. 10-25 digit numeric UTR (most common across all UPI apps)
    if _UPI_DIGITS_PATTERN.match(clean):
        return True, clean

    # 2. PhonePe Transaction ID (T24... / P24...)
    if _PHONEPE_TXN_PATTERN.match(clean):
        return True, clean.upper()

    # 3. Alphanumeric UPI ref (GPay / Paytm / BHIM)
    # Must contain at least 2 digits to prevent pure random letters
    if _GENERIC_UPI_ALPHANUM_PATTERN.match(clean) and sum(c.isdigit() for c in clean) >= 2:
        return True, clean

    return (
        False,
        f"**Invalid UPI Reference format.**\n"
        f"UPI references can be:\n"
        f"• **12-digit UTR** (e.g. `427819283746`)\n"
        f"• **PhonePe Transaction ID** (e.g. `T241003...`)\n"
        f"• **GPay / Paytm Reference**\n"
        f"You entered: `{txn_id[:30]}`\n\n"
        f"Where to find it: PhonePe / GPay → Transaction History → tap payment → Details.",
    )


def is_known_test_id(txn_id: str) -> bool:
    """Rejects obviously fake placeholder transaction IDs and trivial repetition."""
    clean = txn_id.strip().upper().replace(" ", "")
    _FAKE_PATTERNS = {
        "123456789012",
        "000000000000",
        "111111111111",
        "222222222222",
        "999999999999",
        "12345678901234567",
        "5LY36029PD1738444",  # the example from our own docs
        "8MC585209K746392H",
        "012345678901",
        "1234567890",
        "0000000000",
    }
    if clean in {p.upper() for p in _FAKE_PATTERNS}:
        return True

    # If the string consists of mostly identical characters (e.g. "00000000000000")
    if len(clean) >= 10 and len(set(clean)) <= 2:
        return True

    return False
