from copy import deepcopy
import logging
from typing import Any, Dict, Optional

from homeassistant import config_entries, core
from homeassistant.const import CONF_NAME, CONF_PATH
from homeassistant.core import callback

import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_registry import (
    async_entries_for_config_entry,
    async_get_registry,
)
import voluptuous as vol

from .const import DOMAIN, CONF_SERIAL_PORT, CONF_BAUD


_LOGGER = logging.getLogger(__name__)

# UI Strings are defines in strings.json
PORT_SCHEMA = vol.Schema(
    {vol.Required(CONF_SERIAL_PORT): cv.string, vol.Optional(CONF_BAUD): cv.positive_int}
)

class EspNowBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Custom config flow."""

    data: Optional[Dict[str, Any]]

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        """Invoked when a user initiates a flow via the user interface."""
        errors: Dict[str, str] = {}
        if user_input is not None:
            _LOGGER.info("User Input:{}".format(user_input))
            # TODO Input validation
            self.data = user_input
            return self.async_create_entry(title="ESP-NOW Bridge", data=self.data)

        return self.async_show_form(
            step_id="user", data_schema=PORT_SCHEMA, errors=errors
        )

