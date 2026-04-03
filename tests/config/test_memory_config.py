from nanobot.config.schema import Config


def test_memory_backend_defaults_to_local() -> None:
    config = Config()

    assert config.memory.backend == "local"
    assert config.memory.supermemory.base_url == "https://api.supermemory.ai"


def test_memory_backend_accepts_supermemory_values() -> None:
    config = Config.model_validate(
        {
            "memory": {
                "backend": "supermemory",
                "supermemory": {
                    "apiKey": "sm_test_key",
                    "baseUrl": "https://api.supermemory.ai",
                    "containerTag": "workspace-prod",
                    "entityContext": "Remember durable user preferences and exact links.",
                    "timeoutS": 25,
                },
            }
        }
    )

    assert config.memory.backend == "supermemory"
    assert config.memory.supermemory.api_key == "sm_test_key"
    assert config.memory.supermemory.container_tag == "workspace-prod"
    assert (
        config.memory.supermemory.entity_context
        == "Remember durable user preferences and exact links."
    )
    assert config.memory.supermemory.timeout_s == 25
