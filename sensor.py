"""Platform for sensor integration."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
    ENTITY_ID_FORMAT,
)
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN

import logging

_LOGGER = logging.getLogger("espnow")


STATE_CLASS_ABBR = {
    "m": SensorStateClass.MEASUREMENT,
    "t": SensorStateClass.TOTAL,
    "ti": SensorStateClass.TOTAL_INCREASING
}


class EspNowSensor(SensorEntity):

    def __init__(self, node, name, unit=None, icon=None, device_class=None, state_class=None, native_value=None, config=None, entity=None):
        self.hass = node.hass
        self._node = node
        self._attr_name = node.name + " " + name
        self._state = None
        self._available = True
        self._attr_device_class = device_class if device_class else None
        self._attr_state_class = STATE_CLASS_ABBR.get(state_class, state_class) if state_class else None
        self._attr_icon = icon if icon else None
        self._attr_native_unit_of_measurement = unit if unit else None
        self._attr_native_value = native_value if native_value else None

        if entity:
            self.entity = entity
            self.fromEntity(entity)

        if config:
            self.configure(config)

        if not entity:
            self.entity = node.bridge.entity_registry.async_get_or_create(
                domain=SENSOR_DOMAIN,
                platform=DOMAIN,
                unique_id=node.mac + "_" + self._attr_name.lower().replace(" ", "_").replace("-", "_"),
                config_entry=node.config_entry,
                device_id=node.device_id,
                original_device_class=self._attr_device_class,            
                original_icon=self._attr_icon,
                original_name=self._attr_name,
                capabilities={"state_class": self._attr_state_class} if self._attr_state_class else None,
                unit_of_measurement = self._attr_native_unit_of_measurement
            )

        self.entity_id =  self.entity.entity_id
        _LOGGER.info("New Sensor:{} {}".format(self.entity_id, self.entity.unique_id))


    @staticmethod
    def makeId(node, name):
        return ENTITY_ID_FORMAT.format((DOMAIN + "_" + node.mac + "_" + node.name + "_" + name).lower().replace(" ", "_").replace("-", "_"))

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    @property
    def state(self):
        return self._state

    @property
    def device_name(self):
        return self.node.name
        
    @property
    def device_id(self):
        return self.node.device_id

    @property
    def device_info(self) -> DeviceInfo:
        _LOGGER.info("Device Info:{}".format(self._node.device_info))
        return self._node.device_info

    def configure(self, config):
        _LOGGER.info("Sensor:{} got config:{}".format(self._attr_unique_id, config))
        for key, value in config.items():
            if key == "dc":
                self._attr_device_class = value
            elif key == "sc":
                self._attr_state_class = STATE_CLASS_ABBR.get(value, value)
            elif key == "icon":
                self._attr_icon = value
            elif key == "i":
                self._attr_icon = value
            elif key == "unit":
                self._attr_native_unit_of_measurement = value
            elif key == "u":
                self._attr_native_unit_of_measurement = value
            elif key == "nv":
                self._attr_native_value = value
            else:
                _LOGGER.warning("Sensor:{} unknown config {}:{}".format(self._attr_unique_id, key, value))

    def fromEntity(self, entity):
        self._attr_device_class = entity.original_device_class
        if entity.capabilities:
            self._attr_state_class = entity.capabilities.get('state_class')        
        self.area_id = entity.area_id
        #self.icon = entity.icon
        #self.has_entity_name = entity.has_entity_name
        #self.name = entity.name
        self._attr_icon = entity.original_icon
        #self.supported_features = entity.supported_features
        #self.unit_of_measurement = entity.unit_of_measurement
        self._attr_native_unit_of_measurement = entity.unit_of_measurement

    def handleNewValue(self, value):
        _LOGGER.debug("{} new value: {}".format(self.name, value))
        self._state = value
        self.async_write_ha_state()
