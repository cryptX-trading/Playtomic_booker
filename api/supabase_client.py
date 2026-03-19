"""
api/supabase.py
Client Supabase — gestion de la base de données utilisateurs.
"""

import logging
import os
import sys

import requests

log = logging.getLogger(__name__)

_FR_TO_EN_DAYS = {
    "lundi": "monday",
    "mardi": "tuesday",
    "mercredi": "wednesday",
    "jeudi": "thursday",
    "vendredi": "friday",
    "samedi": "saturday",
    "dimanche": "sunday",
}


class SupabaseClient:

    def __init__(self) -> None:
        self._base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self._key = os.environ.get("SUPABASE_KEY", "")
        if not self._base_url or not self._key:
            log.error("Les variables SUPABASE_URL et SUPABASE_KEY doivent être définies.")
            sys.exit(1)

    def _headers(self) -> dict:
        return {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self._base_url}/rest/v1/{path}"

    def load_users(self) -> list:
        """Charge tous les users et normalise les jours en anglais."""
        resp = requests.get(self._url("users"), headers=self._headers(), timeout=10)
        resp.raise_for_status()
        users = resp.json()

        for user in users:
            for rule in user.get("slots_config", []):
                rule["days"] = [
                    _FR_TO_EN_DAYS.get(d.lower(), d.lower())
                    for d in rule.get("days", [])
                ]
            if user.get("slots_sent") is None:
                user["slots_sent"] = []

        log.info("%d user(s) chargé(s) depuis Supabase.", len(users))
        return users

    def save_user_state(self, user_id: int, slots_sent: list) -> None:
        """Met à jour slots_sent pour un user."""
        resp = requests.patch(
            self._url(f"users?id=eq.{user_id}"),
            headers=self._headers(),
            json={"slots_sent": slots_sent},
            timeout=10,
        )
        resp.raise_for_status()
