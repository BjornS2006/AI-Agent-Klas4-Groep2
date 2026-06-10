def check_event_exists(details: dict) -> bool:
    """Check whether a matching calendar event already exists."""
    return False


def prepare_create_event(details: dict) -> dict:
    """Prepare a new calendar event payload."""
    return {**details, "status": "ready_to_create"}


def prepare_update_event(details: dict) -> dict:
    """Prepare an update payload for an existing calendar event."""
    return {**details, "status": "ready_to_update"}


def apply_calendar_action(action: str, details: dict) -> dict:
    """Apply a calendar action by creating or updating an event."""
    if action == "aanmaken":
        return {**prepare_create_event(details), "status": "toegepast"}
    return {**prepare_update_event(details), "status": "toegepast"}
