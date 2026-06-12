"""
test_calendar.py
================
Standalone tests voor scheduler/appointments.py en kalender/calendar_nodes.py.
Radicale moet draaien op http://localhost:5232 (of RADICALE_URL env var).

Gebruik:
    python test_calendar.py
"""

import os
import sys

# Zodat lokale imports werken zonder installatie
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta

# ─── Kleur output helpers ────────────────────────────────────────────────────

def ok(msg):  print(f"  \033[32m✓\033[0m  {msg}")
def fail(msg): print(f"  \033[31m✗\033[0m  {msg}"); 
def header(msg): print(f"\n\033[1m{msg}\033[0m")

passed = failed = 0

def check(label, condition, extra=""):
    global passed, failed
    if condition:
        ok(label)
        passed += 1
    else:
        fail(f"{label}  {extra}")
        failed += 1


# ═════════════════════════════════════════════════════════════════════════════
#  1. appointments.py – lage niveaufuncties
# ═════════════════════════════════════════════════════════════════════════════

header("1. _parse_dt")
from scheduler.appointments import _parse_dt

for val, expect in [
    ("2025-06-01T09:00:00", datetime(2025, 6, 1, 9, 0, 0)),
    ("2025-06-01T09:00",    datetime(2025, 6, 1, 9, 0)),
    ("2025-06-01 09:00",    datetime(2025, 6, 1, 9, 0)),
    ("2025-06-01",          datetime(2025, 6, 1)),
]:
    result = _parse_dt(val)
    check(f"parse '{val}'", result == expect, f"got {result}")

already_dt = datetime(2025, 1, 1, 12, 0)
check("datetime passthrough", _parse_dt(already_dt) == already_dt)

try:
    _parse_dt("geen-datum")
    check("ongeldige waarde gooit ValueError", False)
except ValueError:
    check("ongeldige waarde gooit ValueError", True)


# ─────────────────────────────────────────────────────────────────────────────
header("2. _build_ical")
from scheduler.appointments import _build_ical

details_basis = {
    "summary": "Testvergadering",
    "start": "2025-06-01T10:00:00",
    "end":   "2025-06-01T11:00:00",
    "description": "Beschrijving",
    "location": "Kantoor",
    "reminder_minutes": 15,
}

ical_str, uid, start_dt, end_dt = _build_ical(details_basis)
check("retourneert string",          isinstance(ical_str, str))
check("BEGIN:VCALENDAR aanwezig",    "BEGIN:VCALENDAR" in ical_str)
check("VEVENT aanwezig",             "BEGIN:VEVENT" in ical_str)
check("VALARM aanwezig",             "BEGIN:VALARM" in ical_str)
check("summary in ical",             "Testvergadering" in ical_str)
check("locatie in ical",             "Kantoor" in ical_str)
check("uid is string",               isinstance(uid, str) and len(uid) > 0)
check("start correct",               start_dt == datetime(2025, 6, 1, 10, 0))
check("end correct",                 end_dt   == datetime(2025, 6, 1, 11, 0))

# Zonder end → standaard +1 uur
ical_str2, _, start2, end2 = _build_ical({**details_basis, "end": None})
check("end valt terug op +1 uur",    end2 == start2 + timedelta(hours=1))

# UID hergebruik
ical_str3, uid3, _, _ = _build_ical({**details_basis, "uid": "vaste-uid-123"})
check("bestaande uid behouden",      uid3 == "vaste-uid-123")


# ─────────────────────────────────────────────────────────────────────────────
header("3. prepare_create_event")
from scheduler.appointments import prepare_create_event

prep = prepare_create_event(details_basis)
check("uid toegevoegd",              "uid" in prep)
check("reminder_time toegevoegd",    "reminder_time" in prep)
check("ical_data aanwezig",          "ical_data" in prep)
check("status is ready_to_create",   prep["status"] == "ready_to_create")

reminder_dt = datetime.fromisoformat(prep["reminder_time"])
start_dt2   = datetime.fromisoformat(prep["start"])
check("reminder 15 min voor start",  start_dt2 - reminder_dt == timedelta(minutes=15))


# ═════════════════════════════════════════════════════════════════════════════
#  4. CalDAV integratie (vereist draaiende Radicale)
# ═════════════════════════════════════════════════════════════════════════════

header("4. CalDAV integratie  (Radicale moet draaien)")

from scheduler.appointments import (
    _get_caldav_client,
    _get_calendar,
    _save_to_caldav,
    _delete_from_caldav,
    check_event_exists,
    apply_calendar_action,
)

try:
    client   = _get_caldav_client()
    calendar = _get_calendar(client)
    check("verbinding met Radicale", True)
except Exception as exc:
    check("verbinding met Radicale", False, str(exc))
    print("\n  ⚠  Radicale niet bereikbaar – CalDAV-tests overgeslagen.\n")
    # Sla de rest van sectie 4 over
    calendar = None

