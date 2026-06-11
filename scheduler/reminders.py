"""
scheduler/reminders.py
======================
Taak-/reminderprotocol-logica.

Reminders en taken worden als kalender-events opgeslagen in
Radicale (via appointments.py). Het remindertijdstip wordt
bijgehouden in mem0 zodat de agent op het juiste moment een
notificatie kan geven.

Vereisten:
    pip install caldav icalendar mem0ai
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any

import caldav
from icalendar import Calendar as iCalendar
from mem0 import Memory

from scheduler.appointments import (
    _get_caldav_client,
    _get_calendar,
    _get_mem0,
    _parse_dt,
    _build_ical,
    _save_to_caldav,
    _delete_from_caldav,
    _store_reminder,
    _remove_existing_reminder,
    check_event_exists,
    prepare_create_event,
    prepare_update_event,
    apply_calendar_action,
    DEFAULT_REMINDER_MINUTES,
    MEM0_USER_ID,
)
from agent.agent import llm

logger = logging.getLogger(__name__)


# ═════════════════════════════════════════════════
#  INTERNE HELPERS
# ═════════════════════════════════════════════════

def _search_reminders_in_mem0(query: str) -> list[dict]:
    """
    Zoek bestaande reminders in mem0.
    Retourneert een lijst van matches met metadata.
    """
    try:
        m = _get_mem0()
        results = m.search(query, user_id=MEM0_USER_ID)
        return [
            entry
            for entry in results.get("results", [])
            if entry.get("metadata", {}).get("type") in (
                "calendar_reminder",
                "task_reminder",
            )
        ]
    except Exception as exc:
        logger.error("mem0 reminder-zoekactie mislukt: %s", exc)
        return []


def _search_reminders_in_caldav(
    summary: str | None = None,
    start: datetime | None = None,
    days_range: int = 7,
) -> list[dict]:
    """
    Zoek events in Radicale die op reminders/taken lijken.

    Parameters
    ----------
    summary : str | None
        (Deel van) de samenvatting om op te zoeken.
    start : datetime | None
        Zoek vanaf deze datum. Default: vandaag.
    days_range : int
        Aantal dagen vooruit om te zoeken.

    Returns
    -------
    list[dict]
        Gevonden events als dicts met uid, summary, start, end,
        description, status.
    """
    try:
        client = _get_caldav_client()
        calendar = _get_calendar(client)

        search_start = start or datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0,
        )
        search_end = search_start + timedelta(days=days_range)

        events = calendar.date_search(
            start=search_start, end=search_end, expand=True,
        )

        found: list[dict] = []
        summary_lower = (summary or "").lower()

        for event in events:
            try:
                cal = event.icalendar_instance
                for component in cal.walk():
                    if component.name != "VEVENT":
                        continue

                    ev_summary = str(component.get("summary", ""))
                    ev_status = str(component.get("status", "NEEDS-ACTION"))
                    ev_start = component.get("dtstart")
                    ev_end = component.get("dtend")
                    ev_desc = str(component.get("description", ""))
                    ev_uid = str(component.get("uid", ""))

                    # Filter op summary als die is opgegeven
                    if summary_lower and summary_lower not in ev_summary.lower():
                        continue

                    found.append({
                        "uid": ev_uid,
                        "summary": ev_summary,
                        "start": ev_start.dt.isoformat() if ev_start else None,
                        "end": ev_end.dt.isoformat() if ev_end else None,
                        "description": ev_desc,
                        "caldav_status": ev_status,
                    })
            except Exception:
                continue

        return found

    except Exception as exc:
        logger.error("CalDAV reminder-zoekactie mislukt: %s", exc)
        return []


def _mark_event_status(uid: str, new_status: str) -> bool:
    """
    Wijzig de STATUS property van een CalDAV-event.
    Gangbare waarden: NEEDS-ACTION, IN-PROCESS, COMPLETED, CANCELLED.
    """
    try:
        client = _get_caldav_client()
        calendar = _get_calendar(client)
        event = calendar.event_by_uid(uid)

        cal = event.icalendar_instance
        for component in cal.walk():
            if component.name != "VEVENT":
                continue
            component["status"] = new_status
            component["last-modified"] = datetime.utcnow()
            break

        event.data = cal.to_ical().decode("utf-8")
        event.save()
        logger.info("Event %s status → %s", uid, new_status)
        return True

    except caldav.error.NotFoundError:
        logger.warning("Event %s niet gevonden voor statuswijziging.", uid)
        return False
    except Exception as exc:
        logger.error("Statuswijziging mislukt voor %s: %s", uid, exc)
        return False


def _store_task_reminder_in_mem0(details: dict) -> None:
    """
    Sla een taak-/reminderrecord op in mem0 met type
    'task_reminder' zodat het onderscheiden kan worden
    van gewone kalender-reminders.
    """
    try:
        m = _get_mem0()

        text = (
            f"Taak/Reminder: '{details.get('summary', 'taak')}'. "
            f"Gepland op {details.get('start', 'onbekend')}. "
            f"Status: {details.get('task_status', 'open')}."
        )
        if details.get("description"):
            text += f" Beschrijving: {details['description']}."
        if details.get("reminder_time"):
            text += f" Herinneringstijdstip: {details['reminder_time']}."

        m.add(
            text,
            user_id=MEM0_USER_ID,
            metadata={
                "type": "task_reminder",
                "uid": details.get("uid"),
                "summary": details.get("summary"),
                "start": details.get("start"),
                "end": details.get("end"),
                "reminder_time": details.get("reminder_time"),
                "task_status": details.get("task_status", "open"),
            },
        )
        logger.info("Taak-reminder opgeslagen in mem0: %s", details.get("uid"))
    except Exception as exc:
        logger.error("mem0 taak-reminder opslaan mislukt: %s", exc)


# ═════════════════════════════════════════════════
#  PUBLIEKE FUNCTIES – graph nodes
# ═════════════════════════════════════════════════

def find_matching_reminder(details: dict) -> dict | None:
    """
    Zoek of er al een reminder/taak bestaat die matcht met
    de opgegeven details.

    Zoekt eerst in mem0 (op summary-tekst), daarna in CalDAV
    (op summary + datumbereik). Retourneert de eerste match
    als dict, of None.
    """
    summary = details.get("summary", details.get("raw", ""))

    # ── 1. Zoek in mem0 ──
    mem0_hits = _search_reminders_in_mem0(summary)
    if mem0_hits:
        best = mem0_hits[0]
        meta = best.get("metadata", {})
        return {
            "uid": meta.get("uid"),
            "summary": meta.get("summary", ""),
            "start": meta.get("start"),
            "end": meta.get("end"),
            "reminder_time": meta.get("reminder_time"),
            "task_status": meta.get("task_status", "open"),
            "source": "mem0",
            "mem0_id": best.get("id"),
        }

    # ── 2. Zoek in CalDAV ──
    start_dt = None
    if details.get("start"):
        try:
            start_dt = _parse_dt(details["start"])
        except ValueError:
            pass

    caldav_hits = _search_reminders_in_caldav(
        summary=summary,
        start=start_dt,
        days_range=30,
    )
    if caldav_hits:
        hit = caldav_hits[0]
        return {
            **hit,
            "task_status": "afgerond"
            if hit.get("caldav_status") == "COMPLETED"
            else "open",
            "source": "caldav",
        }

    return None


# ─────────────────────────────────────────────
#  GRAPH NODE FUNCTIES
# ─────────────────────────────────────────────

def analyse_reminders(state):
    """
    Analyse reminders – Datum/taakbeschrijving/afgerond of niet
    - LLM nodig
    - API kalender tool call
    - Geen code

    De LLM extraheert gestructureerde informatie uit de
    gebruikersinput. Vervolgens worden bestaande reminders
    in CalDAV opgezocht om context mee te geven.
    """
    # ── Stap 1: LLM-analyse van de invoer ──
    prompt = f"""Analyseer de volgende gebruikersinput over een taak of reminder.
