from agent.assistant import run


if __name__ == "__main__":
    result = run("Wat is het weer vandaag in Den Haag?")
    print("=== RESULTAAT ===")
    print(result.get("final_output", "Geen output"))
