"""
api/anybuddy_client.py
Client Anybuddy — implémente PlatformClient.
Les heures retournées par l'API sont déjà en heure locale Paris.
"""

import requests

from api.base_client import PlatformClient

_BASE_URL = "https://api-booking.anybuddyapp.com/v1"
_TIMEOUT = 10


class AnybuddyClient(PlatformClient):

    def get_availability(self, venue_id: str, activity: str, date_str: str) -> list:
        url = f"{_BASE_URL}/centers/{venue_id}/availabilities"
        resp = requests.get(
            url,
            params={"date": date_str, "activity": activity},
            headers={"Accept": "application/json"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()

        time_slots = resp.json().get("availabilities", {}).get("timeSlots", [])
        slots = []
        for slot in time_slots:
            if not slot.get("isReservable", False):
                continue

            # startDate format : "2026-03-24T10:00" (heure locale Paris)
            start_date = slot.get("startDate", "")
            start_time = start_date[11:16] if len(start_date) >= 16 else ""
            date = start_date[:10] if len(start_date) >= 10 else date_str

            price = {}
            activities = slot.get("activities", [])
            if activities:
                a = activities[0]
                cents = a.get("priceCents", 0)
                currency = a.get("currencyCode", "EUR")
                if cents:
                    price = {"amount": f"{cents / 100:.2f}", "currency": currency}

            slots.append({
                "start_time": start_time,
                "date": date,
                "duration": slot.get("duration", 0),
                "price": price,
            })
        return slots

    def get_booking_url(self, venue_id: str, activity: str) -> str:
        return f"https://www.anybuddyapp.com/club-{venue_id}/reservation/{activity}"
