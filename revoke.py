"""ApexClash Pro — 1-Click Key & Transaction Revocation Tool

Usage:
  python revoke.py 427819283746 "fake payment"
  python revoke.py CAL-M30-20261103-... "chargeback"

This script appends the target to docs/revoked.txt and syncs it.
The desktop bot re-downloads this file periodically and blocks revoked keys.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REVOKED_FILE = ROOT / "docs" / "revoked.txt"


def main():
    if len(sys.argv) < 2:
        print("\nUsage: python revoke.py <license_key_or_txn_id> [reason]")
        print("Example: python revoke.py 427819283746 'unpaid upi'\n")
        sys.exit(1)

    target = sys.argv[1].strip()
    reason = sys.argv[2].strip() if len(sys.argv) > 2 else "admin_revoke"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if not REVOKED_FILE.is_file():
        REVOKED_FILE.write_text("# ApexClash Pro — Revocation Blacklist\n", encoding="utf-8")

    content = REVOKED_FILE.read_text(encoding="utf-8")
    lines = [line.strip() for line in content.splitlines()]

    if target in lines:
        print(f"[!] '{target}' is already in docs/revoked.txt")
    else:
        with open(REVOKED_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n# Revoked: {reason} on {now_str}\n{target}\n")
        print(f"[✓] Added '{target}' to docs/revoked.txt (reason: {reason})")

    # Ask if user wants to push to GitHub
    try:
        print("[*] Committing to git...")
        subprocess.run(["git", "add", "docs/revoked.txt"], cwd=ROOT, check=True)
        subprocess.run(["git", "commit", "-m", f"revoke: {target} ({reason})"], cwd=ROOT, check=True)
        print("[✓] Committed to git.")
        print("[*] Run 'git push' to deploy blacklist live to GitHub.")
    except Exception as exc:
        print(f"[*] Note: Manual git commit/push needed if you want it live: {exc}")


if __name__ == "__main__":
    main()
