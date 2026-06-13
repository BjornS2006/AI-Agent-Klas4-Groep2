from mem0 import Memory
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="mem0")


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
            "embedding_dims": 768,
        },
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "collection_name": "mem0_768",
            "embedding_model_dims": 768,
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
