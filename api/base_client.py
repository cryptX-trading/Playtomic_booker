"""
api/base_client.py
Interface abstraite que tous les clients de plateforme doivent implémenter.
"""

from abc import ABC, abstractmethod


class PlatformClient(ABC):
    """
    Interface commune pour les clients de réservation sportive.

    Chaque client retourne une liste de créneaux normalisés :
    [
        {
            "start_time": "HH:MM",        # heure locale Paris
            "date":        "YYYY-MM-DD",   # date locale Paris
            "duration":    90,             # durée en minutes
            "price":       {"amount": "50.00", "currency": "EUR"}  # ou {}
        },
        ...
    ]
    """

    @abstractmethod
    def get_availability(self, venue_id: str, activity: str, date_str: str) -> list:
        """
        Retourne les créneaux disponibles pour un club sur une journée.

        Args:
            venue_id:  Identifiant du club sur la plateforme.
            activity:  Activité ciblée (ex: "padel", "PADEL").
            date_str:  Date au format "YYYY-MM-DD".

        Returns:
            Liste de créneaux normalisés (voir format ci-dessus).
        """

    @abstractmethod
    def get_booking_url(self, venue_id: str, activity: str) -> str:
        """Retourne l'URL de réservation pour un club."""
