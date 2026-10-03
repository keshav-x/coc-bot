"""UPI Payment Link & Dynamic QR Code Generator for PhonePe / GPay / Paytm."""

from __future__ import annotations

import urllib.parse
from typing import Dict


class UPIService:
    def __init__(self, upi_id: str, payee_name: str = "ApexClash Bot") -> None:
        self.upi_id = upi_id
        self.payee_name = payee_name

    def build_upi_uri(self, amount: int, order_id: str) -> str:
        """Constructs a standard UPI deep-link URI.
        Format: upi://pay?pa=...&pn=...&am=...&cu=INR&tn=...
        """
        params = {
            "pa": self.upi_id,
            "pn": self.payee_name,
            "am": str(amount),
            "cu": "INR",
            "tn": f"ApexClash-{order_id}",
        }
        query_str = urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
        return f"upi://pay?{query_str}"

    def build_qr_url(self, amount: int, order_id: str) -> str:
        """Generates a high-resolution QR Code image URL for Discord embeds.
        Can be scanned directly by PhonePe, Google Pay, Paytm, or BHIM.
        """
        upi_uri = self.build_upi_uri(amount, order_id)
        encoded_data = urllib.parse.quote(upi_uri)
        return f"https://api.qrserver.com/v1/create-qr-code/?size=350x350&data={encoded_data}&format=png"
