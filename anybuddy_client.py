"""
anybuddy_client.py
Responsabilité unique : communication avec l'API publique Anybuddy.
"""

import requests

BASE_URL = "https://api-booking.anybuddyapp.com/v1"
DEFAULT_TIMEOUT = 10


def get_availability(center_id: str, activity: str, date_str: str) -> list:
    """
    Retourne les créneaux disponibles pour un club Anybuddy sur une journée.

    Args:
        center_id: Identifiant du club sur Anybuddy (ex: "paris-padel").
        activity:  Activité ciblée, ex: "padel".
        date_str:  Date au format "YYYY-MM-DD".

    Returns:
        Liste de timeSlots réservables, format normalisé :
        [
            {
                "start_time": "HH:MM",   # heure locale Paris
                "duration": 90,
                "price": {"amount": "50.00", "currency": "EUR"}
            },
            ...
        ]
    """
    url = f"{BASE_URL}/centers/{center_id}/availabilities"
    params = {"date": date_str, "activity": activity}

    response = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT,
                            headers={"Accept": "application/json"})
    response.raise_for_status()

    data = response.json()
    time_slots = data.get("availabilities", {}).get("timeSlots", [])

    slots = []
    for slot in time_slots:
        if not slot.get("isReservable", False):
            continue

        # startDate format : "2026-03-24T10:00"  (heure locale Paris)
        start_date = slot.get("startDate", "")
        start_time = start_date[11:16] if len(start_date) >= 16 else ""
        duration = slot.get("duration", 0)

        # Prix depuis la première activité disponible
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
            "duration": duration,
            "price": price,
        })

    return slots
