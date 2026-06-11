"""
scheduler/appointments.py
=========================
Afspraken-/kalenderactielogica via CalDAV (Radicale) met
reminder-opslag in mem0.

Vereisten:
    pip install caldav icalendar mem0ai

Radicale draait standaard op http://localhost:5232.
Configureer de constanten hieronder of via environment variables.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any

import caldav
from icalendar import Calendar, Event, Alarm
from mem0 import Memory

logger = logging.getLogger(__name__)

# ─── Configuratie ────────────────────────────────
RADICALE_URL = os.getenv("RADICALE_URL", "http://localhost:5232")
RADICALE_USERNAME = os.getenv("RADICALE_USERNAME", "user")
RADICALE_PASSWORD = os.getenv("RADICALE_PASSWORD", "password")
CALENDAR_NAME = os.getenv("CALENDAR_NAME", "persoonlijke-assistent")
MEM0_USER_ID = os.getenv("MEM0_USER_ID", "default_user")

# Standaard reminder: 15 minuten voor het event
DEFAULT_REMINDER_MINUTES = 15


# ═════════════════════════════════════════════════
#  INTERNE HELPERS
# ═════════════════════════════════════════════════

def _get_caldav_client() -> caldav.DAVClient:
    """Maak een CalDAV-client aan richting Radicale."""
    return caldav.DAVClient(
        url=RADICALE_URL,
        username=RADICALE_USERNAME,
        password=RADICALE_PASSWORD,
    )


def _get_calendar(client: caldav.DAVClient) -> caldav.Calendar:
    """
    Haal de doelkalender op, of maak hem aan als hij
    nog niet bestaat.
    """
    principal = client.principal()
    for cal in principal.calendars():
        if cal.name == CALENDAR_NAME:
            return cal
    # Kalender bestaat nog niet → aanmaken
    logger.info("Kalender '%s' niet gevonden – wordt aangemaakt.", CALENDAR_NAME)
    return principal.make_calendar(name=CALENDAR_NAME)


def _get_mem0() -> Memory:
    """Geef een mem0 Memory-instantie terug."""
    return Memory()


# ─── Datetime parsing ────────────────────────────

_DT_FORMATS = [
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
]


def _parse_dt(value: Any) -> datetime:
    """
    Probeer een datetime te parsen uit een string of geef
    de waarde terug als het al een datetime is.
    """
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        for fmt in _DT_FORMATS:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    raise ValueError(f"Kan datetime niet parsen: {value!r}")


# ─── iCalendar opbouw ───────────────────────────

def _build_ical(details: dict) -> tuple[str, str, datetime, datetime]:
    """
    Bouw een volledige iCalendar-string (VCALENDAR met VEVENT)
    op basis van het details-dict.

    Returns
    -------
    tuple[ical_str, uid, start_dt, end_dt]
    """
    cal = Calendar()
    cal.add("prodid", "-//PersoonlijkeAssistent//NL")
    cal.add("version", "2.0")

    event = Event()

    # UID – hergebruik bestaande of genereer nieuwe
    uid = details.get("uid") or str(uuid.uuid4())
    event.add("uid", uid)

    # Samenvatting / titel
    event.add("summary", details.get("summary", "Geen titel"))

    # Start- en eindtijd
    start_dt = _parse_dt(details["start"])
    end_raw = details.get("end")
    end_dt = _parse_dt(end_raw) if end_raw else start_dt + timedelta(hours=1)
    event.add("dtstart", start_dt)
    event.add("dtend", end_dt)

    # Optionele velden
    if details.get("description"):
        event.add("description", details["description"])
    if details.get("location"):
        event.add("location", details["location"])

    # Tijdstempels
    now = datetime.utcnow()
    event.add("created", now)
    event.add("last-modified", now)

    # VALARM – reminder als onderdeel van het event
    reminder_min = int(details.get("reminder_minutes", DEFAULT_REMINDER_MINUTES))
    alarm = Alarm()
    alarm.add("action", "DISPLAY")
    alarm.add("description", f"Reminder: {details.get('summary', 'event')}")
    alarm.add("trigger", timedelta(minutes=-reminder_min))
    event.add_component(alarm)

    cal.add_component(event)
    return cal.to_ical().decode("utf-8"), uid, start_dt, end_dt


# ─── CalDAV I/O ─────────────────────────────────

def _save_to_caldav(ical_data: str, uid: str, calendar: caldav.Calendar) -> None:
    """Sla een event op (of overschrijf als de UID al bestaat)."""
    try:
        existing = calendar.event_by_uid(uid)
        existing.data = ical_data
        existing.save()
        logger.info("Bestaand event bijgewerkt: %s", uid)
    except caldav.error.NotFoundError:
        calendar.save_event(ical_data)
        logger.info("Nieuw event aangemaakt: %s", uid)


def _delete_from_caldav(uid: str, calendar: caldav.Calendar) -> bool:
    """Verwijder een event op UID. Retourneert True als het bestond."""
    try:
        event = calendar.event_by_uid(uid)
        event.delete()
        logger.info("Event verwijderd: %s", uid)
        return True
    except caldav.error.NotFoundError:
        return False


# ─── mem0 reminder-opslag ────────────────────────

def _store_reminder(details: dict) -> None:
    """
    Sla het remindertijdstip + eventinfo op in mem0 zodat
    de agent op het juiste moment een notificatie kan geven.
    """
    try:
        m = _get_mem0()
        reminder_text = (
            f"Herinnering voor '{details.get('summary', 'event')}' "
            f"om {details.get('reminder_time')}. "
            f"De afspraak begint om {details.get('start')} "
            f"en eindigt om {details.get('end')}."
        )
        if details.get("location"):
            reminder_text += f" Locatie: {details['location']}."
        if details.get("description"):
            reminder_text += f" Details: {details['description']}."

        m.add(
            reminder_text,
            user_id=MEM0_USER_ID,
            metadata={
                "type": "calendar_reminder",
                "uid": details.get("uid"),
                "summary": details.get("summary"),
                "reminder_time": details.get("reminder_time"),
                "start": details.get("start"),
                "end": details.get("end"),
            },
        )
        logger.info(
            "Reminder opgeslagen in mem0 – event %s om %s",
            details.get("uid"),
            details.get("reminder_time"),
        )
    except Exception as exc:
        logger.error("mem0 reminder opslaan mislukt: %s", exc)


def _remove_existing_reminder(uid: str) -> None:
    """
    Verwijder een eerder opgeslagen reminder uit mem0 (op basis
    van UID) zodat er geen verouderde notificaties blijven staan.
    """
    try:
        m = _get_mem0()
        results = m.search(
            f"calendar_reminder uid:{uid}",
            user_id=MEM0_USER_ID,
        )
        for entry in results.get("results", []):
            meta = entry.get("metadata", {})
            if meta.get("uid") == uid:
                m.delete(entry["id"])
                logger.info("Oude reminder verwijderd uit mem0: %s", uid)
    except Exception as exc:
        logger.warning("Kon oude reminder niet opruimen: %s", exc)


# ═════════════════════════════════════════════════
#  PUBLIEKE API – aangeroepen vanuit calendar_nodes
# ═════════════════════════════════════════════════

def check_event_exists(details: dict) -> bool:
    """
    Controleer of er al een matching event in Radicale staat.

    Zoekstrategie:
      1. Exacte UID-match (als `uid` in details zit)
      2. Anders: zoek op dezelfde dag naar events met
         (deels) overeenkomende summary of exact dezelfde
         starttijd.

    Parameters
    ----------
    details : dict
        Moet minstens ``start`` bevatten.
        Optioneel: ``uid``, ``summary``, ``end``.
    """
    try:
        client = _get_caldav_client()
        calendar = _get_calendar(client)

        # ── Strategie 1: exacte UID ──
        if details.get("uid"):
            try:
                calendar.event_by_uid(details["uid"])
                return True
            except caldav.error.NotFoundError:
                return False

        # ── Strategie 2: summary + datumbereik ──
        start = _parse_dt(details["start"])
        end_raw = details.get("end")
        end = _parse_dt(end_raw) if end_raw else start + timedelta(hours=1)

        search_start = start.replace(hour=0, minute=0, second=0)
        search_end = end.replace(hour=23, minute=59, second=59)

        events = calendar.date_search(
            start=search_start,
            end=search_end,
            expand=True,
        )

        target_summary = (details.get("summary") or "").lower().strip()

        for ev in events:
            vobj = ev.vobject_instance.vevent
            ev_summary = str(getattr(vobj, "summary", "")).lower().strip()
            ev_start = vobj.dtstart.value

            # Match op summary-substring
            if target_summary and target_summary in ev_summary:
                return True

            # Match op exact dezelfde starttijd (zonder summary)
            if isinstance(ev_start, datetime) and ev_start == start:
                return True

        return False

    except Exception as exc:
        logger.error("check_event_exists mislukt: %s", exc)
        return False


def prepare_create_event(details: dict) -> dict:
    """
    Bereid een nieuw calendar-event-payload voor.

    Voegt toe:
      - gegenereerde UID
      - berekende reminder_time (absoluut)
      - ical_data klaar voor CalDAV
      - status ``"ready_to_create"``
    """
    ical_data, uid, start_dt, end_dt = _build_ical(details)

    reminder_min = int(details.get("reminder_minutes", DEFAULT_REMINDER_MINUTES))
    reminder_time = start_dt - timedelta(minutes=reminder_min)

    return {
        **details,
        "uid": uid,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "reminder_minutes": reminder_min,
        "reminder_time": reminder_time.isoformat(),
        "ical_data": ical_data,
        "status": "ready_to_create",
    }


def prepare_update_event(details: dict) -> dict:
    """
    Bereid een update-payload voor van een bestaand event.

    Haalt het huidige event op via CalDAV, merged de nieuwe
    waarden er overheen (zodat ontbrekende velden behouden
    blijven), en bouwt een nieuwe iCal-string.
    """
    merged = {**details}

    # Haal bestaande waarden op als terugval
    if details.get("uid"):
        try:
            client = _get_caldav_client()
            calendar = _get_calendar(client)
            existing = calendar.event_by_uid(details["uid"])
            vobj = existing.vobject_instance.vevent

            if not merged.get("summary") and hasattr(vobj, "summary"):
                merged["summary"] = str(vobj.summary.value)
            if not merged.get("start") and hasattr(vobj, "dtstart"):
                merged["start"] = vobj.dtstart.value.isoformat()
            if not merged.get("end") and hasattr(vobj, "dtend"):
                merged["end"] = vobj.dtend.value.isoformat()
            if not merged.get("description") and hasattr(vobj, "description"):
                merged["description"] = str(vobj.description.value)
            if not merged.get("location") and hasattr(vobj, "location"):
                merged["location"] = str(vobj.location.value)

        except Exception as exc:
            logger.warning("Bestaand event ophalen voor merge mislukt: %s", exc)

    ical_data, uid, start_dt, end_dt = _build_ical(merged)

    reminder_min = int(merged.get("reminder_minutes", DEFAULT_REMINDER_MINUTES))
    reminder_time = start_dt - timedelta(minutes=reminder_min)

    return {
        **merged,
        "uid": uid,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "reminder_minutes": reminder_min,
        "reminder_time": reminder_time.isoformat(),
        "ical_data": ical_data,
        "status": "ready_to_update",
    }


def apply_calendar_action(action: str, details: dict) -> dict:
    """
    Voer de kalenderactie uit: maak aan of pas aan in Radicale,
    en sla het remindertijdstip op in mem0.

    Parameters
    ----------
    action : str
        ``"aanmaken"`` voor een nieuw event,
        ``"aanpassen"`` om een bestaand event te wijzigen.
    details : dict
        Moet minstens ``summary`` en ``start`` bevatten.
        Optioneel: ``end``, ``description``, ``location``,
        ``reminder_minutes``, ``uid`` (verplicht bij aanpassen).

    Returns
    -------
    dict
        Alle eventdetails + ``status`` (``"toegepast"`` of
        ``"mislukt"``) en ``action_performed``.
    """
    try:
        # 1. Payload voorbereiden
        if action == "aanmaken":
            prepared = prepare_create_event(details)
        else:
            prepared = prepare_update_event(details)

        # 2. Opslaan in Radicale via CalDAV
        client = _get_caldav_client()
        calendar = _get_calendar(client)
        _save_to_caldav(
            ical_data=prepared["ical_data"],
            uid=prepared["uid"],
            calendar=calendar,
        )

        # 3. Oude reminder opruimen (bij update) en nieuwe opslaan
        if action == "aanpassen" and details.get("uid"):
            _remove_existing_reminder(details["uid"])
        _store_reminder(prepared)

        # 4. Resultaat opschonen en teruggeven
        result = {k: v for k, v in prepared.items() if k != "ical_data"}
        result["status"] = "toegepast"
        result["action_performed"] = action
        return result

    except Exception as exc:
        logger.error("apply_calendar_action mislukt: %s", exc)
        return {
            **details,
            "status": "mislukt",
            "error": str(exc),
            "action_performed": action,
        }
