"""Provides device automations for ESP-NOW devices that emit events."""

import logging
import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.components.device_automation.exceptions import (
    InvalidDeviceAutomationConfig,
)
from homeassistant.components.homeassistant.triggers import event as event_trigger
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, IntegrationError
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, EVENT_TYPE 
from . import EspNowBridge 

CONF_SUBTYPE = "subtype"
DEVICE = "device"

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {vol.Required(CONF_TYPE): str, vol.Optional(CONF_SUBTYPE): str}
)

_LOGGER = logging.getLogger(__name__)


async def async_validate_trigger_config(
    hass: HomeAssistant, config: ConfigType
) -> ConfigType:
    """Validate config."""
    config = TRIGGER_SCHEMA(config)
    _LOGGER.debug("Validate Trigger Config: {}".format(config))

    # if ZHA_DOMAIN in hass.config.components:
    #     await hass.data[DATA_ZHA][ZHA_DEVICES_LOADED_EVENT].wait()
    #     trigger = (config[CONF_TYPE], config[CONF_SUBTYPE])
    #     try:
    #         zha_device = async_get_zha_device(hass, config[CONF_DEVICE_ID])
    #     except (KeyError, AttributeError, IntegrationError) as err:
    #         raise InvalidDeviceAutomationConfig from err
    #     if (
    #         zha_device.device_automation_triggers is None
    #         or trigger not in zha_device.device_automation_triggers
    #     ):
    #         raise InvalidDeviceAutomationConfig

    return config



# Called when Automations are loaded that contain a corresponding device trigger
async def async_attach_trigger(
    hass: HomeAssistant,
    config: ConfigType,
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Listen for state changes based on configuration."""
    _LOGGER.debug("Attach Trigger {} Config: {}".format(trigger_info, config))
    trigger_key = config[CONF_TYPE]
    if subtype := config.get(CONF_SUBTYPE):
        trigger_key += '|' + subtype
    try:
        node = EspNowBridge.nodes_by_device_id[config[CONF_DEVICE_ID]]
    except (KeyError, AttributeError) as err:
        raise HomeAssistantError(
            f"Unable to get device {config[CONF_DEVICE_ID]}"
        ) from err

    if trigger_key not in node.device_automation_triggers:
        _LOGGER.error("Unable to find Node {} Trigger: {}".format(node.name, trigger_key))
        raise HomeAssistantError(f"Unable to find trigger {trigger_key}")

    trigger = node.device_automation_triggers[trigger_key]
    trigger_data = {"device_id": node.device_id, **trigger}
    _LOGGER.debug("Attach Trigger: {} {} ".format(trigger_key, trigger_data))

    event_config = {
        event_trigger.CONF_PLATFORM: "event",
        event_trigger.CONF_EVENT_TYPE: EVENT_TYPE,
        event_trigger.CONF_EVENT_DATA: trigger_data
    }

    event_config = event_trigger.TRIGGER_SCHEMA(event_config)
    return await event_trigger.async_attach_trigger(
        hass, event_config, action, trigger_info, platform_type="device"
    )


# Called when automations are created and a device trigger of the corresponding type is selected.
# Populates the device trigger UI.
async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
    """List device triggers.

    Make sure the device supports device automations and
    if it does return the trigger list.
    """
    _LOGGER.debug("Get Triggers: {}".format(device_id))
    node = EspNowBridge.nodes_by_device_id[device_id]

    if not node.device_automation_triggers:
        return []

    triggers = []

    _LOGGER.debug(node.device_automation_triggers)
    for tr in node.device_automation_triggers.keys():
        trigger, subtype = node.triggerParts(tr)
        t =  {
                CONF_DEVICE_ID: device_id,
                CONF_DOMAIN: DOMAIN,
                CONF_PLATFORM: DEVICE,
                CONF_TYPE: trigger
        }
        if (subtype):
            t[CONF_SUBTYPE] = subtype
        triggers.append(t)
    _LOGGER.debug("Get Triggers for {} : {}".format(device_id, triggers))
    return triggers
