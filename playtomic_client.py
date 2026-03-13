"""
playtomic_client.py
Responsabilité unique : communication avec l'API publique Playtomic.
"""

import requests

AVAILABILITY_URL = "https://api.playtomic.io/v1/availability"
DEFAULT_TIMEOUT = 10  # secondes


def get_availability(tenant_id: str, sport_id: str, date_str: str) -> list:
    """
    Retourne les créneaux disponibles pour un club/venue sur une journée donnée.

    Args:
        tenant_id: Identifiant UUID du club sur Playtomic.
        sport_id:  Sport ciblé, ex: "PADEL".
        date_str:  Date au format "YYYY-MM-DD".

    Returns:
        Liste de resources (terrains) avec leurs slots disponibles.
        Format attendu :
        [
            {
                "resource_id": "...",
                "start_date": "YYYY-MM-DD",
                "slots": [
                    {
                        "start_time": "HH:MM",
                        "duration": 90,
                        "price": {"amount": 24.0, "currency": "EUR"}
                    },
                    ...
                ]
            },
            ...
        ]

    Raises:
        requests.HTTPError: Si l'API retourne un code d'erreur HTTP.
        requests.Timeout: Si la requête dépasse le timeout.
        requests.RequestException: Pour toute autre erreur réseau.
    """
    params = {
        "sport_id": sport_id,
        "tenant_id": tenant_id,
        "start_min": f"{date_str}T00:00:00",
        "start_max": f"{date_str}T23:59:59",
    }

    response = requests.get(AVAILABILITY_URL, params=params, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    return response.json()
