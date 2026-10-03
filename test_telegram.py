"""Test Telegram message sender for ApexClash Pro alerts."""

import json
from pathlib import Path
import requests

CONFIG_FILE = Path(__file__).resolve().parent / "sales_bot" / "config.json"


def send_test_message():
    if not CONFIG_FILE.is_file():
        print("[!] config.json not found.")
        return False

    cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    token = cfg.get("telegram_bot_token", "").strip()
    chat_id = cfg.get("telegram_chat_id", "").strip()

    if not token or not chat_id:
        print("[!] Telegram bot token or chat ID is missing in sales_bot/config.json")
        return False

    text = (
        "🚀 <b>ApexClash Pro Security System Connected!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>Status:</b> Telegram Notifications Active\n"
        "💳 <b>Sample UTR:</b> <code>428391829102</code>\n"
        "🔑 <b>Sample Key:</b> <code>TXN-M30-20261103-428391829102-E8A291B7</code>\n"
        "📦 <b>Sample Plan:</b> Monthly Pass (₹249 / $4.99)\n"
        "💻 <b>Device:</b> <code>E8A291B74C9D32F1</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Whenever a buyer enters a Transaction ID / UTR in the app, you will receive an instant alert right here so you can verify payment!"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            print("[✓] Sample alert message sent to Telegram successfully!")
            return True
        else:
            err = data.get("description", "")
            print(f"[!] Telegram Error: {err}")
            if "chat not found" in err.lower():
                print(
                    "\n[*] Next step: Open https://t.me/Apexlegend_pro_bot in Telegram and tap 'START' once.\n"
                    "Then run this script again: python test_telegram.py"
                )
            return False
    except Exception as exc:
        print(f"[!] Network error: {exc}")
        return False


if __name__ == "__main__":
    send_test_message()