Extraheer de volgende velden (als ze beschikbaar zijn):

- summary: korte titel van de taak/reminder
- description: uitgebreide beschrijving
- start: datum en/of tijd (formaat YYYY-MM-DD HH:MM)
- end: einddatum/-tijd (indien van toepassing)
- reminder_minutes: hoeveel minuten van tevoren herinnerd moet worden
- task_status: "open", "afgerond" of "geannuleerd"

Antwoord ALLEEN met de velden in dit formaat (één per regel):
summary: ...
description: ...
start: ...
end: ...
reminder_minutes: ...
task_status: ...

Gebruikersinput: {state.raw_input}
Bekende gebruikersinformatie: {state.user_memory}

Analyse:"""

    response = llm.invoke(prompt)
    raw_analysis = response.content.strip()

    # ── Stap 2: Parse het LLM-antwoord naar een dict ──
    parsed: dict[str, str] = {}
    for line in raw_analysis.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower().replace(" ", "_")
            value = value.strip()
            if value and value.lower() not in ("geen", "n/a", "onbekend", "nvt", "none", "..."):
                parsed[key] = value

    # ── Stap 3: Zoek in CalDAV naar bestaande events op die dag ──
    existing_events: list[dict] = []
    if parsed.get("start"):
        try:
            start_dt = _parse_dt(parsed["start"])
            existing_events = _search_reminders_in_caldav(
                summary=parsed.get("summary"),
                start=start_dt,
                days_range=1,
            )
        except ValueError:
            pass

    # Voeg bestaande events toe aan de details voor context
    parsed["existing_events"] = existing_events
    parsed["raw_analysis"] = raw_analysis

    return {
        "reminder_prompt": raw_analysis,
        "reminder_details": parsed,
    }


def moet_status_veranderen_of_nieuwe(state):
    """
    Moet status veranderen of nieuwe maken
    - Geen LLM
    - API call
    - Code

    Zoekt met find_matching_reminder of er al een
    overeenkomstige taak/reminder bestaat. Zo ja →
    'veranderen', zo nee → 'nieuwe'.
    """
    existing = find_matching_reminder(state.reminder_details)

    if existing:
        # Bestaande gegevens mergen in reminder_details
        merged = {**state.reminder_details}
        merged["existing_uid"] = existing.get("uid")
        merged["existing_summary"] = existing.get("summary")
        merged["existing_start"] = existing.get("start")
        merged["existing_status"] = existing.get("task_status")
        merged["match_source"] = existing.get("source")
        if existing.get("mem0_id"):
            merged["existing_mem0_id"] = existing["mem0_id"]

        return {
            "reminder_action": "veranderen",
            "reminder_details": merged,
        }

    return {"reminder_action": "nieuwe"}


def maak_aanpassing_reminder(state):
    """
    Maak de aanpassing (bestaande reminder wijzigen)
    - Geen LLM
    - API call
    - Code

    Past het bestaande event aan in CalDAV en werkt de
    reminder bij in mem0.
    """
    details = {**state.reminder_details}
    uid = details.get("existing_uid") or details.get("uid")

    if not uid:
        logger.error("Geen UID beschikbaar voor aanpassing.")
        return {
            "reminder_details": {**details, "status": "fout", "error": "Geen UID"},
        }

    # ── Bepaal wat er moet veranderen ──
    new_status = details.get("task_status")
    needs_reschedule = any(details.get(k) for k in ("start", "end", "reminder_minutes"))

    # ── Statuswijziging (bijv. afgerond markeren) ──
    if new_status == "afgerond":
        _mark_event_status(uid, "COMPLETED")
        # Verwijder reminder uit mem0 – niet meer nodig
        _remove_existing_reminder(uid)
        details["status"] = "aangepast"
        details["changes"] = ["Status → afgerond"]

        # Werk mem0 taak-record bij
        _store_task_reminder_in_mem0({**details, "uid": uid, "task_status": "afgerond"})
        return {"reminder_details": details}

    if new_status == "geannuleerd":
        _mark_event_status(uid, "CANCELLED")
        _remove_existing_reminder(uid)
        details["status"] = "aangepast"
        details["changes"] = ["Status → geannuleerd"]
        return {"reminder_details": details}

    # ── Inhoudelijke wijziging (tijd, beschrijving, etc.) ──
    if needs_reschedule:
        update_payload = {
            "uid": uid,
            "summary": details.get("summary") or details.get("existing_summary"),
            "start": details.get("start") or details.get("existing_start"),
            "end": details.get("end"),
            "description": details.get("description"),
            "reminder_minutes": details.get("reminder_minutes"),
        }
        result = apply_calendar_action("aanpassen", update_payload)
        details.update(result)
        details["changes"] = [
            f"{k} bijgewerkt"
            for k in ("start", "end", "description", "reminder_minutes", "summary")
            if details.get(k)
        ]
    else:
        details["status"] = "aangepast"
        details["changes"] = ["Geen wijzigingen gedetecteerd"]

    return {"reminder_details": details}


def zeg_veranderingen_vraag_toestemming(state):
    """
    Zeg wat de veranderingen zijn en vraag toestemming
    - LLM nodig
    - Geen API call
    - Geen code
    """
    changes = state.reminder_details.get("changes", [])
    changes_text = ", ".join(changes) if changes else "aanpassingen aan de reminder"

    prompt = f"""Je bent een persoonlijke assistent. Je wilt de volgende veranderingen aanbrengen