if calendar is not None:
    # Maak een uniek event aan
    test_uid  = f"test-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    now       = datetime.now().replace(second=0, microsecond=0)
    ev_details = {
        "summary":          "Automatische testafspraak",
        "start":            now.isoformat(),
        "end":              (now + timedelta(hours=1)).isoformat(),
        "description":      "Aangemaakt door test_calendar.py",
        "location":         "Testlocatie",
        "reminder_minutes": 10,
        "uid":              test_uid,
    }

    # check_event_exists → False vóór aanmaken
    check("event bestaat nog niet",  not check_event_exists(ev_details))

    # apply_calendar_action: aanmaken
    result = apply_calendar_action("aanmaken", ev_details)
    check("aanmaken status toegepast", result.get("status") == "toegepast")
    check("uid behouden na aanmaken",  result.get("uid") == test_uid)

    # check_event_exists → True na aanmaken
    check("event bestaat na aanmaken", check_event_exists({"uid": test_uid, "start": now.isoformat()}))

    # apply_calendar_action: aanpassen
    updated_details = {**ev_details, "summary": "Aangepaste testafspraak", "uid": test_uid}
    result2 = apply_calendar_action("aanpassen", updated_details)
    check("aanpassen status toegepast", result2.get("status") == "toegepast")

    # Controleer dat de aanpassing er staat
    ev = calendar.event_by_uid(test_uid)
    summary_in_cal = str(ev.vobject_instance.vevent.summary.value)
    check("summary bijgewerkt in Radicale", summary_in_cal == "Aangepaste testafspraak",
          f"got '{summary_in_cal}'")

    # Opruimen
    deleted = _delete_from_caldav(test_uid, calendar)
    check("event verwijderd na test",  deleted)
    check("event weg na verwijderen",  not check_event_exists({"uid": test_uid, "start": now.isoformat()}))


# ═════════════════════════════════════════════════════════════════════════════
#  5. calendar_nodes.py
# ═════════════════════════════════════════════════════════════════════════════

header("5. _extract_json  (calendar_nodes)")
import unittest.mock, sys
# inject a fake llm so calendar_nodes doesn't trigger the full agent import chain
sys.modules.setdefault("agent", unittest.mock.MagicMock())
sys.modules.setdefault("agent.agent", unittest.mock.MagicMock())

import importlib
cn = importlib.import_module("kalender.calendar_nodes")
_extract_json = cn._extract_json
_to_appointments_details = cn._to_appointments_details

check("clean json",          _extract_json('{"a": 1}') == {"a": 1})
check("markdown fences",     _extract_json('```json\n{"a": 1}\n```') == {"a": 1})
check("json midden in tekst",_extract_json('tekst {"a": 1} meer tekst') == {"a": 1})
check("ongeldig → leeg dict",_extract_json("geen json hier") == {})


header("6. _to_appointments_details  (calendar_nodes)")
_to_appointments_details = cn._to_appointments_details

llm_out = {
    "titel":        "Tandarts",
    "datum":        "2025-07-15",
    "tijd":         "14:30",
    "duur_minuten": 45,
    "beschrijving": "Controle",
    "locatie":      "Centrum",
}
conv = _to_appointments_details(llm_out)
check("summary correct",   conv["summary"] == "Tandarts")
check("start correct",     conv["start"]   == "2025-07-15T14:30:00")
check("end correct",       conv["end"]     == "2025-07-15T15:15:00")
check("description",       conv["description"] == "Controle")
check("location",          conv["location"] == "Centrum")
check("geen LLM-sleutels", "titel" not in conv and "datum" not in conv)

# uid doorgegeven als die aanwezig is
conv_uid = _to_appointments_details({**llm_out, "uid": "abc-123"})
check("uid doorgegeven",   conv_uid.get("uid") == "abc-123")

# Ongeldige datum → valt terug op nu (geen crash)
conv_bad = _to_appointments_details({**llm_out, "datum": "geen-datum"})
check("ongeldige datum geen crash", "start" in conv_bad)


# ─────────────────────────────────────────────────────────────────────────────
header("7. Nodes met mock state  (geen LLM, geen Radicale)")

class MockState:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

# kalender_aanmaken
kalender_aanmaken = cn.kalender_aanmaken
result = kalender_aanmaken(MockState())
check("kalender_aanmaken → aanmaken", result == {"calendar_action": "aanmaken"})

# bestaat_in_kalender: we mocken check_event_exists
import kalender.calendar_nodes as cn
original_check = cn.check_event_exists

cn.check_event_exists = lambda d: True
result = cn.bestaat_in_kalender(MockState(calendar_details={}))
check("bestaat_in_kalender → True",  result == {"calendar_exists": True})

cn.check_event_exists = lambda d: False
result = cn.bestaat_in_kalender(MockState(calendar_details={}))
check("bestaat_in_kalender → False", result == {"calendar_exists": False})

cn.check_event_exists = original_check  # herstellen

# kalender_toepassen: verwijderen zonder API
from kalender.calendar_nodes import kalender_toepassen
state_del = MockState(calendar_action="verwijderen", calendar_details={"summary": "x"})
result = kalender_toepassen(state_del)
check("verwijderen geeft status terug zonder crash",
      "status" in result["calendar_details"])


# ═════════════════════════════════════════════════════════════════════════════
#  Eindresultaat
# ═════════════════════════════════════════════════════════════════════════════

total = passed + failed
print(f"\n{'─'*40}")
print(f"  {passed}/{total} geslaagd", end="")
if failed:
    print(f"  –  \033[31m{failed} mislukt\033[0m")
else:
    print(f"  \033[32m– alles OK\033[0m")
print()
sys.exit(0 if failed == 0 else 1)