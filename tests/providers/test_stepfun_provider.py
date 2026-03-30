"""Tests for Step Fun provider registration."""

from nanobot.config.schema import ProvidersConfig
from nanobot.providers.registry import PROVIDERS


def test_stepfun_config_field_exists() -> None:
    config = ProvidersConfig()
    assert hasattr(config, "stepfun")


def test_stepfun_provider_in_registry() -> None:
    specs = {spec.name: spec for spec in PROVIDERS}
    assert "stepfun" in specs

    stepfun = specs["stepfun"]
    assert stepfun.env_key == "STEPFUN_API_KEY"
    assert stepfun.default_api_base == "https://api.stepfun.com/v1"
