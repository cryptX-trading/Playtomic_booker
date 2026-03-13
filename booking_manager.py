"""
booking_manager.py
Orchestrateur principal : charge la config, interroge l'API Playtomic via
playtomic_client, filtre les créneaux désirés et envoie des notifications
Telegram pour les nouvelles disponibilités.
"""

import json
import logging
import os
import sys
from datetime import date, datetime, timedelta

import requests
import yaml

import playtomic_client

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
STATE_FILE = "state.json"
CONFIG_FILE = "config.yaml"

# Mapping jours français → anglais (strftime renvoie l'anglais)
FR_TO_EN_DAYS = {
    "lundi": "monday",
    "mardi": "tuesday",
    "mercredi": "wednesday",
    "jeudi": "thursday",
    "vendredi": "friday",
    "samedi": "saturday",
    "dimanche": "sunday",
}

FR_DAY_NAMES = {
    "monday": "Lundi",
    "tuesday": "Mardi",
    "wednesday": "Mercredi",
    "thursday": "Jeudi",
    "friday": "Vendredi",
    "saturday": "Samedi",
    "sunday": "Dimanche",
}

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # Injecter les secrets depuis les variables d'environnement
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        log.error(
            "Les variables d'environnement TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID "
            "doivent être définies."
        )
        sys.exit(1)

    config.setdefault("telegram", {})
    config["telegram"]["bot_token"] = bot_token
    config["telegram"]["chat_id"] = chat_id

    # Normaliser les jours en anglais minuscule
    for slot_rule in config.get("desired_slots", []):
        slot_rule["days"] = [
            FR_TO_EN_DAYS.get(d.lower(), d.lower()) for d in slot_rule["days"]
        ]

    return config


# ---------------------------------------------------------------------------
# State (anti-spam : évite de notifier deux fois le même créneau)
# ---------------------------------------------------------------------------

def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"notified": []}


def save_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def purge_old_entries(notified_keys: set, today: date) -> set:
    """Supprime les entrées dont la date est passée."""
    cutoff = (today - timedelta(days=1)).isoformat()
    return {k for k in notified_keys if k.split("|")[1] >= cutoff}


def make_key(tenant_id: str, date_str: str, start_time: str) -> str:
    return f"{tenant_id}|{date_str}|{start_time}"


# ---------------------------------------------------------------------------
# Filtrage
# ---------------------------------------------------------------------------

def is_desired(
    start_time: str,
    duration: int,
    day_of_week: str,
    desired_slots: list,
) -> bool:
    """Renvoie True si le créneau correspond à un des règles désirées."""
    for rule in desired_slots:
        if day_of_week.lower() in rule["days"]:
            if start_time in rule.get("start_times", []):
                if duration >= rule.get("duration_min", 0):
                    return True
    return False


# ---------------------------------------------------------------------------
# Notification Telegram
# ---------------------------------------------------------------------------

def send_telegram(bot_token: str, chat_id: str, message: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=10,
        )
        resp.raise_for_status()
        log.info("Notification Telegram envoyée.")
    except requests.RequestException as e:
        log.error("Erreur lors de l'envoi de la notification Telegram : %s", e)


def format_message(venue_name: str, date_str: str, start_time: str, duration: int, price: dict) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_en = dt.strftime("%A").lower()
    day_fr = FR_DAY_NAMES.get(day_en, day_en.capitalize())
    # Format : "Jeudi 19 mars"
    month_fr = [
        "", "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    ]
    date_label = f"{day_fr} {dt.day} {month_fr[dt.month]}"

    price_str = ""
    if price:
        amount = price.get("amount", "")
        currency = price.get("currency", "")
        if amount:
            price_str = f"\n💶 {amount} {currency}"

    return (
        f"🎾 <b>Terrain disponible !</b>\n"
        f"📍 {venue_name}\n"
        f"📅 {date_label} à {start_time} ({duration} min)"
        f"{price_str}\n"
        f"🔗 https://app.playtomic.io"
    )


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------

def main() -> None:
    config = load_config()
    state = load_state()
    notified_keys: set = set(state.get("notified", []))

    today = date.today()
    days_ahead = config.get("days_ahead", 7)
    sport_id = config.get("sport_id", "PADEL")
    desired_slots = config.get("desired_slots", [])

    bot_token = config["telegram"]["bot_token"]
    chat_id = config["telegram"]["chat_id"]

    new_notifications = 0

    for venue in config.get("venues", []):
        venue_name = venue["name"]
        tenant_id = venue["tenant_id"]

        for offset in range(days_ahead):
            check_date = today + timedelta(days=offset)
            date_str = check_date.isoformat()
            day_of_week = check_date.strftime("%A").lower()  # "monday", etc.

            try:
                resources = playtomic_client.get_availability(tenant_id, sport_id, date_str)
            except Exception as e:
                log.warning("Erreur API pour %s le %s : %s", venue_name, date_str, e)
                continue

            for resource in resources:
                for slot in resource.get("slots", []):
                    start_time = slot.get("start_time", "")
                    duration = slot.get("duration", 0)
                    price = slot.get("price", {})

                    if not is_desired(start_time, duration, day_of_week, desired_slots):
                        continue

                    key = make_key(tenant_id, date_str, start_time)
                    if key in notified_keys:
                        log.debug("Créneau déjà notifié : %s", key)
                        continue

                    log.info("Nouveau créneau : %s %s à %s", venue_name, date_str, start_time)
                    message = format_message(venue_name, date_str, start_time, duration, price)
                    send_telegram(bot_token, chat_id, message)
                    notified_keys.add(key)
                    new_notifications += 1

    log.info("%d nouvelle(s) notification(s) envoyée(s).", new_notifications)

    # Purge des créneaux passés et sauvegarde du state
    notified_keys = purge_old_entries(notified_keys, today)
    save_state({"notified": sorted(notified_keys)})


if __name__ == "__main__":
    main()
