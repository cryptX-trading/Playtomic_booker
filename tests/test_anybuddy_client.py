"""
Tests du AnybuddyClient — appels réels à l'API Anybuddy.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.anybuddy_client import AnybuddyClient

CLIENT = AnybuddyClient()

VENUE_ID = "paris-padel"
ACTIVITY = "padel"
DATE = "2026-03-24"


def test_get_availability_returns_list():
    slots = CLIENT.get_availability(VENUE_ID, ACTIVITY, DATE)
    assert isinstance(slots, list), "Doit retourner une liste"
    print(f"  {len(slots)} créneau(x) trouvé(s)")


def test_slot_structure():
    slots = CLIENT.get_availability(VENUE_ID, ACTIVITY, DATE)
    if not slots:
        print("  Aucun créneau dispo ce jour — structure non vérifiable")
        return
    slot = slots[0]
    assert "start_time" in slot, "Champ 'start_time' manquant"
    assert "date" in slot, "Champ 'date' manquant"
    assert "duration" in slot, "Champ 'duration' manquant"
    assert "price" in slot, "Champ 'price' manquant"
    assert len(slot["start_time"]) == 5, f"Format start_time invalide: {slot['start_time']}"
    print(f"  Premier créneau : {slot['start_time']} | {slot['duration']} min | {slot['price']}")


def test_booking_url():
    url = CLIENT.get_booking_url(VENUE_ID, ACTIVITY)
    assert VENUE_ID in url, "L'URL doit contenir le venue_id"
    assert ACTIVITY in url, "L'URL doit contenir l'activité"
    print(f"  URL : {url}")


if __name__ == "__main__":
    tests = [test_get_availability_returns_list, test_slot_structure, test_booking_url]
    failed = 0
    for t in tests:
        try:
            print(f"▶ {t.__name__}")
            t()
            print("  ✅ OK")
        except Exception as e:
            print(f"  ❌ FAIL : {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} tests passés.")
