"""
booking_manager.py
Orchestrateur principal : abstrait de toute plateforme spécifique.
Utilise les clients du dossier api/ via un registre de plateformes.
"""

import logging
import os
import sys
import time
from datetime import date, datetime, timedelta

import requests
import yaml

from api.anybuddy_client import AnybuddyClient
from api.playtomic_client import PlaytomicClient
from api.supabase_client import SupabaseClient

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
# Registre des plateformes
# ---------------------------------------------------------------------------
PLATFORM_CLIENTS = {
    "playtomic": PlaytomicClient(),
    "anybuddy": AnybuddyClient(),
}

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
CONFIG_FILE = "config.yaml"

FR_DAY_NAMES = {
    "monday": "Lundi", "tuesday": "Mardi", "wednesday": "Mercredi",
    "thursday": "Jeudi", "friday": "Vendredi", "saturday": "Samedi",
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
# Cache des disponibilités (toutes plateformes)
# ---------------------------------------------------------------------------

def fetch_all_availability(venues: list, days_ahead: int, sport_id: str) -> dict:
    """
    Récupère les dispos pour tous les clubs via le client approprié.
    Retourne un dict : {(venue_id, date_str): [slots enrichis]}
    """
    today = date.today()
    cache = {}

    for venue in venues:
        platform = venue.get("platform", "playtomic")
        client = PLATFORM_CLIENTS.get(platform)
        if not client:
            log.warning("Plateforme inconnue '%s' pour %s, skip.", platform, venue["name"])
            continue

        venue_id = venue["tenant_id"]
        venue_name = venue["name"]
        activity = venue.get("activity", sport_id)
        log.info("--- Récupération dispo : %s (%s) ---", venue_name, platform)

        for offset in range(days_ahead):
            check_date = today + timedelta(days=offset)
            date_str = check_date.isoformat()

            try:
                raw_slots = client.get_availability(venue_id, activity, date_str)
                enriched = []
                for slot in raw_slots:
                    slot_date = slot.get("date", date_str)
                    enriched.append({
                        **slot,
                        "_venue_id": venue_id,
                        "_venue_name": venue_name,
                        "_platform": platform,
                        "_date_str": slot_date,
                        "_day_of_week": datetime.strptime(slot_date, "%Y-%m-%d").strftime("%A").lower(),
                        "_start_time_paris": slot["start_time"],
                        "_booking_url": client.get_booking_url(venue_id, activity),
                    })
                cache[(venue_id, date_str)] = enriched
                log.info("  %s (%s) : %d créneau(x) dispo", date_str, check_date.strftime("%A").lower(), len(enriched))
                for s in enriched:
                    log.info("    → %s (Paris) | %d min", s["_start_time_paris"], s.get("duration", 0))
            except Exception as e:
                log.warning("Erreur API pour %s le %s : %s", venue_name, date_str, e)
                cache[(venue_id, date_str)] = []

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


def make_key(venue_id: str, date_str: str, start_time: str) -> str:
    return f"{venue_id}|{date_str}|{start_time}"


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


def format_message(venue_name: str, date_str: str, start_time: str,
                   duration: int, price: dict, booking_url: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    day_fr = FR_DAY_NAMES.get(dt.strftime("%A").lower(), "")
    month_fr = ["", "janvier", "février", "mars", "avril", "mai", "juin",
                "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    date_label = f"{day_fr} {dt.day} {month_fr[dt.month]}"

    price_str = ""
    if price and isinstance(price, dict):
        amount = price.get("amount", "")
        currency = price.get("currency", "")
        if amount:
            price_str = f"\n💶 {amount} {currency}"

    return (
        f"🎾 <b>Terrain disponible !</b>\n"
        f"📍 {venue_name}\n"
        f"📅 {date_label} à {start_time} ({duration} min)"
        f"{price_str}\n"
        f"🔗 <a href=\"{booking_url}\">Réserver</a>"
    )


# ---------------------------------------------------------------------------
# Check par user
# ---------------------------------------------------------------------------

def check_user(user: dict, availability_cache: dict, bot_token: str) -> list:
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
            start_time = slot["_start_time_paris"]
            duration = slot.get("duration", 0)
            date_str = slot["_date_str"]
            day_of_week = slot["_day_of_week"]

            if not is_desired(start_time, duration, day_of_week, slots_config):
                continue

            matching_slots.append(f"{slot['_venue_name']} | {date_str} à {start_time} ({duration} min)")
            key = make_key(slot["_venue_id"], date_str, start_time)

            if key in notified_keys:
                continue

            log.info("  ✓ NOUVEAU CRÉNEAU : %s %s à %s (%d min)",
                     slot["_venue_name"], date_str, start_time, duration)
            message = format_message(
                slot["_venue_name"], date_str, start_time,
                duration, slot.get("price", {}), slot["_booking_url"]
            )
            send_telegram(bot_token, chat_id, message)
            notified_keys.add(key)
            new_notifications += 1

    if matching_slots:
        log.info("  Créneaux correspondant à la config de %s (%d) :", name, len(matching_slots))
        for s in matching_slots:
            log.info("    • %s", s)
    else:
        log.info("  Aucun créneau ne correspond à la config de %s.", name)

    log.info("  >>> %d notification(s) envoyée(s) à %s <<<", new_notifications, name)

    return purge_old_entries(sorted(notified_keys), date.today())


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------

def run_once(config: dict, users: list, db: SupabaseClient) -> list:
    days_ahead = config.get("days_ahead", 7)
    sport_id = config.get("sport_id", "PADEL")
    venues = config.get("venues", [])
    bot_token = config["telegram_bot_token"]

    log.info("Horizon : %d jours | Clubs : %d | Users : %d",
             days_ahead, len(venues), len(users))

    availability_cache = fetch_all_availability(venues, days_ahead, sport_id)

    for user in users:
        updated_slots_sent = check_user(user, availability_cache, bot_token)
        user["slots_sent"] = updated_slots_sent
        try:
            db.save_user_state(user["id"], updated_slots_sent)
        except Exception as e:
            log.error("Erreur sauvegarde Supabase pour %s : %s", user["name"], e)

    return users


def main() -> None:
    config = load_config()
    interval_min = config.get("check_interval_min", 15)
    hour_start = config.get("active_hours_start", 8)
    hour_end = config.get("active_hours_end", 22)

    log.info("=" * 60)
    log.info("Démarrage du Watcher (intervalle : %d min)", interval_min)
    log.info("=" * 60)

    db = SupabaseClient()
    users = db.load_users()

    while True:
        current_hour = datetime.now().hour
        if hour_start <= current_hour < hour_end:
            log.info("--- Nouvelle vérification ---")
            users = run_once(config, users, db)
            log.info("Prochain check dans %d minutes...", interval_min)
        else:
            log.info("Hors plage horaire (%dh-%dh), pause.", hour_start, hour_end)
        time.sleep(interval_min * 60)


if __name__ == "__main__":
    main()
