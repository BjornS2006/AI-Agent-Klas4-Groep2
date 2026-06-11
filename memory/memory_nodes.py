from memory.mem0_config import mem0_client


def memory_gebruiker_algemeen(state):
    """
    Recall general user facts and preferences from mem0.
    Uses mem0 to retrieve stored user information.
    """
    user_mem = {}
    if mem0_client:
        try:
            memories = mem0_client.recall(
                "general user facts, preferences, and characteristics",
                user_id="default_user"
            )
            user_mem = {"facts": memories} if memories else {}
        except Exception as e:
            print(f"Error recalling general memory: {e}")
    return {"general_memory": user_mem}


def memory_gebruiker_personen(state):
    """
    Recall person/contact information from mem0.
    Retrieves stored information about known people and their contact details.
    """
    person_mem = {}
    if mem0_client:
        try:
            memories = mem0_client.recall(
                "names, contact information, and details about known people and contacts",
                user_id="default_user"
            )
            person_mem = {"contacts": memories} if memories else {}
        except Exception as e:
            print(f"Error recalling person memory: {e}")
    return {"person_memory": person_mem}


def personen_opvragen(state):
    """
    Personen opvragen
    Call naar memory over een persoon en de gebruiker.
    """
    return {"person_memory": state.person_memory}


def add_memory_from_conversation(text: str, memory_type: str = "general") -> None:
    """
    Store new user insights extracted from conversation.

    Args:
        text: The information to store in memory
        memory_type: Type of memory - "general" or "person"
    """
    if mem0_client:
        try:
            mem0_client.add(
                messages=text,
                user_id="default_user",
                metadata={"type": memory_type}
            )
        except Exception as e:
            print(f"Error adding memory: {e}")