aan een bestaande reminder/taak. Leg uit wat er verandert en vraag beleefd om
toestemming.

Huidige taak: {state.reminder_details.get('existing_summary', 'onbekend')}
Huidige starttijd: {state.reminder_details.get('existing_start', 'onbekend')}
Huidige status: {state.reminder_details.get('existing_status', 'onbekend')}

Gewenste veranderingen: {changes_text}
Nieuwe details: {state.reminder_details}

Formuleer een duidelijk, kort bericht in het Nederlands:"""

    response = llm.invoke(prompt)
    return {
        "output_text": response.content,
        # Toestemming moet door de gebruiker gegeven worden;
        # default op False totdat de volgende interactie dat bevestigt.
        "reminder_approved": False,
    }


def maak_taak_reminder(state):
    """
    Maak taak/reminder (nieuwe aanmaken)
    - Geen LLM
    - API call
    - Code

    Maakt een nieuw event aan in Radicale en slaat het
    remindertijdstip op in mem0.
    """
    details = {**state.reminder_details}

    # Zorg dat er minstens een summary en starttijd zijn
    if not details.get("summary"):
        details["summary"] = details.get("raw_analysis", "Nieuwe taak")[:80]
    if not details.get("start"):
        # Fallback: 1 uur vanaf nu
        fallback = datetime.utcnow() + timedelta(hours=1)
        details["start"] = fallback.strftime("%Y-%m-%dT%H:%M")
        logger.warning("Geen starttijd opgegeven – fallback naar %s", details["start"])

    # Standaard 1 uur duur als er geen eindtijd is
    if not details.get("end"):
        try:
            start_dt = _parse_dt(details["start"])
            details["end"] = (start_dt + timedelta(hours=1)).isoformat()
        except ValueError:
            pass

    details["task_status"] = "open"

    # ── Aanmaken via appointments.py ──
    result = apply_calendar_action("aanmaken", details)

    # ── Sla ook als task_reminder op in mem0 ──
    _store_task_reminder_in_mem0(result)

    result["status"] = "aangemaakt"
    return {"reminder_details": result}


def voer_taak_uit(state):
    """
    Voer taak uit
    - LLM niet nodig
    - API call nodig
    - Geen regel nodig

    Markeert de taak als COMPLETED in CalDAV en werkt
    mem0 bij.
    """
    details = {**state.task_details} if state.task_details else {**state.reminder_details}
    uid = details.get("uid") or details.get("existing_uid")

    if uid:
        _mark_event_status(uid, "COMPLETED")
        _remove_existing_reminder(uid)
        _store_task_reminder_in_mem0({**details, "uid": uid, "task_status": "afgerond"})
        details["task_status"] = "afgerond"
        details["status"] = "uitgevoerd"
    else:
        details["status"] = "uitgevoerd"
        details["task_status"] = "afgerond"
        logger.warning("Taak uitgevoerd maar geen UID om in CalDAV bij te werken.")

    return {"task_details": details}


def geef_aan_klaar(state):
    """
    Geef aan dat het klaar is – transitienode.
    Verzamelt een samenvatting van wat er is gedaan.
    """
    task = state.task_details or {}
    reminder = state.reminder_details or {}

    summary = task.get("summary") or reminder.get("summary") or "taak"
    status = task.get("status") or reminder.get("status") or "klaar"

    return {
        "output_text": f"'{summary}' is verwerkt (status: {status}).",
    }


def maak_output_reminder(state):
    """
    Maak output gebaseerd op reminder
    - LLM nodig
    - Geen regel
    - Geen API
    """
    prompt = f"""Je bent een persoonlijke assistent. Genereer een kort, natuurlijk
