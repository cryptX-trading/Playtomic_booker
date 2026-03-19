"""
booking_manager.py
Orchestrateur principal : charge les users depuis Supabase, récupère les
disponibilités Playtomic (cache partagé), filtre par user et envoie des
notifications Telegram individuelles.
"""

import logging
import os
import sys
import time
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
CONFIG_FILE = "config.yaml"

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

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not bot_token:
        log.error("La variable d'environnement TELEGRAM_BOT_TOKEN doit être définie.")
        sys.exit(1)

    config["telegram_bot_token"] = bot_token
    return config


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------

def _supabase_headers() -> dict:
    key = os.environ.get("SUPABASE_KEY", "")
    if not key:
        log.error("La variable d'environnement SUPABASE_KEY doit être définie.")
        sys.exit(1)
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _supabase_url(path: str) -> str:
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base:
        log.error("La variable d'environnement SUPABASE_URL doit être définie.")
        sys.exit(1)
    return f"{base}/rest/v1/{path}"


def load_users() -> list:
    """Charge tous les users depuis Supabase."""
    resp = requests.get(
        _supabase_url("users"),
        headers=_supabase_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    users = resp.json()

    for user in users:
        # Normaliser les jours en anglais
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
        _supabase_url(f"users?id=eq.{user_id}"),
        headers=_supabase_headers(),
        json={"slots_sent": slots_sent},
        timeout=10,
    )
    resp.raise_for_status()


# ---------------------------------------------------------------------------
# Cache des disponibilités Playtomic
# ---------------------------------------------------------------------------

def fetch_all_availability(venues: list, days_ahead: int, sport_id: str) -> dict:
    """
    Récupère les dispos pour tous les clubs et toutes les dates.
    Retourne un dict : {(tenant_id, date_str): [slots enrichis]}
    """
    today = date.today()
    cache = {}

    for venue in venues:
        tenant_id = venue["tenant_id"]
        venue_name = venue["name"]
        log.info("--- Récupération dispo : %s ---", venue_name)

        for offset in range(days_ahead):
            check_date = today + timedelta(days=offset)
            date_str = check_date.isoformat()

            try:
                resources = playtomic_client.get_availability(tenant_id, sport_id, date_str)
                slots = []
                for resource in resources:
                    for slot in resource.get("slots", []):
                        slot["_tenant_id"] = tenant_id
                        slot["_venue_name"] = venue_name
                        slot["_date_str"] = date_str
                        slot["_day_of_week"] = check_date.strftime("%A").lower()
                        slots.append(slot)
                cache[(tenant_id, date_str)] = slots
                log.info("  %s : %d créneau(x) dispo", date_str, len(slots))
            except Exception as e:
                log.warning("Erreur API pour %s le %s : %s", venue_name, date_str, e)
                cache[(tenant_id, date_str)] = []

    return cache


# ---------------------------------------------------------------------------
# Filtrage
# ---------------------------------------------------------------------------

def is_desired(start_time: str, duration: int, day_of_week: str, slots_config: list) -> bool:
    for rule in slots_config:
        if day_of_week.lower() in rule["days"]:
            if start_time in rule.get("start_times", []):
                if duration >= rule.get("duration_min", 0):
                    return True
    return False


def make_key(tenant_id: str, date_str: str, start_time: str) -> str:
    return f"{tenant_id}|{date_str}|{start_time}"


def purge_old_entries(slots_sent: list, today: date) -> list:
    cutoff = (today - timedelta(days=1)).isoformat()
    return [k for k in slots_sent if k.split("|")[1] >= cutoff]


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
        log.info("  → Notification Telegram envoyée.")
    except requests.RequestException as e:
        log.error("  → Erreur Telegram : %s", e)


