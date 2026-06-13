from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated

from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from agent.agent import llm
from agent.search import format_searxng_results, search_searxng
from kalender.calendar_nodes import (
    analyseer_kalender_taak,
    bestaat_in_kalender,
    kalender_aanmaken,
    kalender_toepassen,
    kalender_verandering_aanbrengen,
    vraag_toestemming_kalender,
    vat_samen_kalender,
)
from memory.memory_nodes import (
    memory_gebruiker_algemeen,
    memory_gebruiker_personen,
    personen_opvragen,
)
from scheduler.reminders import (
    analyse_reminders,
    geef_aan_klaar,
    maak_aanpassing_reminder,
    maak_output_reminder,
    maak_taak_reminder,
    moet_status_veranderen_of_nieuwe,
    reminder_notificatie,
    voer_taak_uit,
    zeg_veranderingen_vraag_toestemming,
)


@dataclass
class AssistantState:
    """Gedeelde state voor de volledige workflow."""

    messages: Annotated[list, add_messages] = field(default_factory=list)
    raw_input: str = ""
    input_type: str = "text"
    protocol: str = ""
    search_needed: bool = False
    search_query: str = ""
    search_results: str = ""
    enough_info: bool = False
    calendar_prompt: str = ""
    calendar_exists: bool = False
    calendar_action: str = ""
    calendar_details: dict = field(default_factory=dict)
    calendar_approved: bool = False
    reminder_prompt: str = ""
    reminder_action: str = ""
    reminder_details: dict = field(default_factory=dict)
    task_details: dict = field(default_factory=dict)
    reminder_approved: bool = False
    user_memory: dict = field(default_factory=dict)
    person_memory: dict = field(default_factory=dict)
    general_memory: dict = field(default_factory=dict)
    output_text: str = ""
    final_output: str = ""



def analyseer_input(state: AssistantState) -> dict:
    prompt = f"""Analyseer de volgende gebruikersinput en bepaal welk protocol gevolgd moet worden.
Antwoord met EXACT één van: \"praten\", \"kalender\", \"taak_reminder\"

- \"praten\": als de gebruiker een vraag stelt, wil praten, of informatie wil
- \"kalender\": als de gebruiker iets wil toevoegen/wijzigen/bekijken in de kalender
- \"taak_reminder\": als de gebruiker een taak of reminder wil aanmaken, wijzigen of bekijken

Gebruikersinput: {state.raw_input}

Protocol:"""
    response = llm.invoke(prompt)
    protocol = response.content.strip().lower()
    if "kalender" in protocol:
        protocol = "kalender"
    elif "taak" in protocol or "reminder" in protocol:
        protocol = "taak_reminder"
    else:
        protocol = "praten"
    return {"protocol": protocol}


def route_protocol(state: AssistantState) -> str:
    return state.protocol


def analyseer_text_praten(state: AssistantState) -> dict:
    prompt = f"""Analyseer de volgende tekst. Geef een samenvatting van wat de gebruiker wil.

Tekst: {state.raw_input}

Analyse:"""
    response = llm.invoke(prompt)
    return {"output_text": response.content}


def _search_query(state: AssistantState) -> str:
    return state.search_query.strip() or state.raw_input.strip()


def moet_opzoeken(state: AssistantState) -> dict:
    prompt = f"""Op basis van de volgende vraag, moet ik iets opzoeken?
Antwoord met \"JA: <zoekterm>\" of \"NEE\".

Vraag: {state.raw_input}
Context: {state.output_text}

Antwoord:"""
    response = llm.invoke(prompt)
    answer = response.content.strip()
    if answer.upper().startswith("JA"):
        search_query = answer.split(":", 1)[-1].strip() if ":" in answer else state.raw_input
        return {"search_needed": True, "search_query": search_query}
    return {"search_needed": False}


def route_opzoeken(state: AssistantState) -> str:
    return "opzoeken" if state.search_needed else "genereer_output"


def opzoeken(state: AssistantState) -> dict:
    query = _search_query(state)
    results = search_searxng(query)
    formatted_results = format_searxng_results(query, results)
    if not formatted_results:
        formatted_results = f"Geen zoekresultaten gevonden voor: {query}"
    return {"search_results": formatted_results}


def weet_ik_genoeg(state: AssistantState) -> dict:
    if not state.search_results or state.search_results.startswith("Geen zoekresultaten") or state.search_results.startswith("SearxNG fout"):
        return {"enough_info": True}

    prompt = f"""Heb ik genoeg informatie om de vraag van de gebruiker te beantwoorden?

Oorspronkelijke vraag: {state.raw_input}
Gevonden informatie: {state.search_results}

Antwoord met \"JA\" of \"NEE: <nieuwe zoekterm>\":"""
    response = llm.invoke(prompt)
    answer = response.content.strip()
    if answer.upper().startswith("JA"):
        return {"enough_info": True}
    new_query = answer.split(":", 1)[-1].strip() if ":" in answer else state.search_query
    return {"enough_info": False, "search_query": new_query}


def route_genoeg_info(state: AssistantState) -> str:
    return "genereer_output" if state.enough_info else "opzoeken"


def genereer_output_praten(state: AssistantState) -> dict:
    context_parts = [f"Gebruikersvraag: {state.raw_input}"]
    if state.search_results:
        context_parts.append(f"Gevonden informatie: {state.search_results}")
    if state.person_memory:
        context_parts.append(f"Persoonsinformatie: {state.person_memory}")
    if state.general_memory:
        context_parts.append(f"Gebruikersgeheugen: {state.general_memory}")
    context = "\n".join(context_parts)
    prompt = f"""Genereer een behulpzaam en natuurlijk antwoord op basis van de volgende context.

{context}

Antwoord:"""
    response = llm.invoke(prompt)
    return {"output_text": response.content}


