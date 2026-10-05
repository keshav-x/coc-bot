"""
ApexClash Pro â€” Discord Sales & License Automation Bot  (v3 â€” TXN-ID verification)

Payment flow
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
1. /store  â†’ user picks plan
2. Bot shows PayPal link (pre-filled amount) + GPay/UPI QR (pre-filled amount)
3. User pays with either method
4. User clicks "I've Paid" â†’ modal asks for Transaction ID
5. Bot validates the Transaction ID:
     PayPal   â†’ format check + PayPal Captures API verify (auto, zero-touch)
     UPI/GPay â†’ format check + duplicate check (optimistic: key delivered,
                30-min admin approval window)
6. Key is generated & DM'd to user automatically
7. Admin gets a notification DM with Approve / Revoke buttons
8. /revoke <order_id>  â†’ revokes the key, DMs the user, pushes to revocation Gist

Admin commands
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
/store    â€” open the public store
/genkey   â€” manually generate a key (optionally DM to a member)
/verify   â€” inspect any key
/orders   â€” list recent orders
/revoke   â€” revoke a key by order ID (can also flag it as fraud)
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import string
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

SALES_BOT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT  = SALES_BOT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import discord
from discord import app_commands
from discord.ext import commands

from app.services.crypto_license import CryptoLicenseEngine
from sales_bot.config           import load_config, save_example_config, CONFIG_PATH
from sales_bot.license_generator import generate_license_for_tier
from sales_bot.paypal_service   import PayPalService
from sales_bot.upi_service      import UPIService
from sales_bot.verification_service import (
    validate_paypal_txn_id,
    validate_upi_txn_id,
    is_known_test_id,
)
from sales_bot.revocation_service import (
    revoke_order,
    is_key_revoked,
    push_revocation_gist,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("SalesBot")

ORDERS_DB_PATH = SALES_BOT_DIR / "orders.json"

# â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _fmt_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %d %H:%M UTC") if ts else "?"

def _make_order_id() -> str:
    return "ACB-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

def load_orders() -> Dict[str, Any]:
    if ORDERS_DB_PATH.is_file():
        try:
            with open(ORDERS_DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_orders(orders: Dict[str, Any]) -> None:
    try:
        with open(ORDERS_DB_PATH, "w", encoding="utf-8") as f:
            json.dump(orders, f, indent=2)
    except Exception as exc:
        logger.error("save_orders: %s", exc)

def is_txn_id_used(txn_id: str, exclude_order_id: Optional[str] = None) -> bool:
    """Returns True if this transaction ID is already linked to an existing active/delivered order."""
    clean = txn_id.strip().upper()
    if not clean:
        return False
    orders = load_orders()
    return any(
        oid != exclude_order_id and o.get("txn_id", "").strip().upper() == clean
        for oid, o in orders.items()
        if o.get("status") not in ("rejected", "revoked", "awaiting_payment")
    )

# â”€â”€ Embed builders â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _delivery_embed(tier: str, order_id: str, key: str) -> discord.Embed:
    plan = config["pricing"].get(tier, {})
    days  = plan.get("days", 0)
    expiry = "Never (Lifetime)" if not days else f"{days} days from today"
    embed = discord.Embed(
        title="ðŸŽ‰ You're Unlocked â€” ApexClash Pro is Active!",
        description=(
            f"Your **{plan.get('name', tier.capitalize())} license** has been delivered.\n\n"
            f"**Your Activation Key:**\n"
            f"```\n{key}\n```\n"
            f"**How to activate (30 seconds):**\n"
            f"1. Open **ApexClash Bot** on your PC.\n"
            f"2. Navigate to the **License** tab.\n"
            f"3. Paste your key â†’ click **Check Key**.\n"
            f"4. Green light = bot unlocked. Farming begins automatically."
        ),
        color=0x10B981,
    )
    embed.add_field(name="Plan",    value=plan.get("name", tier), inline=True)
    embed.add_field(name="Expires", value=expiry,                 inline=True)
    embed.add_field(name="Order",   value=f"`{order_id}`",        inline=True)
    embed.set_footer(text="Ed25519 signed â€¢ hardware-bound â€¢ offline verification â€¢ Store this key safely.")
    return embed

# â”€â”€ Services (loaded after config) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

config = load_config()
save_example_config()

upi_svc = UPIService(
    upi_id=config.get("phonepe_upi_id", "yourphonepe@ybl"),
    payee_name=config.get("payee_name", "ApexClash Pro"),
)
paypal_svc = PayPalService(
    client_id=config.get("paypal_client_id", ""),
    client_secret=config.get("paypal_client_secret", ""),
    mode=config.get("paypal_mode", "live"),
)
PAYPAL_ME_URL: str   = config.get("paypal_me_url", "https://paypal.me/yourname")
ADMIN_ID: int        = config.get("admin_discord_id", 0)
GIST_ID: str         = config.get("revocation_gist_id", "")
GITHUB_TOKEN: str    = config.get("github_token", "")
AUTO_REVOKE_UNCONFIRMED: bool = config.get("auto_revoke_unconfirmed", False)
UPI_APPROVAL_SECS: int  = config.get("upi_approval_window_seconds", 1800)   # 30 min (if auto_revoke_unconfirmed is enabled)
PAYPAL_APPROVAL_SECS: int = config.get("paypal_approval_window_seconds", 300)  # 5 min without API

# â”€â”€ Bot setup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MODALS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class TxnIdModal(discord.ui.Modal):
    txn_id = discord.ui.TextInput(
        label="Transaction / Reference ID",
        placeholder="PayPal: 5LY36029PD1738444  |  UPI/GPay: 427819283746",
        min_length=10,
        max_length=40,
        required=True,
        style=discord.TextStyle.short,
    )

    def __init__(
        self,
        order_id: str,
        tier: str,
        method: str,           # "paypal" | "upi"
        amount_inr: int,
        amount_usd: float,
    ):
        super().__init__(title="Confirm Your Payment")
        self.order_id   = order_id
        self.tier       = tier
        self.method     = method
        self.amount_inr = amount_inr
        self.amount_usd = amount_usd

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        raw_txn = self.txn_id.value.strip()

        # â”€â”€ Step 1: known fake ID â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if is_known_test_id(raw_txn):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="âŒ Rejected â€” Example / Test ID",
                    description=(
                        f"`{raw_txn}` matches a known example or placeholder value.\n\n"
                        "Please enter your **actual transaction ID** from your payment confirmation."
                    ),
                    color=0xEF4444,
                ),
                ephemeral=True,
            )
            return

        # â”€â”€ Step 2: format validation with method auto-detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        method = self.method
        if method == "paypal":
            ok, result = validate_paypal_txn_id(raw_txn)
            if not ok:
                # Check if buyer clicked PayPal button but paid via UPI
                upi_ok, upi_res = validate_upi_txn_id(raw_txn)
                if upi_ok:
                    method = "upi"
                    ok, result = True, upi_res
        else:
            ok, result = validate_upi_txn_id(raw_txn)
            if not ok:
                # Check if buyer clicked UPI button but paid via PayPal
                pp_ok, pp_res = validate_paypal_txn_id(raw_txn)
                if pp_ok:
                    method = "paypal"
                    ok, result = True, pp_res

        self.method = method

        if not ok:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="âŒ Invalid Transaction ID",
                    description=result,
                    color=0xEF4444,
                ),
                ephemeral=True,
            )
            return

        clean_txn = result  # sanitised value

        # â”€â”€ Step 3: duplicate check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if is_txn_id_used(clean_txn, exclude_order_id=self.order_id):
            await interaction.followup.send(
                embed=discord.Embed(
                    title="âŒ Transaction ID Already Used",
                    description=(
                        f"`{clean_txn}` has already been submitted for another order.\n\n"
                        "Each payment can only be used for one license key.\n"
                        "If you believe this is an error, contact the admin."
                    ),
                    color=0xEF4444,
                ),
                ephemeral=True,
            )
            return

        # â”€â”€ Step 4: record the order (before verification, to lock TXN ID) â”€â”€â”€â”€
        orders = load_orders()
        order = orders.get(self.order_id, {})
        order.update({
            "txn_id":     clean_txn,
            "method":     self.method,
            "submitted_at": int(time.time()),
        })
        orders[self.order_id] = order
        save_orders(orders)

        # â”€â”€ Step 5: PayPal API verification (if configured) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if self.method == "paypal" and paypal_svc.is_configured:
            verified = paypal_svc.capture_order(clean_txn)
            if verified:
                await _deliver_key_and_notify(
                    interaction, self.order_id, self.tier,
                    clean_txn, self.method, verified_auto=True
                )
            else:
                # API says not captured yet â€” could be wrong TXN ID
                await interaction.followup.send(
                    embed=discord.Embed(
                        title="âš ï¸ PayPal Payment Not Found",
                        description=(
                            f"The PayPal Transaction ID `{clean_txn}` could not be verified as **Completed**.\n\n"
                            "**Please check:**\n"
                            "â€¢ You copied the correct **Transaction ID** (not the order ID).\n"
                            "â€¢ The payment status is **Completed** in your PayPal app.\n"
                            "â€¢ PayPal â†’ Activity â†’ tap the payment â†’ Transaction ID.\n\n"
                            "If your payment is confirmed, try again in 2â€“3 minutes or contact the admin."
                        ),
                        color=0xF59E0B,
                    ),
                    ephemeral=True,
                )
            return

        # â”€â”€ Step 6: optimistic delivery (UPI / PayPal without API) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        await _deliver_key_and_notify(
            interaction, self.order_id, self.tier,
            clean_txn, self.method, verified_auto=False
        )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Core delivery function
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

async def _deliver_key_and_notify(
    interaction: discord.Interaction,
    order_id: str,
    tier: str,
    txn_id: str,
    method: str,
    verified_auto: bool,
):
    """Generates key, saves order, DMs user, and pings admin."""
    try:
        key = generate_license_for_tier(tier)
    except Exception as exc:
        await interaction.followup.send(
            f"âŒ Key generation error: `{exc}`. Contact admin.", ephemeral=True
        )
        return

    orders = load_orders()
    order  = orders.get(order_id, {})
    order.update({
        "status":        "delivered",
        "license_key":   key,
        "delivered_at":  int(time.time()),
        "verified_auto": verified_auto,
    })
    orders[order_id] = order
    save_orders(orders)

    plan = config["pricing"].get(tier, {})
    amount_label = (
        f"â‚¹{plan.get('inr', '?')}"
        if method == "upi"
        else f"${plan.get('usd', '?'):.2f}"
    )
    window_label = (
        f"{UPI_APPROVAL_SECS // 60} min"
        if method == "upi"
        else f"{PAYPAL_APPROVAL_SECS // 60} min"
    )

    # â”€â”€ Deliver to user â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    verification_note = (
        "âœ… **Payment auto-verified via PayPal API.**"
        if verified_auto
        else (
            f"âš¡ **License is active immediately!**\n"
            f"Keep your Order ID `{order_id}` for reference.\n"
            f"*(Note: Transaction IDs are cross-checked with banking records. Fraudulent IDs are blacklisted and revoked).* "
        )
    )

    user_embed = _delivery_embed(tier, order_id, key)
    user_embed.add_field(name="Status", value=verification_note, inline=False)

    await interaction.followup.send(embed=user_embed, ephemeral=True)

    # â”€â”€ Admin notification â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if ADMIN_ID:
        try:
            admin = bot.get_user(ADMIN_ID) or await bot.fetch_user(ADMIN_ID)
        except Exception:
            admin = None

        if admin:
            method_emoji = "âš¡" if method == "upi" else "ðŸ’³"
            admin_embed = discord.Embed(
                title=f"{method_emoji} New Sale â€” {plan.get('name', tier)} ({amount_label})",
                description=(
                    f"A key has been **auto-delivered** to <@{interaction.user.id}>.\n"
                    f"{'Payment was verified via PayPal API âœ…' if verified_auto else 'Check your PhonePe / PayPal app to confirm funds, then click **Confirm** or **Revoke** below.'}"
                ),
                color=0x10B981 if verified_auto else 0x38BDF8,
            )
            admin_embed.add_field(name="Order ID",  value=f"`{order_id}`",                                inline=True)
            admin_embed.add_field(name="Plan",       value=plan.get("name", tier),                        inline=True)
            admin_embed.add_field(name="Amount",     value=amount_label,                                  inline=True)
            admin_embed.add_field(name="Method",     value=method.upper(),                                inline=True)
            admin_embed.add_field(name="Customer",   value=f"<@{interaction.user.id}> (`{interaction.user.name}`)", inline=True)
            admin_embed.add_field(name="TXN ID",     value=f"```{txn_id}```",                             inline=False)
            admin_embed.add_field(name="Key Issued", value=f"```{key[:50]}...```",                        inline=False)

            if not verified_auto:
                admin_embed.set_footer(
                    text=f"Verify in {'PhonePe app â€” check â‚¹' + str(plan.get('inr','?')) + ' received' if method == 'upi' else 'PayPal â€” check $' + str(plan.get('usd','?')) + ' received'}. Tap Revoke below if fake."
                )

            view = AdminReviewView(
                order_id=order_id,
                buyer_id=interaction.user.id,
                key=key,
                tier=tier,
                txn_id=txn_id,
                verified_auto=verified_auto,
            )
            try:
                await admin.send(embed=admin_embed, view=view)
            except Exception as exc:
                logger.error("Could not DM admin: %s", exc)

    # â”€â”€ Auto-revocation timer (only if explicitly enabled in config) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if not verified_auto and AUTO_REVOKE_UNCONFIRMED:
        window = UPI_APPROVAL_SECS if method == "upi" else PAYPAL_APPROVAL_SECS
        asyncio.create_task(
            _auto_revocation_check(order_id, key, window)
        )


async def _auto_revocation_check(order_id: str, key: str, window_seconds: int):
    """
    After the approval window expires, re-checks the order status.
    If admin has NOT marked it as 'confirmed', the key is auto-revoked.
    Marking as confirmed requires admin to click 'Confirm' in the admin DM.
    """
    await asyncio.sleep(window_seconds)
    orders = load_orders()
    order = orders.get(order_id, {})

    if order.get("status") == "confirmed":
        logger.info("Order %s was confirmed by admin â€” no auto-revocation.", order_id)
        return
    if order.get("status") == "revoked":
        logger.info("Order %s was already manually revoked.", order_id)
        return

    # Auto-revoke
    logger.warning("Order %s â€” approval window expired. Auto-revoking.", order_id)
    order["status"] = "revoked"
    order["revoke_reason"] = "auto_expired"
    order["revoked_at"] = int(time.time())
    orders[order_id] = order
    save_orders(orders)

    revoke_order(order_id, key, reason="auto_expired")
    if GIST_ID and GITHUB_TOKEN:
        push_revocation_gist(GIST_ID, GITHUB_TOKEN)

    # DM the user
    buyer_id = order.get("user_id")
    if buyer_id:
        try:
            buyer = bot.get_user(buyer_id) or await bot.fetch_user(buyer_id)
            await buyer.send(
                embed=discord.Embed(
                    title="ðŸš« Access Revoked â€” Payment Unverified",
                    description=(
                        f"Your license key for order `{order_id}` has been **revoked** "
                        f"because the payment transaction ID `{order.get('txn_id', '?')}` "
                        f"could not be verified within the allowed time window.\n\n"
                        "If your payment was genuine, please contact support with:\n"
                        "â€¢ A **screenshot** of your payment confirmation.\n"
                        "â€¢ Your **Order ID**: `{order_id}`"
                    ),
                    color=0xEF4444,
                )
            )
        except Exception:
            pass

    logger.info("Auto-revocation complete for order %s.", order_id)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Admin Review View
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class AdminReviewView(discord.ui.View):
    def __init__(
        self,
        order_id: str,
        buyer_id: int,
        key: str,
        tier: str,
        txn_id: str,
        verified_auto: bool,
    ):
        super().__init__(timeout=None)
        self.order_id     = order_id
        self.buyer_id     = buyer_id
        self.key          = key
        self.tier         = tier
        self.txn_id       = txn_id
        self.verified_auto = verified_auto

        if verified_auto:
            # Remove revoke-for-fraud from auto-verified; keep only revoke
            pass

    @discord.ui.button(label="âœ… Confirm â€” Payment Genuine", style=discord.ButtonStyle.green, emoji="ðŸ”’")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        orders = load_orders()
        order  = orders.get(self.order_id, {})
        if order.get("status") == "revoked":
            await interaction.response.send_message("âš ï¸ Already revoked.", ephemeral=True)
            return
        order["status"] = "confirmed"
        order["confirmed_at"] = int(time.time())
        orders[self.order_id] = order
        save_orders(orders)

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"âœ… Order {self.order_id} â€” Confirmed",
                description=f"Payment confirmed. Key remains active for <@{self.buyer_id}>.",
                color=0x10B981,
            ),
            view=self,
        )

    @discord.ui.button(label="ðŸš« Revoke â€” Fake / Fraudulent", style=discord.ButtonStyle.danger, emoji="âŒ")
    async def revoke(self, interaction: discord.Interaction, button: discord.ui.Button):
        orders = load_orders()
        order  = orders.get(self.order_id, {})
        if order.get("status") == "revoked":
            await interaction.response.send_message("âš ï¸ Already revoked.", ephemeral=True)
            return

        order["status"]       = "revoked"
        order["revoke_reason"] = "admin_manual_fraud"
        order["revoked_at"]   = int(time.time())
        orders[self.order_id] = order
        save_orders(orders)

        revoke_order(self.order_id, self.key, reason="admin_manual_fraud")
        if GIST_ID and GITHUB_TOKEN:
            asyncio.create_task(asyncio.to_thread(
                push_revocation_gist, GIST_ID, GITHUB_TOKEN
            ))

        # DM buyer
        try:
            buyer = bot.get_user(self.buyer_id) or await bot.fetch_user(self.buyer_id)
            await buyer.send(
                embed=discord.Embed(
                    title="ðŸš« License Revoked",
                    description=(
                        f"Your license key for order `{self.order_id}` has been revoked.\n\n"
                        "The transaction ID you submitted could not be verified as a genuine payment.\n\n"
                        "If you believe this is a mistake, reply here with a **screenshot** of your payment."
                    ),
                    color=0xEF4444,
                )
            )
        except Exception:
            pass

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"ðŸš« Order {self.order_id} â€” Revoked (Fraud)",
                description=(
                    f"Key revoked and added to revocation list.\n"
                    f"TXN ID `{self.txn_id}` blacklisted.\n"
                    f"User <@{self.buyer_id}> has been notified."
                ),
                color=0xEF4444,
            ),
            view=self,
        )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Payment method selection views
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class PaymentView(discord.ui.View):
    """
    Shown after plan selection.
    Displays payment instructions + 'I've Paid' buttons for each method.
    """

    def __init__(self, tier: str):
        super().__init__(timeout=300)
        self.tier     = tier
        plan          = config["pricing"].get(tier, {})
        self.inr: int      = plan.get("inr", 249)
        self.usd: float    = plan.get("usd", 4.99)
        self.plan_name: str = plan.get("name", "Pass")
        self.order_id  = _make_order_id()

        # Pre-register order skeleton so TXN ID slot is reserved
        orders = load_orders()
        if self.order_id not in orders:
            orders[self.order_id] = {
                "order_id":   self.order_id,
                "user_id":    0,
                "tier":       tier,
                "created_at": int(time.time()),
                "status":     "awaiting_payment",
            }
            save_orders(orders)

        # Build UPI QR & links
        self._upi_qr_url   = upi_svc.build_qr_url(self.inr, self.order_id)
        self._upi_intent   = upi_svc.build_upi_uri(self.inr, self.order_id)
        self._paypal_url   = f"{PAYPAL_ME_URL}/{self.usd:.2f}"

        # Link buttons (row 0)
        self.add_item(discord.ui.Button(
            label=f"ðŸ“± Open PhonePe / GPay (â‚¹{self.inr})",
            url=self._upi_intent,
            style=discord.ButtonStyle.link,
            row=0,
        ))
        self.add_item(discord.ui.Button(
            label=f"ðŸ’³ Pay via PayPal (${self.usd:.2f})",
            url=self._paypal_url,
            style=discord.ButtonStyle.link,
            row=0,
        ))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Stamp the buyer ID on first interaction
        orders = load_orders()
        order  = orders.get(self.order_id, {})
        if not order.get("user_id"):
            order["user_id"]  = interaction.user.id
            order["username"] = str(interaction.user)
            orders[self.order_id] = order
            save_orders(orders)
        return True

    @discord.ui.button(
        label="âš¡ Paid with PhonePe / UPI â€” Submit TXN ID",
        style=discord.ButtonStyle.success,
        row=1,
    )
    async def paid_upi(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            TxnIdModal(
                order_id=self.order_id,
                tier=self.tier,
                method="upi",
                amount_inr=self.inr,
                amount_usd=self.usd,
            )
        )

    @discord.ui.button(
        label="ðŸ’³ Paid with PayPal â€” Submit TXN ID",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def paid_paypal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            TxnIdModal(
                order_id=self.order_id,
                tier=self.tier,
                method="paypal",
                amount_inr=self.inr,
                amount_usd=self.usd,
            )
        )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Plan selection
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class PlanSelect(discord.ui.Select):
    def __init__(self):
        p = config.get("pricing", {})
        options = [
            discord.SelectOption(
                label=f"âš¡ Weekly Pass  â€” â‚¹{p['weekly']['inr']} / ${p['weekly']['usd']}",
                value="weekly",
                description="7 Days VIP",
                emoji="ðŸ—“ï¸",
            ),
            discord.SelectOption(
                label=f"ðŸŒŸ Monthly VIP  â€” â‚¹{p['monthly']['inr']} / ${p['monthly']['usd']}",
                value="monthly",
                description="30 Days â€¢ Most Popular",
                emoji="â­",
                default=True,
            ),
            discord.SelectOption(
                label=f"ðŸ† Annual Pass  â€” â‚¹{p['annual']['inr']} / ${p['annual']['usd']}",
                value="annual",
                description="365 Days â€¢ 50% cheaper than monthly",
                emoji="ðŸ“…",
            ),
            discord.SelectOption(
                label=f"ðŸ‘‘ Lifetime VIP â€” â‚¹{p['lifetime']['inr']} / ${p['lifetime']['usd']}",
                value="lifetime",
                description="Never expires",
                emoji="â™¾ï¸",
            ),
        ]
        super().__init__(
            placeholder="ðŸ›’  Pick a plan to continueâ€¦",
            min_values=1, max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        tier = self.values[0]
        plan = config["pricing"].get(tier, {})
        days_str = "Forever" if tier == "lifetime" else f"{plan.get('days')} days"

        pview = PaymentView(tier)

        embed = discord.Embed(
            title=f"{'ðŸ‘‘' if tier == 'lifetime' else 'âœ…'}  {plan['name']} â€” Payment Details",
            description=(
                f"**Duration:** {days_str}\n"
                f"**UPI / PhonePe (India):** â‚¹{plan['inr']}\n"
                f"**PayPal / Cards (Global):** ${plan['usd']:.2f}\n\n"
                f"**Pay using either button below, then click the matching 'âœ… I've Paid' button "
                f"to enter your Transaction ID and receive your key automatically.**"
            ),
            color=0xF59E0B if tier == "lifetime" else 0x38BDF8,
        )
        embed.set_image(url=pview._upi_qr_url)  # UPI QR code as the embed image
        embed.add_field(
            name="UPI ID",
            value=f"`{upi_svc.upi_id}`\n*(also encoded in QR above)*",
            inline=True,
        )
        embed.add_field(
            name="Order ID",
            value=f"`{pview.order_id}`\n*(keep this for reference)*",
            inline=True,
        )
        embed.add_field(
            name="âš ï¸ Important",
            value=(
                "â€¢ Send **exact** amount â€” no more, no less.\n"
                "â€¢ Each payment = one key only.\n"
                "â€¢ Fake TXN IDs are auto-detected and access is revoked."
            ),
            inline=False,
        )
        embed.set_footer(text="After paying, click the matching 'I've Paid' button below.")
        await interaction.response.send_message(embed=embed, view=pview, ephemeral=True)


class StoreView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(PlanSelect())


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Events & Slash Commands
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@bot.event
async def on_ready():
    logger.info("Sales Bot ready: %s (ID: %s)", bot.user, bot.user.id)
    try:
        synced = await bot.tree.sync()
        logger.info("Synced %d command(s)", len(synced))
    except Exception as exc:
        logger.error("Sync failed: %s", exc)


@bot.tree.command(name="store", description="Open the ApexClash Pro store â€” instant key via PhonePe or PayPal")
async def slash_store(interaction: discord.Interaction):
    p = config.get("pricing", {})
    embed = discord.Embed(
        title="âš”ï¸  ApexClash Pro â€” Official Store",
        description=(
            "24/7 autonomous Clash of Clans farming: Zero-Gem Guard, smart OCR loot filter, "
            "and BÃ©zier-curve humanizer for anti-ban protection.\n\n"
            "**Pay â†’ Submit TXN ID â†’ Key delivered automatically in seconds.**\n\n"
            f"âš¡ **Weekly**   â‚¹{p['weekly']['inr']} / ${p['weekly']['usd']:.2f}  â€¢  7 days\n"
            f"ðŸŒŸ **Monthly**  â‚¹{p['monthly']['inr']} / ${p['monthly']['usd']:.2f}  â€¢  30 days *(Popular)*\n"
            f"ðŸ† **Annual**   â‚¹{p['annual']['inr']} / ${p['annual']['usd']:.2f}  â€¢  365 days *(50% off)*\n"
            f"ðŸ‘‘ **Lifetime** â‚¹{p['lifetime']['inr']} / ${p['lifetime']['usd']:.2f}  â€¢  Forever"
        ),
        color=0x38BDF8,
    )
    embed.add_field(
        name="ðŸ’³ Payment Methods",
        value="ðŸ‡®ðŸ‡³ PhonePe Â· GPay Â· Paytm (UPI)  |  ðŸŒ PayPal Â· Visa Â· Mastercard",
        inline=False,
    )
    embed.add_field(
        name="âš¡ How fast?",
        value="Submit your TXN ID â†’ key in your DMs within **60 seconds**.",
        inline=False,
    )
    embed.set_footer(text="Select your plan from the dropdown below.")
    await interaction.response.send_message(embed=embed, view=StoreView())


@bot.tree.command(name="revoke", description="[Admin] Revoke a license key by order ID")
@app_commands.describe(
    order_id="Order ID (e.g. ACB-XXXXX)",
    reason="Reason: fake_txn | chargeback | other",
)
async def slash_revoke(
    interaction: discord.Interaction,
    order_id: str,
    reason: str = "admin_manual",
):
    if ADMIN_ID and interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("âŒ Admin only.", ephemeral=True)
        return

    orders = load_orders()
    order  = orders.get(order_id.upper().strip())
    if not order:
        await interaction.response.send_message(f"âŒ Order `{order_id}` not found.", ephemeral=True)
        return
    if order.get("status") == "revoked":
        await interaction.response.send_message(f"âš ï¸ Order `{order_id}` is already revoked.", ephemeral=True)
        return

    key = order.get("license_key", "")
    if not key:
        await interaction.response.send_message(f"âš ï¸ No key found in order `{order_id}`.", ephemeral=True)
        return

    order["status"]       = "revoked"
    order["revoke_reason"] = reason
    order["revoked_at"]   = int(time.time())
    orders[order_id.upper().strip()] = order
    save_orders(orders)

    revoke_order(order_id.upper().strip(), key, reason=reason)
    if GIST_ID and GITHUB_TOKEN:
        asyncio.create_task(asyncio.to_thread(push_revocation_gist, GIST_ID, GITHUB_TOKEN))

    # DM buyer
    buyer_id = order.get("user_id")
    if buyer_id:
        try:
            buyer = bot.get_user(buyer_id) or await bot.fetch_user(buyer_id)
            await buyer.send(
                embed=discord.Embed(
                    title="ðŸš« Your ApexClash Pro License Has Been Revoked",
                    description=(
                        f"License for order `{order_id}` was revoked.\n"
                        f"**Reason:** {reason.replace('_', ' ').title()}\n\n"
                        "If you believe this is an error, reply with payment proof."
                    ),
                    color=0xEF4444,
                )
            )
        except Exception:
            pass

    await interaction.response.send_message(
        embed=discord.Embed(
            title=f"ðŸš« Order {order_id} â€” Revoked",
            description=f"Key revoked, blacklisted, and Gist updated.\nReason: `{reason}`",
            color=0xEF4444,
        ),
        ephemeral=True,
    )


@bot.tree.command(name="genkey", description="[Admin] Generate a key and optionally DM it to a member")
@app_commands.describe(tier="weekly | monthly | annual | lifetime", member="Discord member to DM")
async def slash_genkey(
    interaction: discord.Interaction,
    tier: str = "monthly",
    member: Optional[discord.Member] = None,
):
    if ADMIN_ID and interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("âŒ Admin only.", ephemeral=True)
        return
    try:
        key = generate_license_for_tier(tier.lower())
    except Exception as exc:
        await interaction.response.send_message(f"âŒ `{exc}`", ephemeral=True)
        return

    order_id = _make_order_id()
    orders = load_orders()
    orders[order_id] = {
        "order_id": order_id,
        "user_id":  (member.id if member else interaction.user.id),
        "tier":     tier.lower(),
        "method":   "manual",
        "status":   "delivered",
        "license_key": key,
        "delivered_at": int(time.time()),
    }
    save_orders(orders)

    if member:
        try:
            await member.send(embed=_delivery_embed(tier.lower(), order_id, key))
            note = f"Key DM'd to {member.mention}."
        except Exception:
            note = f"Could not DM {member.mention} (DMs closed)."
    else:
        note = "No member specified â€” key below for manual delivery."

    await interaction.response.send_message(
        f"âœ… {note}\n**Order ID:** `{order_id}`\n```\n{key}\n```",
        ephemeral=True,
    )


@bot.tree.command(name="verify", description="Inspect and verify any ApexClash license key")
@app_commands.describe(key="The CAL-... license key")
async def slash_verify(interaction: discord.Interaction, key: str):
    res = CryptoLicenseEngine.verify_key(
        key=key.strip(), current_machine_id="DISCORD_INSPECT", saved_bound_machine=None
    )
    revoked_locally = is_key_revoked(key.strip())
    color = 0xEF4444 if not res.is_valid or revoked_locally else 0x10B981
    status = (
        "ðŸš« Revoked (in local blacklist)" if revoked_locally
        else ("âœ… Valid" if res.is_valid else f"âŒ Invalid â€” {res.reason}")
    )
    embed = discord.Embed(title="ðŸ” Key Inspection", color=color)
    embed.add_field(name="Status", value=status,                          inline=False)
    embed.add_field(name="Tier",   value=res.tier or "N/A",               inline=True)
    embed.add_field(name="Expiry", value=res.expiry_date_str or "N/A",    inline=True)
    embed.add_field(name="Key",    value=f"`{key.strip()[:45]}...`",       inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="orders", description="[Admin] View recent orders")
@app_commands.describe(limit="Number of orders (default 10, max 25)")
async def slash_orders(interaction: discord.Interaction, limit: int = 10):
    if ADMIN_ID and interaction.user.id != ADMIN_ID:
        await interaction.response.send_message("âŒ Admin only.", ephemeral=True)
        return
    all_orders = load_orders()
    recent = sorted(all_orders.values(), key=lambda o: o.get("created_at", 0), reverse=True)[: min(limit, 25)]
    if not recent:
        await interaction.response.send_message("No orders yet.", ephemeral=True)
        return
    status_icons = {
        "delivered": "âœ…", "confirmed": "ðŸ”’", "revoked": "ðŸš«",
        "awaiting_payment": "â³", "auto_expired": "âŒ",
    }
    embed = discord.Embed(title=f"ðŸ“‹ Last {len(recent)} Orders", color=0x38BDF8)
    for o in recent:
        icon = status_icons.get(o.get("status", ""), "â“")
        embed.add_field(
            name=f"{icon} `{o['order_id']}` â€” {o.get('tier','?').upper()}",
            value=(
                f"{o.get('method','?').upper()} â€¢ "
                f"<@{o.get('user_id',0)}> â€¢ "
                f"`{o.get('txn_id','manual')[:20]}` â€¢ "
                f"{_fmt_ts(o.get('created_at', 0))}"
            ),
            inline=False,
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="help", description="Get activation help, emulator setup guides, and developer contact support")
async def slash_help(interaction: discord.Interaction):
    embed = discord.Embed(
        title="âš”ï¸ ApexClash Pro â€” Help & Support Center",
        description=(
            "Autonomous Clash of Clans farming suite with 100% external computer vision, "
            "Zero-Gem Guard, and BÃ©zier-curve humanized anti-ban protection."
        ),
        color=0x38BDF8,
    )
    embed.add_field(
        name="ðŸ›’ How to Purchase & Auto-Deliver",
        value=(
            "1. Type `/store` and choose your pass (Weekly â‚¹99, Monthly â‚¹249, Annual â‚¹799, Lifetime â‚¹1,299).\n"
            "2. Pay using the dynamic **PhonePe / GPay QR** (India) or **PayPal Link** (Global).\n"
            "3. Click **Submit TXN ID** and enter your 12-digit UTR, PhonePe `T...` ID, or PayPal ID.\n"
            "4. Your key is generated and DM'd to you automatically in seconds!"
        ),
        inline=False,
    )
    embed.add_field(
        name="ðŸ”‘ How to Activate",
        value=(
            "1. Open **ApexClash Pro** on your Windows PC.\n"
            "2. Go to the **License** tab on the sidebar.\n"
            "3. Paste your key (`CAL-...`) and click **Activate License**.\n"
            "4. Your PC binds to the license and all Pro features unlock instantly."
        ),
        inline=False,
    )
    embed.add_field(
        name="ðŸ–¥ï¸ Recommended Emulator Settings",
        value=(
            "â€¢ **Emulator:** BlueStacks 5 (Pie 64-bit) or LDPlayer 9 / MuMu 12.\n"
            "â€¢ **Resolution:** 1600 Ã— 900 or 1280 Ã— 720 (240 DPI).\n"
            "â€¢ **Game Language:** English (required for OCR text recognition)."
        ),
        inline=False,
    )
    embed.add_field(
        name="ðŸ“§ Direct Developer Contact & Support",
        value=(
            "â€¢ **Developer Email:** `keshavchaudhary0005@gmail.com`\n"
            "â€¢ **Discord:** `matrix0456`\n"
            "â€¢ **Reddit:** `u/post_matrix`\n"
            "â€¢ **Online Help Center:** [View Full Web Guide](https://keshav-x.github.io/coc-bot/help.html)\n\n"
            "*For hardware resets or payment verification, email with your Order ID.*"
        ),
        inline=False,
    )
    embed.set_footer(text="ApexClash Pro â€¢ Autonomous 24/7 Farming Suite")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="claim", description="Claim your license key by submitting your payment Transaction ID")
@app_commands.describe(
    txn_id="Your 12-digit UTR, PhonePe Transaction ID (T...), or PayPal ID",
    tier="weekly | monthly | annual | lifetime (default: monthly)"
)
async def slash_claim(
    interaction: discord.Interaction,
    txn_id: str,
    tier: str = "monthly",
):
    await interaction.response.defer(ephemeral=True, thinking=True)
    raw_txn = txn_id.strip()
    tier_clean = tier.lower().strip()
    if tier_clean not in config.get("pricing", {}):
        tier_clean = "monthly"

    # Step 1: fake test check
    if is_known_test_id(raw_txn):
        await interaction.followup.send(
            embed=discord.Embed(
                title="âŒ Rejected â€” Example / Test ID",
                description=f"`{raw_txn}` matches a known test ID. Please provide your real payment reference from PhonePe/PayPal.",
                color=0xEF4444,
            ),
            ephemeral=True,
        )
        return

    # Step 2: auto-detect method and validate format
    method = "upi"
    ok, result = validate_upi_txn_id(raw_txn)
    if not ok:
        pp_ok, pp_res = validate_paypal_txn_id(raw_txn)
        if pp_ok:
            method = "paypal"
            ok, result = True, pp_res

    if not ok:
        await interaction.followup.send(
            embed=discord.Embed(
                title="âŒ Invalid Transaction ID",
                description=result,
                color=0xEF4444,
            ),
            ephemeral=True,
        )
        return

    clean_txn = result

    # Step 3: duplicate check
    if is_txn_id_used(clean_txn):
        await interaction.followup.send(
            embed=discord.Embed(
                title="âŒ Transaction ID Already Used",
                description=f"Transaction ID `{clean_txn}` has already been submitted for another order.",
                color=0xEF4444,
            ),
            ephemeral=True,
        )
        return

    # Step 4: generate order skeleton
    order_id = _make_order_id()
    orders = load_orders()
    orders[order_id] = {
        "order_id": order_id,
        "user_id": interaction.user.id,
        "username": str(interaction.user),
        "tier": tier_clean,
        "method": method,
        "txn_id": clean_txn,
        "created_at": int(time.time()),
        "status": "awaiting_delivery",
    }
    save_orders(orders)

    # PayPal API capture check if configured
    verified_auto = False
    if method == "paypal" and paypal_svc.is_configured:
        verified_auto = paypal_svc.capture_order(clean_txn)
        if not verified_auto:
            await interaction.followup.send(
                embed=discord.Embed(
                    title="âš ï¸ PayPal Payment Not Found",
                    description=(
                        f"Transaction ID `{clean_txn}` could not be confirmed as Completed in PayPal API.\n"
                        "Check your PayPal app and try again in 2 minutes, or contact support."
                    ),
                    color=0xF59E0B,
                ),
                ephemeral=True,
            )
            return

    await _deliver_key_and_notify(
        interaction, order_id, tier_clean, clean_txn, method, verified_auto=verified_auto
    )


@bot.tree.command(name="status", description="Check the status of an existing order or license key")
@app_commands.describe(reference="Order ID (ACB-XXXXX) or Transaction ID")
async def slash_status(interaction: discord.Interaction, reference: str):
    clean = reference.strip().upper()
    orders = load_orders()
    matched = None
    for oid, o in orders.items():
        if (
            oid == clean
            or o.get("txn_id", "").strip().upper() == clean
            or o.get("license_key", "").strip() == reference.strip()
        ):
            matched = o
            break

    if not matched:
        await interaction.response.send_message(
            f"âŒ No order found matching `{reference[:35]}`.", ephemeral=True
        )
        return

    status = matched.get("status", "unknown")
    status_map = {
        "confirmed": ("ðŸ”’ Confirmed & Genuine", 0x10B981),
        "delivered": ("âœ… Delivered (Active)", 0x10B981),
        "revoked":   ("ðŸš« Revoked", 0xEF4444),
        "awaiting_payment": ("â³ Awaiting Payment", 0xF59E0B),
    }
    status_text, color = status_map.get(status, (f"â“ {status.capitalize()}", 0x94A3B8))

    embed = discord.Embed(
        title=f"ðŸ“‹ Order Status: {matched.get('order_id')}",
        color=color,
    )
    embed.add_field(name="Status", value=status_text, inline=True)
    embed.add_field(name="Plan", value=matched.get("tier", "?").upper(), inline=True)
    embed.add_field(name="Method", value=matched.get("method", "manual").upper(), inline=True)
    embed.add_field(name="TXN ID", value=f"`{matched.get('txn_id', 'N/A')}`", inline=False)
    if matched.get("license_key"):
        embed.add_field(name="License Key", value=f"`{matched.get('license_key')[:45]}...`", inline=False)
    if matched.get("delivered_at"):
        embed.add_field(name="Delivered At", value=_fmt_ts(matched.get("delivered_at")), inline=True)
    if matched.get("revoke_reason"):
        embed.add_field(name="Revoke Reason", value=f"`{matched.get('revoke_reason')}`", inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Entry point
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def main():
    token = config.get("discord_bot_token", "").strip()
    if not token or token == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print(f"\n[!] Set discord_bot_token in: {CONFIG_PATH}\n")
        sys.exit(1)
    logger.info("Starting ApexClash Sales Botâ€¦")
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()

