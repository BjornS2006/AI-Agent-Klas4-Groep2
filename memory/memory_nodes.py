def memory_gebruiker_algemeen(state):
    """
    Memory gebruiker/algemeen
    - API call nodig
    - Geen LLM
    - Geen regel code
    """
    user_mem = {}
    return {"general_memory": user_mem}


def memory_gebruiker_personen(state):
    """
    Memory gebruiker/personen/contactgegevens
    - API call nodig
    - Geen LLM
    - Geen regel code
    Om namen en contactgegevens te weten.
    """
    person_mem = {}
    return {"person_memory": person_mem}


def personen_opvragen(state):
    """
    Personen opvragen
    Call naar memory over een persoon en de gebruiker.
    """
    return {"person_memory": state.person_memory}