def text_to_speech(state: AssistantState) -> dict:
    return {"final_output": state.output_text}


def text_output(state: AssistantState) -> dict:
    return {"final_output": state.output_text}


def build_graph() -> StateGraph:
    graph = StateGraph(AssistantState)
    graph.add_node("analyseer_input", analyseer_input)
    graph.add_node("memory_algemeen", memory_gebruiker_algemeen)
    graph.add_node("memory_personen", memory_gebruiker_personen)
    graph.add_node("personen_opvragen", personen_opvragen)
    graph.add_node("analyseer_text_praten", analyseer_text_praten)
    graph.add_node("moet_opzoeken", moet_opzoeken)
    graph.add_node("opzoeken", opzoeken)
    graph.add_node("weet_ik_genoeg", weet_ik_genoeg)
    graph.add_node("genereer_output_praten", genereer_output_praten)
    graph.add_node("analyseer_kalender_taak", analyseer_kalender_taak)
    graph.add_node("bestaat_in_kalender", bestaat_in_kalender)
    graph.add_node("kalender_verandering", kalender_verandering_aanbrengen)
    graph.add_node("kalender_aanmaken", kalender_aanmaken)
    graph.add_node("vraag_toestemming_kalender", vraag_toestemming_kalender)
    graph.add_node("kalender_toepassen", kalender_toepassen)
    graph.add_node("vat_samen_kalender", vat_samen_kalender)
    graph.add_node("analyse_reminders", analyse_reminders)
    graph.add_node("moet_status_of_nieuwe", moet_status_veranderen_of_nieuwe)
    graph.add_node("maak_aanpassing_reminder", maak_aanpassing_reminder)
    graph.add_node("zeg_veranderingen", zeg_veranderingen_vraag_toestemming)
    graph.add_node("maak_taak_reminder", maak_taak_reminder)
    graph.add_node("voer_taak_uit", voer_taak_uit)
    graph.add_node("geef_aan_klaar", geef_aan_klaar)
    graph.add_node("maak_output_reminder", maak_output_reminder)
    graph.add_node("reminder_notificatie", reminder_notificatie)
    graph.add_node("text_to_speech", text_to_speech)
    graph.add_node("text_output", text_output)
    graph.add_edge(START, "analyseer_input")
    graph.add_edge("analyseer_input", "memory_algemeen")
    graph.add_edge("memory_algemeen", "memory_personen")
    graph.add_edge("memory_personen", "personen_opvragen")
    graph.add_conditional_edges(
        "personen_opvragen",
        route_protocol,
        {
            "praten": "analyseer_text_praten",
            "kalender": "analyseer_kalender_taak",
            "taak_reminder": "analyse_reminders",
        },
    )
    graph.add_edge("analyseer_text_praten", "moet_opzoeken")
    graph.add_conditional_edges(
        "moet_opzoeken",
        route_opzoeken,
        {
            "opzoeken": "opzoeken",
            "genereer_output": "genereer_output_praten",
        },
    )
    graph.add_edge("opzoeken", "weet_ik_genoeg")
    graph.add_conditional_edges(
        "weet_ik_genoeg",
        route_genoeg_info,
        {
            "genereer_output": "genereer_output_praten",
            "opzoeken": "opzoeken",
        },
    )
    graph.add_edge("genereer_output_praten", "text_to_speech")
    graph.add_edge("text_to_speech", END)
    graph.add_edge("analyseer_kalender_taak", "bestaat_in_kalender")
    graph.add_conditional_edges(
        "bestaat_in_kalender",
        route_kalender_bestaat,
        {
            "kalender_verandering": "kalender_verandering",
            "kalender_aanmaken": "kalender_aanmaken",
        },
    )
    graph.add_edge("kalender_verandering", "vraag_toestemming_kalender")
    graph.add_edge("kalender_aanmaken", "vraag_toestemming_kalender")
    graph.add_edge("vraag_toestemming_kalender", "kalender_toepassen")
    graph.add_edge("kalender_toepassen", "vat_samen_kalender")
    graph.add_edge("vat_samen_kalender", "text_to_speech")
    graph.add_edge("analyse_reminders", "moet_status_of_nieuwe")
    graph.add_conditional_edges(
        "moet_status_of_nieuwe",
        route_reminder_actie,
        {
            "veranderen": "maak_aanpassing_reminder",
            "nieuwe": "maak_taak_reminder",
        },
    )
    graph.add_edge("maak_aanpassing_reminder", "zeg_veranderingen")
    graph.add_edge("zeg_veranderingen", "voer_taak_uit")
    graph.add_edge("maak_taak_reminder", "voer_taak_uit")
    graph.add_edge("voer_taak_uit", "geef_aan_klaar")
    graph.add_edge("geef_aan_klaar", "maak_output_reminder")
    graph.add_edge("maak_output_reminder", "text_to_speech")
    return graph


def route_kalender_bestaat(state: AssistantState) -> str:
    return "kalender_verandering" if state.calendar_exists else "kalender_aanmaken"


def route_reminder_actie(state: AssistantState) -> str:
    return state.reminder_action


def compile_graph():
    graph = build_graph()
    return graph.compile()


def run(user_input: str, input_type: str = "text"):
    app = compile_graph()
    initial_state = {
        "raw_input": user_input,
        "input_type": input_type,
    }
    result = app.invoke(initial_state)
    return result.get("final_output") or result.get("output_text", "Geen antwoord.")