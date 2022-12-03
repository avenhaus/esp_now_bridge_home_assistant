"""Describe logbook events."""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from homeassistant.components.logbook import LOGBOOK_ENTRY_MESSAGE, LOGBOOK_ENTRY_NAME
from homeassistant.const import ATTR_COMMAND, ATTR_DEVICE_ID
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.device_registry as dr

from . import EspNowBridge 
from .const import DOMAIN, EVENT_TYPE

import logging

_LOGGER = logging.getLogger(__name__)

@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    """Describe logbook events."""
    device_registry = dr.async_get(hass)

    @callback
    def async_describe_logbook_event(event: Event) -> dict[str, str]:
        """Describe logbook event."""
        device: dr.DeviceEntry | None = None
        device_name: str = "Unknown device"
        node = None
        event_data: dict = event.data
        event_type: str | None = None
        event_subtype: str | None = None

        try:
            device_entry = device_registry.devices[event.data[ATTR_DEVICE_ID]]
            if device_entry:
                device_name = device_entry.name_by_user or device_entry.name or "Unknown device"
        except (KeyError, AttributeError):
            pass


        _LOGGER.debug("async_describe_logbook_event: {} {} {}".format(event.data[ATTR_DEVICE_ID], device_name, event_data))

        try:
            node = EspNowBridge.nodes_by_device_id[event.data[ATTR_DEVICE_ID]]
        except (KeyError, AttributeError) as err:
            raise HomeAssistantError(f"Unable to get device {event.data[ATTR_DEVICE_ID]}" ) from err

        if event_type is None:
            event_type = event_data.get("type", EVENT_TYPE)

        if event_subtype is None:
            event_subtype = event_data.get("subtype")

        if event_subtype is not None and event_subtype != event_type:
            event_type = f"{event_type} - {event_subtype}"

        if event_type is not None:
            event_type = event_type.replace("_", " ").title()
            if "event" in event_type.lower():
                message = f"{event_type} was fired"
            else:
                message = f"{event_type} event was fired"

        if value := event_data.get("value"):
            message = f"{message} with value: {value}"

        if params := event_data.get("params"):
            message = f"{message} with parameters: {params}"

        return {
            LOGBOOK_ENTRY_NAME: device_name,
            LOGBOOK_ENTRY_MESSAGE: message,
        }

    async_describe_event(DOMAIN, EVENT_TYPE, async_describe_logbook_event)