"""
Persoonlijke Assistent – Hoofdloop
===================================
Draait de agent continu met:
  1. Een inputloop waar je vragen kunt stellen
  2. Een achtergrondthread die elke minuut checkt of er reminders afgaan
"""

import threading
import time
from datetime import datetime

from agent.assistant import run


# ─── Reminder checker (achtergrond) ──────────────
REMINDER_CHECK_INTERVAL = 60  # seconden

def reminder_loop(stop_event: threading.Event):
    """
    Controleert elke minuut of er reminders zijn die nu
    moeten afgaan. Draait in een achtergrondthread.
    """
    from scheduler.reminders import reminder_notificatie

    class FakeState:
        """Minimale state om reminder_notificatie aan te roepen."""
        reminder_details = {}

    while not stop_event.is_set():
        try:
            state = FakeState()
            result = reminder_notificatie(state)
            due = result.get("reminder_details", {}).get("due_reminders", [])

            if due:
                print(f"\n🔔 Reminder(s) om {datetime.now().strftime('%H:%M')}:")
                for r in due:
                    print(f"   • {r.get('summary', 'Onbekend')}")
                print("\n> ", end="", flush=True)  # prompt opnieuw tonen

        except Exception as exc:
            pass  # stil falen, niet de gebruiker storen

        stop_event.wait(REMINDER_CHECK_INTERVAL)


# ─── Hoofdloop ───────────────────────────────────

def main():
    print("=" * 50)
    print("  Persoonlijke Assistent")
    print("  Typ 'stop' of 'exit' om te stoppen")
    print("=" * 50)
    print()

    # Start reminder checker op de achtergrond
    stop_event = threading.Event()
    reminder_thread = threading.Thread(
        target=reminder_loop,
        args=(stop_event,),
        daemon=True,
    )
    reminder_thread.start()

    while True:
        try:
            user_input = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nTot ziens!")
            break

        if not user_input:
            continue

        if user_input.lower() in ("stop", "exit", "quit"):
            print("Tot ziens!")
            break

        try:
            result = run(user_input)
            print(f"\n{result}\n")
        except Exception as exc:
            print(f"\n❌ Fout: {exc}\n")

    # Stop de reminder-thread netjes
    stop_event.set()
    reminder_thread.join(timeout=5)


if __name__ == "__main__":
    main()
