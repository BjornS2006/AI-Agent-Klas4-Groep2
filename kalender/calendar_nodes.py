from agent.agent import llm
from scheduler.appointments import apply_calendar_action, check_event_exists


def analyseer_kalender_taak(state):
    """
    Maak een kalender taak met details.
    - LLM nodig
    - Geen API tools
    - Geen regel code
    Extraheert kalenderdetails uit de input.
    """
    prompt = f"""Extraheer de kalenderdetails uit de volgende tekst.
Geef terug als JSON met velden: titel, datum, tijd, beschrijving, locatie.

Tekst: {state.raw_input}

JSON:"""
    response = llm.invoke(prompt)
    return {
        "calendar_prompt": response.content,
        "calendar_details": {"raw": response.content},
    }


def bestaat_in_kalender(state):
    """
    Bestaat het al in de kalender? Ja/nee
    - Geen LLM
    - Regel code
    - Geen API call
    """
    exists = check_event_exists(state.calendar_details)
    return {"calendar_exists": exists}


def kalender_verandering_aanbrengen(state):
    """
    Maak de verandering aan als het moet
    - LLM niet nodig
    - API call nodig?
    - Regel code nodig?
    """
    return {"calendar_action": "aanpassen"}


def kalender_aanmaken(state):
    """
    Maak het aan
    - LLM niet nodig
    - Wel API tool call
    - Geen regel code
    """
    return {"calendar_action": "aanmaken"}


def vraag_toestemming_kalender(state):
    """
    Vraag toestemming en zeg wat je wilt doen
    - LLM nodig
    - Geen API call
    - Geen regel code
    """
    prompt = f"""Ik wil het volgende doen met de kalender:
Actie: {state.calendar_action}
Details: {state.calendar_details}

Formuleer een duidelijke vraag aan de gebruiker om toestemming te vragen.
Leg uit wat je gaat doen.

Bericht:"""
    response = llm.invoke(prompt)
    return {"output_text": response.content, "calendar_approved": True}


def kalender_toepassen(state):
    """
    Aanpassing/maken van kalender toepassen
    - LLM niet nodig
    - API nodig
    - Geen regel code nodig
    """
    result = apply_calendar_action(state.calendar_action, state.calendar_details)
    return {"calendar_details": result}


def vat_samen_kalender(state):
    """
    Vat samen wat gedaan is
    - LLM nodig
    - Geen API
    - Geen regel
    """
    prompt = f"""Vat samen wat er is gedaan met de kalender.
Actie: {state.calendar_action}
Details: {state.calendar_details}

Samenvatting:"""
    response = llm.invoke(prompt)
    return {"output_text": response.content}
