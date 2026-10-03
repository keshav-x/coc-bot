# 🤖 ApexClash Pro — Automated Discord Sales Bot (v3)

An automated sales bot that accepts **PhonePe / Indian UPI** (₹) and **Global PayPal / Cards** ($), validates transaction IDs, delivers cryptographically signed Ed25519 license keys in seconds, and provides **one-click revocation** if a payment is fraudulent.

---

## ⚡ How The New Flow Works

```
1. Customer runs /store in Discord (or clicks pinned embed)
                  │
                  ▼
2. Chooses plan (Weekly ₹99 / Monthly ₹249 / Annual ₹799 / Lifetime ₹1,299)
                  │
                  ▼
3. Bot displays dynamic PhonePe/GPay QR code + direct PayPal link
                  │
                  ▼
4. Buyer pays and clicks "Paid with PhonePe/UPI" or "Paid with PayPal"
                  │
                  ▼
5. Buyer pastes Transaction ID in modal (12-digit UTR, PhonePe T..., or PayPal ID)
                  │
                  ├── Validation Checks:
                  │   ✓ Format validation (12-digit UTR / PhonePe T... / 17-char PayPal)
                  │   ✓ Duplicate prevention (rejects already-used IDs)
                  │   ✓ Fake ID pattern detection (rejects 000000..., 123456..., repetitive test strings)
                  │   ✓ Optional PayPal Captures API auto-verification
                  │
                  ▼
6. ⚡ Key is generated & delivered automatically to the buyer in Discord DMs!
                  │
                  ▼
7. Admin receives a DM with order details, buyer info, and TXN ID:
                  ├── [ ✅ Confirm — Payment Genuine ]  ➔ Marks order confirmed
                  └── [ 🚫 Revoke — Fake / Fraudulent ] ➔ 1-click instant revocation
```

---

## 🛡️ Revocation & Anti-Fraud Architecture

1. **Format & Duplicate Filter:**
   - Any duplicate or fake pattern is blocked before a key is ever minted.
2. **Instant Delivery + Admin DM:**
   - Buyer gets their key right away (no waiting or losing sales).
   - Admin receives a Discord DM with the customer name, order ID, amount, and TXN ID.
3. **One-Click Revoke:**
   - Admin checks their PhonePe / PayPal notification.
   - If fake or unpaid, admin taps `[ 🚫 Revoke ]` in Discord (or runs `/revoke <order_id>`).
   - The key is instantly blacklisted in `revoked_keys.json`, user is notified, and (optionally) pushed to your GitHub Gist.
4. **App Enforcement:**
   - The desktop bot checks the revocation list on validation. Revoked keys are rejected immediately.

---

## 🚀 Quick Setup (Under 5 Minutes)

### Step 1: Install Dependencies
```bash
pip install discord.py requests
```

### Step 2: Create a Discord Bot
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application** ➔ Name it `ApexClash Store`.
3. Go to **Bot** on the left menu:
   - Click **Reset Token** ➔ Copy your Bot Token.
   - Under **Privileged Gateway Intents**, turn ON:
     - ✅ **Message Content Intent**
4. Go to **OAuth2 ➔ URL Generator**:
   - Select Scopes: `bot`, `applications.commands`
   - Select Permissions: `Send Messages`, `Embed Links`, `Attach Files`, `Use Slash Commands`
   - Open the generated URL to invite the bot to your Discord server.

### Step 3: Configure `sales_bot/config.json`
Copy `sales_bot/config.example.json` to `sales_bot/config.json` and fill in:
```json
{
  "discord_bot_token": "YOUR_DISCORD_BOT_TOKEN_HERE",
  "admin_discord_id": 123456789012345678,
  "phonepe_upi_id": "cockingkeshav@ybl",
  "payee_name": "ApexClash Pro",
  "paypal_me_url": "https://paypal.me/cockingkeshav",
  "paypal_client_id": "",
  "paypal_client_secret": "",
  "paypal_mode": "live",
  "revocation_gist_id": "",
  "github_token": "",
  "auto_revoke_unconfirmed": false
}
```
> **Tip to find your Discord ID:** In Discord Settings ➔ Advanced ➔ Enable Developer Mode. Right-click your profile and select **Copy User ID**.

### Step 4: Run the Bot
```bash
python sales_bot/sales_bot.py
```

---

## 🛠️ Bot Commands

* `/store` — Displays the interactive store embed with plan dropdown and pay buttons.
* `/claim txn_id:<id> [tier:monthly]` — Claim a license key immediately by submitting your Transaction ID.
* `/status reference:<order_id_or_txn>` — Check the live status of an order, payment, or key.
* `/help` — Displays setup guides, activation steps, and developer email support.
* `/revoke order_id:ACB-XXXXX reason:fake_txn` — [Admin] Instantly revokes a license, blacklists it, and notifies the user.
* `/genkey tier:monthly [member:@user]` — [Admin] Manually generates an Ed25519 key (and optionally DMs it).
* `/verify key:CAL-...` — Inspect any key: view tier, expiry date, validity, and revocation status.
* `/orders` — [Admin] View the last 10-25 orders, amounts, and statuses.
