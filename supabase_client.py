"""
supabase_client.py
Responsabilité unique : communication avec la base de données Supabase.
"""

import logging
import os
import sys

import requests

log = logging.getLogger(__name__)

BASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
API_KEY = os.environ.get("SUPABASE_KEY", "")

FR_TO_EN_DAYS = {
    "lundi": "monday",
    "mardi": "tuesday",
    "mercredi": "wednesday",
    "jeudi": "thursday",
    "vendredi": "friday",
    "samedi": "saturday",
    "dimanche": "sunday",
}


def _check_env() -> None:
    if not BASE_URL or not API_KEY:
        log.error("Les variables d'environnement SUPABASE_URL et SUPABASE_KEY doivent être définies.")
        sys.exit(1)


def _headers() -> dict:
    _check_env()
    return {
        "apikey": API_KEY,
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def _url(path: str) -> str:
    _check_env()
    return f"{BASE_URL}/rest/v1/{path}"


def load_users() -> list:
    """Charge tous les users depuis Supabase et normalise les jours en anglais."""
    resp = requests.get(_url("users"), headers=_headers(), timeout=10)
    resp.raise_for_status()
    users = resp.json()

    for user in users:
        for rule in user.get("slots_config", []):
            rule["days"] = [
                FR_TO_EN_DAYS.get(d.lower(), d.lower()) for d in rule.get("days", [])
            ]
        if user.get("slots_sent") is None:
            user["slots_sent"] = []

    log.info("%d user(s) chargé(s) depuis Supabase.", len(users))
    return users


def save_user_state(user_id: int, slots_sent: list) -> None:
    """Met à jour slots_sent pour un user dans Supabase."""
    resp = requests.patch(
        _url(f"users?id=eq.{user_id}"),
        headers=_headers(),
        json={"slots_sent": slots_sent},
        timeout=10,
    )
    resp.raise_for_status()