bericht in het Nederlands over de status van de taak/reminder.

Reminder details: {state.reminder_details}
Taak details: {state.task_details}
Actie uitgevoerd: {state.reminder_action}

Bericht:"""

    response = llm.invoke(prompt)
    return {"output_text": response.content}


def reminder_notificatie(state):
    """
    Reminder notificatie
    - Geen LLM
    - API nodig
    - Misschien een regel

    Controleert in mem0 of er reminders zijn waarvan het
    herinneringstijdstip verstreken is (of binnen nu en
    5 minuten valt). Retourneert de details zodat de
    agent de gebruiker kan waarschuwen.
    """
    now = datetime.utcnow()
    window = now + timedelta(minutes=5)

    try:
        m = _get_mem0()
        # Haal alle reminder-memories op
        all_memories = m.get_all(user_id=MEM0_USER_ID)

        due_reminders: list[dict] = []

        for entry in all_memories.get("results", []):
            meta = entry.get("metadata", {})
            if meta.get("type") not in ("calendar_reminder", "task_reminder"):
                continue
            if meta.get("task_status") == "afgerond":
                continue

            reminder_time_str = meta.get("reminder_time")
            if not reminder_time_str:
                continue

            try:
                reminder_dt = _parse_dt(reminder_time_str)
            except ValueError:
                continue

            # Reminder is aan de beurt als het tijdstip
            # in het verleden ligt of binnen het venster valt
            if reminder_dt <= window:
                due_reminders.append({
                    "mem0_id": entry.get("id"),
                    "uid": meta.get("uid"),
                    "summary": meta.get("summary"),
                    "start": meta.get("start"),
                    "end": meta.get("end"),
                    "reminder_time": reminder_time_str,
                    "text": entry.get("memory", ""),
                })

        if due_reminders:
            logger.info(
                "%d reminder(s) aan de beurt: %s",
                len(due_reminders),
                [r["summary"] for r in due_reminders],
            )
            return {
                "reminder_details": {
                    "due_reminders": due_reminders,
                    "count": len(due_reminders),
                    "checked_at": now.isoformat(),
                },
            }

        return {
            "reminder_details": {
                "due_reminders": [],
                "count": 0,
                "checked_at": now.isoformat(),
            },
        }

    except Exception as exc:
        logger.error("Reminder-notificatiecheck mislukt: %s", exc)
        return {
            "reminder_details": {
                "due_reminders": [],
                "count": 0,
                "error": str(exc),
            },
        }
