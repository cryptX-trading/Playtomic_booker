"""
api/playtomic_client.py
Client Playtomic — implémente PlatformClient.
Les heures retournées par l'API sont en UTC, converties en heure Paris.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from api.base_client import PlatformClient

_API_URL = "https://api.playtomic.io/v1/availability"
_PARIS_TZ = ZoneInfo("Europe/Paris")
_TIMEOUT = 10


class PlaytomicClient(PlatformClient):

    def get_availability(self, venue_id: str, activity: str, date_str: str) -> list:
        params = {
            "sport_id": activity,
            "tenant_id": venue_id,
            "start_min": f"{date_str}T00:00:00",
            "start_max": f"{date_str}T23:59:59",
        }
        resp = requests.get(_API_URL, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()

        slots = []
        for resource in resp.json():
            for slot in resource.get("slots", []):
                raw_time = slot.get("start_time", "")
                utc_dt = datetime.strptime(
                    f"{date_str}T{raw_time}", "%Y-%m-%dT%H:%M:%S"
                ).replace(tzinfo=ZoneInfo("UTC"))
                paris_dt = utc_dt.astimezone(_PARIS_TZ)

                price = {}
                raw_price = slot.get("price", {})
                if isinstance(raw_price, dict):
                    amount = raw_price.get("amount", "")
                    currency = raw_price.get("currency", "")
                    if amount:
                        price = {"amount": str(amount), "currency": currency}

                slots.append({
                    "start_time": paris_dt.strftime("%H:%M"),
                    "date": paris_dt.strftime("%Y-%m-%d"),
                    "duration": slot.get("duration", 0),
                    "price": price,
                })
        return slots

    def get_booking_url(self, venue_id: str, activity: str) -> str:
        return f"https://app.playtomic.io/tenant/{venue_id}"
