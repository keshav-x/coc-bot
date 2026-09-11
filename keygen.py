#!/usr/bin/env python3
"""Clash AutoLoot — License Key Generator & Management Utility.

Usage Examples:
---------------
1. Generate a 30-Day Subscription Key ($5.00/mo):
   python keygen.py --generate --type monthly --days 30

2. Generate a Lifetime Single-Device Key:
   python keygen.py --generate --type lifetime

3. Generate a 30-Day Key Locked specifically to a customer's Machine ID:
   python keygen.py --generate --type monthly --days 30 --machine A1B2C3D4E5F67890

4. Verify a License Key:
   python keygen.py --verify CAL-M30-20261011-UNIV-9A1B2C3D

5. Check Current PC Hardware ID:
   python keygen.py --my-id
"""

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.crypto_license import (
    CryptoLicenseEngine,
    TIER_MONTHLY,
    TIER_ANNUAL,
    TIER_LIFETIME,
)
from app.services.license import HardwareFingerprint


def main():
    parser = argparse.ArgumentParser(
        description="Clash AutoLoot Cryptographic License Key Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--generate",
        action="store_true",
        help="Generate a new cryptographically signed activation key",
    )
    parser.add_argument(
        "--type",
        choices=["monthly", "annual", "lifetime"],
        default="monthly",
        help="Subscription tier: monthly ($5/mo), annual ($50/yr), or lifetime",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Duration in days (default: 30 for monthly, 365 for annual)",
    )
    parser.add_argument(
        "--machine",
        type=str,
        default=None,
        help="Optional Customer Machine ID to lock the key specifically to their hardware",
    )
    parser.add_argument(
        "--verify",
        type=str,
        default=None,
        help="Verify and inspect an activation key string",
    )
    parser.add_argument(
        "--my-id",
        action="store_true",
        help="Print this computer's unique hardware fingerprint",
    )

    args = parser.parse_args()

    if args.my_id:
        hw_id = HardwareFingerprint.compute()
        print("\n=======================================================")
        print("  THIS MACHINE HARDWARE FINGERPRINT")
        print("=======================================================")
        print(f"  Machine ID: {hw_id}")
        print("  (Share this ID with the bot seller to get a locked key)")
        print("=======================================================\n")
        return

    if args.verify:
        key = args.verify.strip().upper()
        hw_id = HardwareFingerprint.compute()
        res = CryptoLicenseEngine.verify_key(key, hw_id)
        print("\n=======================================================")
        print("  LICENSE KEY VERIFICATION")
        print("=======================================================")
        print(f"  Key:        {key}")
        print(f"  Status:     {'[VALID]' if res.is_valid else '[INVALID]'}")
        print(f"  Reason:     {res.reason}")
        print(f"  Tier:       {res.tier}")
        print(f"  Expires On: {res.expiry_date_str}")
        print("=======================================================\n")
        return

    if args.generate:
        tier_map = {
            "monthly": (TIER_MONTHLY, args.days if args.days != 30 else 30),
            "annual": (TIER_ANNUAL, args.days if args.days != 30 else 365),
            "lifetime": (TIER_LIFETIME, 0),
        }
        tier_code, days = tier_map[args.type]
        key = CryptoLicenseEngine.generate_key(
            tier=tier_code,
            days=days,
            machine_id=args.machine,
        )
        print("\n=======================================================")
        print("  *** NEW CLASH AUTOLOOT ACTIVATION KEY GENERATED ***")
        print("=======================================================")
        print(f"  Key:         {key}")
        print(f"  Tier:        {args.type.upper()} ({days} days)" if days > 0 else f"  Tier:        {args.type.upper()} (Perpetual)")
        print(f"  Hardware:    Locked to [{args.machine}]" if args.machine else "  Hardware:    1 Device (Universal First-Activation Lock)")
        print("=======================================================\n")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
