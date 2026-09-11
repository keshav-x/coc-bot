"""UI constants ported from the legacy theme module."""

ATTACK_STRATEGIES: dict[str, int] = {
    "Sneaky Goblins": 1,
    "Super Minions": 2,
    "Valkyries": 3,
    "Edrags": 4,
}

BUILDER_BASE_ATTACK_STRATEGIES: dict[str, int] = {
    "Baby Dragons": 5,
    "Night Witches": 6,
}

BUILDER_BASE_ATTACK_STRATEGIES_UNDER_DEV: tuple[str, ...] = ()

BUILDER_BASE_PRIORITISE_LABELS = ("Gold", "Both", "Elixir")

PLAN_PRICE_WEEKLY = "$1.00 / week"
PLAN_PRICE_MONTHLY = "$3.00 / month"
PLAN_PRICE_ANNUAL = "$10.00 / year"
PLAN_PRICE_LIFETIME = "$15.00 lifetime"
PLAN_DEVICE_LIMIT = "1 Device (Hardware Bound)"
PLAN_TRIAL_HOURS = 2
PLAN_DESCRIPTION = "Cheap passes ($1/wk, $3/mo, $10/yr, $15 lifetime) with instant activation and 2-Hour Free Trial"

CONTACT_EMAIL = "cockingkeshav@gmail.com"
CONTACT_REDDIT = "post_matrix"
CONTACT_DISCORD = "matrix0456"

STRIPE_LIFETIME_URL = "https://clashautoloot.duckdns.org/v1/checkout/lifetime"
SUBSCRIBE_CHECKOUT_URL = "https://clashautoloot.duckdns.org/v1/checkout/subscribe"

PORTAL_USER_ERRORS: dict[str, str] = {
    "empty": "Enter your license key in the field above first.",
    "invalid_format": "That license key is not formatted correctly.",
    "not_found": "That license key was not found.",
    "revoked": "This license key has been revoked.",
    "machine_mismatch": "This license key is paired to another PC, so billing cannot be opened here.",
    "no_billing_account": "No Stripe billing account is linked to this key — it was likely issued manually. Contact support and we'll sort out your billing.",
    "portal_not_configured": "Billing management is not available yet. Contact support.",
    "network_unreachable": "Could not reach the license server. Check your internet and try again.",
    "failed": "The server declined the request. Try again or contact support.",
}

UNPAIR_USER_ERRORS: dict[str, str] = {
    "empty": "No license key was entered.",
    "invalid_format": "That license key is not formatted correctly.",
    "not_found": "That license key was not found.",
    "revoked": "This license key has been revoked.",
    "machine_mismatch": "This PC was not paired with this key, so nothing was changed on the server.",
    "not_bound": "No machine was paired yet; your local saved key will still be removed.",
    "network_unreachable": "Could not reach the license server. Check your internet and try again.",
    "failed": "The server declined the request. Try again or contact support.",
}
