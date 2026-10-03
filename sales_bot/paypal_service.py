"""PayPal v2 Orders API client for automated order creation and capture."""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, Optional, Tuple
import requests

logger = logging.getLogger("PayPalService")


class PayPalService:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        mode: str = "sandbox",
    ) -> None:
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.mode = mode.lower()
        self.base_url = (
            "https://api-m.paypal.com"
            if self.mode == "live"
            else "https://api-m.sandbox.paypal.com"
        )
        self._access_token: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_access_token(self) -> Optional[str]:
        if not self.is_configured:
            return None
        auth_header = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode("utf-8")
        ).decode("ascii")

        try:
            resp = requests.post(
                f"{self.base_url}/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                self._access_token = data.get("access_token")
                return self._access_token
            logger.error("Failed to authenticate with PayPal: %s", resp.text)
        except Exception as exc:
            logger.error("PayPal authentication error: %s", exc)
        return None

    def create_order(
        self,
        order_id: str,
        item_name: str,
        amount_usd: float,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Creates an order and returns (paypal_order_id, approve_url)."""
        token = self._get_access_token()
        if not token:
            return None, None

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": order_id,
                    "description": item_name,
                    "amount": {
                        "currency_code": "USD",
                        "value": f"{amount_usd:.2f}",
                    },
                }
            ],
            "application_context": {
                "brand_name": "ApexClash Pro",
                "user_action": "PAY_NOW",
            },
        }

        try:
            resp = requests.post(
                f"{self.base_url}/v2/checkout/orders",
                headers=headers,
                json=payload,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                order_id_pp = data.get("id")
                approve_url = None
                for link in data.get("links", []):
                    if link.get("rel") == "approve":
                        approve_url = link.get("href")
                        break
                return order_id_pp, approve_url
            logger.error("PayPal create order failed: %s", resp.text)
        except Exception as exc:
            logger.error("PayPal order creation exception: %s", exc)

        return None, None

    def capture_order(self, paypal_order_id: str) -> bool:
        """Captures a paid PayPal order. Returns True if COMPLETED."""
        token = self._get_access_token()
        if not token:
            return False

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.post(
                f"{self.base_url}/v2/checkout/orders/{paypal_order_id}/capture",
                headers=headers,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                status = data.get("status")
                return status == "COMPLETED"
            logger.warning("PayPal capture response %s: %s", resp.status_code, resp.text)
        except Exception as exc:
            logger.error("PayPal capture error: %s", exc)
        return False
