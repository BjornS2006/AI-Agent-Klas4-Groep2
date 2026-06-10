from agent.agent import llm


def analyse_reminders(state):
    """
    Analyse reminders - Datum/taakbeschrijving/afgerond of niet
    - LLM nodig
    - API kalender tool call
    - Geen code
    """
    prompt = f"""Analyseer de volgende taak/reminder informatie.
Extraheer: datum, taakbeschrijving, status (afgerond/niet afgerond).

Input: {state.raw_input}
Memory: {state.user_memory}

Analyse:"""
    response = llm.invoke(prompt)
    return {
        "reminder_prompt": response.content,
        "reminder_details": {"raw": response.content},
    }


def find_matching_reminder(details: dict) -> bool:
    """Determine whether a matching reminder already exists."""
    return False


def moet_status_veranderen_of_nieuwe(state):
    """
    Moet status veranderen of nieuwe maken
    - Geen LLM
    - API call
    - Code
    """
    existing = find_matching_reminder(state.reminder_details)
    action = "veranderen" if existing else "nieuwe"
    return {"reminder_action": action}


def maak_aanpassing_reminder(state):
    """
    Maak de aanpassing (bestaande reminder wijzigen)
    - Geen LLM
    - API call
    - Code
    """
    return {"reminder_details": {**state.reminder_details, "status": "aangepast"}}


def zeg_veranderingen_vraag_toestemming(state):
    """
    Zeg wat de veranderingen zijn en vraag toestemming
    - LLM nodig
    - Geen API call
    - Geen code
    """
    prompt = f"""Ik wil de volgende veranderingen aanbrengen aan een reminder:
Details: {state.reminder_details}

Formuleer een duidelijk bericht dat uitlegt wat er verandert en vraag toestemming.

Bericht:"""
    response = llm.invoke(prompt)
    return {"output_text": response.content, "reminder_approved": True}


def maak_taak_reminder(state):
    """
    Maak taak/reminder (nieuwe aanmaken)
    - Geen LLM
    - API call
    - Code
    """
    return {"reminder_details": {**state.reminder_details, "status": "aangemaakt"}}


def voer_taak_uit(state):
    """
    Voer taak uit
    - LLM niet nodig
    - API call nodig
    - Geen regel nodig
    """
    return {"task_details": {**state.task_details, "status": "uitgevoerd"}}


def geef_aan_klaar(state):
    """
    Geef aan dat het klaar is
    - Transitie-node
    """
    return {"output_text": "Taak is uitgevoerd."}


def maak_output_reminder(state):
    """
    Maak output gebaseerd op reminder
    - LLM nodig
    - Geen regel
    - Geen API
    """
    prompt = f"""Genereer een natuurlijk bericht over de reminder/taak status.

Reminder details: {state.reminder_details}
Taak details: {state.task_details}

Bericht:"""
    response = llm.invoke(prompt)
    return {"output_text": response.content}


def reminder_notificatie(state):
    """
    Reminder notificatie
    - Geen LLM
    - API nodig
    - Misschien een regel
    """
    return {"reminder_details": state.reminder_details}
