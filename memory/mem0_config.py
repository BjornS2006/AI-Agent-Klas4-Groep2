from mem0 import Memory


def init_mem0_client():
    """Initialize mem0 client with Ollama backend for persistent memory storage."""
    config = {
        "llm": {
            "provider": "ollama",
            "config": {
                "model": "gemma4:e2b",
                "ollama_base_url": "http://localhost:11434",
            },
        },
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": "nomic-embed-text",
                "ollama_base_url": "http://localhost:11434",
            },
        },
        "storage": {
            "type": "sqlite",
            "path": "./mem0_storage",
        },
        "version": "v1.0",
    }

    try:
        m = Memory.from_config(config)
        return m
    except Exception as e:
        print(f"Warning: Failed to initialize mem0: {e}")
        return None


# Global mem0 instance
mem0_client = init_mem0_client()
