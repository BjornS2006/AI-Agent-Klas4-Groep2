from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from agent.agent import llm
from scheduler.appointments import apply_calendar_action, check_event_exists


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


def _to_appointments_details(llm_details: dict) -> dict:
    """
    Convert LLM output keys → appointments.py schema.

    LLM produces:  titel, datum (YYYY-MM-DD), tijd (HH:MM), duur_minuten,
                   beschrijving, locatie
    appointments.py expects: summary, start (ISO datetime str), end (ISO),
                              description, location, uid (optional)
    """
    datum = llm_details.get("datum", "")
    tijd = llm_details.get("tijd", "08:00")
    duur = int(llm_details.get("duur_minuten", 60))

    # Build ISO datetime strings
    try:
        start_dt = datetime.strptime(f"{datum} {tijd}", "%Y-%m-%d %H:%M")
    except ValueError:
        start_dt = datetime.now().replace(second=0, microsecond=0)

    end_dt = start_dt + timedelta(minutes=duur)

    result = {
        "summary": llm_details.get("titel", ""),
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "description": llm_details.get("beschrijving", ""),
        "location": llm_details.get("locatie", ""),
    }

    # Preserve uid if present (needed for updates)
    if llm_details.get("uid"):
        result["uid"] = llm_details["uid"]

    return result


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

def analyseer_kalender_taak(state) -> dict:
    """
    Extract calendar details from raw_input using the LLM.
    Stores both the raw LLM output and a parsed dict.
    """
    prompt = f"""Extraheer de kalenderdetails uit de volgende tekst.
Geef terug als JSON met de volgende velden:
  titel        - naam van het evenement
  datum        - datum in formaat YYYY-MM-DD
  tijd         - begintijd in formaat HH:MM (24-uurs)
  duur_minuten - duur in minuten (standaard 60 als niet vermeld)
  beschrijving - korte omschrijving (leeg als niet vermeld)
  locatie      - locatie (leeg als niet vermeld)

Geef ALLEEN de JSON terug, geen andere tekst.

Tekst: {state.raw_input}
JSON:"""
    response = llm.invoke(prompt)
    raw = response.content.strip()
    llm_details = _extract_json(raw)

    llm_details.setdefault("titel", state.raw_input[:60])
    llm_details.setdefault("datum", datetime.now().strftime("%Y-%m-%d"))
    llm_details.setdefault("tijd", "08:00")
    llm_details.setdefault("duur_minuten", 60)
    llm_details.setdefault("beschrijving", "")
    llm_details.setdefault("locatie", "")

    # Convert to appointments.py schema immediately so all downstream
    # nodes work with the correct keys
    appointments_details = _to_appointments_details(llm_details)

    return {
        "calendar_prompt": raw,
        "calendar_details": appointments_details,
    }


def bestaat_in_kalender(state) -> dict:
    """
    Check whether a matching event already exists in Radicale.
    calendar_details is already in appointments.py schema at this point.
    """
    exists = check_event_exists(state.calendar_details)
    return {"calendar_exists": exists}


def kalender_verandering_aanbrengen(state) -> dict:
    """
    Determine what change is needed for an existing event.
    appointments.py only supports "aanmaken"/"aanpassen", so verwijderen
    is left as a calendar_action the UI can handle separately if needed.
    """
    details_text = json.dumps(state.calendar_details, ensure_ascii=False, indent=2)

    prompt = f"""Een kalenderafspraak bestaat al. Bepaal welke aanpassing nodig is.
Beschikbare acties: "aanpassen", "verwijderen"

Huidige details (gebruik dezelfde sleutels):
{details_text}

Gebruikersvraag: {state.raw_input}

Als de actie "aanpassen" is, geef dan de volledige bijgewerkte details terug als JSON
met dezelfde sleutels (summary, start, end, description, location, uid).
Alle velden moeten aanwezig zijn, ook de ongewijzigde.
Als de actie "verwijderen" is, geef dan alleen {{"actie": "verwijderen"}} terug.

Geef ALLEEN JSON terug, geen andere tekst.
JSON:"""
    response = llm.invoke(prompt)
    result = _extract_json(response.content.strip())

    if result.get("actie") == "verwijderen":
        # appointments.py has no delete — store action, UI layer handles it
        return {"calendar_action": "verwijderen"}

    # Merge updated fields over current details; remove stray "actie" key
    merged = {**state.calendar_details, **result}
    merged.pop("actie", None)

    return {
        "calendar_action": "aanpassen",
        "calendar_details": merged,
    }


def kalender_aanmaken(state) -> dict:
    """Signal that the action is to create a new event."""
    return {"calendar_action": "aanmaken"}


def vraag_toestemming_kalender(state) -> dict:
    """
    Ask the user for confirmation before applying the calendar action.
    calendar_approved is set True here; actual human confirmation is
    handled at the UI layer before the graph is invoked.
    """
    details_text = json.dumps(state.calendar_details, ensure_ascii=False, indent=2)

    prompt = f"""Ik wil het volgende doen met de kalender:
Actie: {state.calendar_action}
Details:
{details_text}

Formuleer een duidelijke, vriendelijke bevestigingsvraag aan de gebruiker.
Leg kort uit wat je gaat doen en vraag of dit klopt.
Houd het beknopt (maximaal 3 zinnen).
Bericht:"""
    response = llm.invoke(prompt)
    return {
        "output_text": response.content.strip(),
        "calendar_approved": True,
    }


def kalender_toepassen(state) -> dict:
    """
    Apply the calendar action via CalDAV.
    Skips the API call for "verwijderen" since appointments.py
    doesn't implement it — logs a warning instead.
    """
    if state.calendar_action == "verwijderen":
        # Not implemented in appointments.py; return as-is with a note
        return {
            "calendar_details": {
                **state.calendar_details,
                "status": "verwijderen niet ondersteund via appointments.py",
                "action_performed": "verwijderen",
            }
        }

    updated = apply_calendar_action(state.calendar_action, state.calendar_details)
    return {"calendar_details": updated}


def vat_samen_kalender(state) -> dict:
    """Summarise what was done with the calendar for the user."""
    status = state.calendar_details.get("status", "onbekend")
    details_text = json.dumps(state.calendar_details, ensure_ascii=False, indent=2)

    prompt = f"""Vat samen wat er is gedaan met de kalender.
Actie: {state.calendar_action}
Status: {status}
Details:
{details_text}

Schrijf een korte, vriendelijke bevestiging (1-2 zinnen) voor de gebruiker.
Samenvatting:"""
    response = llm.invoke(prompt)
    return {"output_text": response.content.strip()}