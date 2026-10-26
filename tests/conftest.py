"""Offline fixtures; tests never address a real fireplace."""

from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def no_live_discovery():
    with (
        patch("custom_components.kalfire_gi.config_flow.async_same_subnet", return_value=None),
        patch(
            "custom_components.kalfire_gi.discovery._async_scan_interface",
            new_callable=AsyncMock,
            return_value=(),
        ),
    ):
        yield