def format_message(venue_name: str, date_str: str, start_time: str, duration: int, price: dict, tenant_id: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_en = dt.strftime("%A").lower()
    day_fr = FR_DAY_NAMES.get(day_en, day_en.capitalize())
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

    booking_url = f"https://app.playtomic.io/tenant/{tenant_id}"

    return (
        f"🎾 <b>Terrain disponible !</b>\n"
        f"📍 {venue_name}\n"
        f"📅 {date_label} à {start_time} ({duration} min)"
        f"{price_str}\n"
        f"🔗 <a href=\"{booking_url}\">Réserver sur Playtomic</a>"
    )


# ---------------------------------------------------------------------------
# Check par user
# ---------------------------------------------------------------------------

def check_user(user: dict, availability_cache: dict, bot_token: str) -> list:
    """
    Filtre le cache selon la config du user, envoie les notifs Telegram.
    Retourne la liste mise à jour de slots_sent.
    """
    name = user["name"]
    chat_id = user["chat_id"]
    slots_config = user.get("slots_config", [])
    notified_keys = set(user.get("slots_sent", []))

    log.info("=== Check pour %s ===", name)

    if not slots_config:
        log.info("  Aucune config de créneaux pour %s, skip.", name)
        return list(notified_keys)

    new_notifications = 0
    matching_slots = []

    for slots in availability_cache.values():
        for slot in slots:
            start_time = slot.get("start_time", "")
            duration = slot.get("duration", 0)
            price = slot.get("price", {})
            tenant_id = slot["_tenant_id"]
            venue_name = slot["_venue_name"]
            date_str = slot["_date_str"]
            day_of_week = slot["_day_of_week"]

            if not is_desired(start_time, duration, day_of_week, slots_config):
                continue

            matching_slots.append(f"{venue_name} | {date_str} à {start_time} ({duration} min)")
            key = make_key(tenant_id, date_str, start_time)

            if key in notified_keys:
                continue

            log.info("  ✓ NOUVEAU CRÉNEAU : %s %s à %s (%d min)", venue_name, date_str, start_time, duration)
            message = format_message(venue_name, date_str, start_time, duration, price, tenant_id)
            send_telegram(bot_token, chat_id, message)
            notified_keys.add(key)
            new_notifications += 1

    if matching_slots:
        log.info("  Créneaux correspondant à la config de %s (%d) :", name, len(matching_slots))
        for s in matching_slots:
            log.info("    • %s", s)
    else:
        log.info("  Aucun créneau ne correspond à la config de %s.", name)

    if new_notifications > 0:
        log.info("  >>> %d notification(s) envoyée(s) à %s <<<", new_notifications, name)
    else:
        log.info("  >>> Aucune nouvelle notification pour %s <<<", name)

    updated = purge_old_entries(sorted(notified_keys), date.today())
    return updated


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------

def run_once(config: dict, users: list) -> list:
    days_ahead = config.get("days_ahead", 7)
    sport_id = config.get("sport_id", "PADEL")
    venues = config.get("venues", [])
    bot_token = config["telegram_bot_token"]

    log.info("Sport : %s | Horizon : %d jours | Clubs : %d | Users : %d",
             sport_id, days_ahead, len(venues), len(users))

    # 1. Fetch toutes les dispos une seule fois
    availability_cache = fetch_all_availability(venues, days_ahead, sport_id)

    # 2. Check + notif par user
    for user in users:
        updated_slots_sent = check_user(user, availability_cache, bot_token)
        user["slots_sent"] = updated_slots_sent
        try:
            save_user_state(user["id"], updated_slots_sent)
        except Exception as e:
            log.error("Erreur sauvegarde Supabase pour %s : %s", user["name"], e)

    return users


def main() -> None:
    config = load_config()
    interval_min = config.get("check_interval_min", 15)
    hour_start = config.get("active_hours_start", 8)
    hour_end = config.get("active_hours_end", 22)

    log.info("=" * 60)
    log.info("Démarrage du Playtomic Watcher (intervalle : %d min)", interval_min)
    log.info("=" * 60)

    users = load_users()

    while True:
        current_hour = datetime.now().hour
        if hour_start <= current_hour < hour_end:
            log.info("--- Nouvelle vérification ---")
            users = run_once(config, users)
            log.info("Prochain check dans %d minutes...", interval_min)
        else:
            log.info("Hors plage horaire (%dh-%dh), pause.", hour_start, hour_end)
        time.sleep(interval_min * 60)


if __name__ == "__main__":
    main()
