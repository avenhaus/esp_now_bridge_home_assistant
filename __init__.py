"""The ESP-NOW Bridge sensor integration."""
from __future__ import annotations


from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry, device_registry
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.storage import Store

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
    ENTITY_ID_FORMAT,
)

from homeassistant.const import ATTR_COMMAND,  CONF_TYPE

import logging
import traceback
from pprint import pformat
import json
from serial import SerialException
import serial_asyncio
import asyncio
from functools import cached_property
import copy

from .const import DOMAIN, CONF_SERIAL_PORT, CONF_BAUD
from .sensor import EspNowSensor
from .binary_sensor import EspNowBinarySensor


_LOGGER = logging.getLogger("espnow")

async def async_setup_entry(  # noqa: C901
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    hass.data.setdefault(DOMAIN, {})

    store = Store(hass, EspNowBridge._STORAGE_VERSION, EspNowBridge._STORAGE_KEY)
    store_data = await store.async_load()
    _LOGGER.info(f"Loaded Store Data: {store_data}")
    EspNowBridge(hass, config_entry, store, store_data)
    return True


async def options_update_listener(
    hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry
):
    """Handle options update."""
    _LOGGER.info("Options Update Entry: {}".format(config_entry.entry_id))
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_unload_entry(
    hass: core.HomeAssistant, config_entry: config_entries.ConfigEntry
) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unload Config Entry: {}".format(config_entry.entry_id))
    unload_ok = all(
        await asyncio.gather(
            *[hass.config_entries.async_forward_entry_unload(config_entry, "sensor")]
        )
    )
    # Remove options_update_listener.
    hass.data[DOMAIN][config_entry.entry_id]["unsub_options_update_listener"]()

    # Remove config config_entry from domain.
    if unload_ok:
        hass.data[DOMAIN].pop(config_entry.entry_id)

    return unload_ok



class EspNowBridge:
    _STORAGE_VERSION = 1
    _STORAGE_KEY = DOMAIN

    hass = None
    entity_registry = None
    device_registry = None
    bridges = []
    nodes = {}
    nodes_by_device_id = {}

    def __init__(self, hass, config_entry, store, store_data):
        self.config_entry = config_entry
        self.config = dict(config_entry.data)
        self.nodes = {}
        self._store = store

        ## config_entry.data["nodes"] = {}

        if not self.hass:
            self.hass = hass
        if not self.entity_registry:
            self.entity_registry = entity_registry.async_get(self.hass)
        if not self.device_registry:
            self.device_registry = device_registry.async_get(self.hass)

        _LOGGER.info("New EspNowBridge: {}: {}".format(config_entry.entry_id, config_entry.data))
        if not self.config.get(CONF_SERIAL_PORT):
            raise ValueError(CONF_SERIAL_PORT + " must be set")
        hass.data[DOMAIN][config_entry.entry_id] = self.config

        if store_data:
            for mac, n in store_data.get("nodes", {}).items():
                Node(self, mac, n.get("name"), triggers=n.get("triggers"), events=n.get("events"))

        # Registers update listener to update config entry when options are updated.
        unsub_options_update_listener = config_entry.add_update_listener(options_update_listener)

        # Store a reference to the unsubscribe function to cleanup if an entry is unloaded.
        self.config["unsub_options_update_listener"] = unsub_options_update_listener

        self._task = self.hass.loop.create_task(self.serialReaderTask())
        self.bridges.append(self)


    async def serialReaderTask(self):
        serial_port = self.config[CONF_SERIAL_PORT];
        while True:
            try:
                reader, _ = await serial_asyncio.open_serial_connection(
                    url=serial_port, baudrate=self.config.get(CONF_BAUD, 460800))

            except SerialException as exc:
                if not logged_error:
                    _LOGGER.exception("Unable to connect to the serial device %s: %s. Will retry", serial_port, exc)
                    logged_error = True
                await self._handleError()
            else:
                _LOGGER.warning("Serial device %s connected", serial_port)
                while True:
                    try:
                        line = await reader.readline()
                    except SerialException as exc:
                        _LOGGER.exception("Error while reading serial device %s: %s", serial_port, exc)
                        await self._handleError()
                        break
                    else:
                        line = line.decode("utf-8").strip()
                        _LOGGER.warning("Received: %s", line)
                        self.handleMessage(line)


    async def _handleError(self):
            """Handle error for serial connection."""
            await asyncio.sleep(1)


    def handleMessage(self, data):
        if data[0] != '{':
            return
        try:
            msg = json.loads(data)
        except Exception as ex:
            _LOGGER.exception('Received invalid JSON: "{}" | {} | {}'.format(data, ex, traceback.format_exc()))
            return

        try:
            mac = msg.get("MAC")
            if not mac:
                _LOGGER.error("Message has no MAC address: {}".format(data))
                return
            node = self.nodes.get(mac)
            if not node:
                node = Node(self, mac, msg.get("name"))
            node.updateSensors(msg)
        except Exception as ex:
            _LOGGER.exception("Failed to handle message: {} | {} | {}".format(data, ex, traceback.format_exc()))

    
    def addNode(self, node):
        self.nodes[node.mac] = node
        self.nodes_by_device_id[node.device_id] = node

    @callback
    def save_config(self):
        nc = {}
        for mac, node in self.nodes.items():
            nc[mac] = node.asdict()
        data = {"nodes": nc}
        _LOGGER.info(f"Save Config: {data}")
        self._store.async_delay_save(lambda: data, 1.0)


class Node(Entity):    
    def __init__(self, bridge, mac, name, triggers=None, events=None):
        super().__init__()
        self.hass = bridge.hass        
        self.bridge = bridge
        self.sensors = {}
        self.mac = mac
        self.config_entry = bridge.config_entry
        self.device_automation_triggers = triggers if triggers else {}
        self.events = events if events else {}
        self._updated = False
        if not name:
            name = "ESPNOW-" + mac

        self._attr_name = name

        self.device_entry = self.bridge.device_registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            configuration_url="https://github.com/avenhaus",
            identifiers={(DOMAIN, self.mac)},
            name=name,
            manufacturer="Espressive",
            model="ESP32",
            sw_version="0.1",
            hw_version="0.1",
        )
        self.device_id = self.device_entry.id
        self._attr_unique_id = "device.esp_now_" + self.device_id
        bridge.addNode(self)
        ## EspNowBridge.config_entry.data["nodes"][self.device_id] = {"triggers": {}}

        _LOGGER.info("New node:{} name:{} device_id:{} unique_id:{}".format(mac, name, self.device_id, self._attr_unique_id))

    def asdict(self):
        return {"name": self._attr_name, "device_id":self.device_id, "triggers": self.device_automation_triggers, "events": self.events}

    def addSensor(self, name, config):
        _LOGGER.info("Found sensor: {}".format(name))
        s = None
        if config.get("t") == 2:
            pass   # E.g. events ...
        elif config.get("t") == 1:
            s = EspNowBinarySensor(self, name, config=config)
        else:
            s = EspNowSensor(self, name, state_class=SensorStateClass.MEASUREMENT, config=config)
        if s:
            self.sensors[name] = s
        return s
    
    def updateSensors(self, msg, path=None):
        events = {}
        for key, value in msg.items():
            name = path + " " + key if path else key
            if not path and key == "MAC":
                pass
            elif not path and key == "name":
                pass
            elif key[0] == "^":
                name = path + " " + key[1:] if path else key[1:]
                self.configureDeviceAutomationTrigger(name, value)
            elif key[0] == "@":
                name = path + " " + key[1:] if path else key[1:]
                events[name] = value
            elif key[0] == "$":
                name = path + " " + key[1:] if path else key[1:]
                self.configureSensor(name, value)
            elif isinstance(value, dict):                
                self.updateSensors(value, name)
            else:
                if key == "not_found":
                    continue
                if value == "not_found":
                    continue                
                s = self.sensors.get(name)
                if not s:
                    s = self.sensorFromEntity(name)
                if not s:
                    continue
                s.handleNewValue(value)
        if events:
            self.fireEvents(events)
        if self._updated:
            self._updated = False
            self.bridge.save_config()

    def sensorFromEntity(self, name):
        s = None
        eid = EspNowSensor.makeId(self, name)
        e = self.bridge.entity_registry.async_get(eid)
        # _LOGGER.debug("SFR Registy {} {}: {}".format(name, eid, e))
        if e:
            s = EspNowSensor(self, name, entity=e)
        else:
            eid = EspNowBinarySensor.makeId(self, name)
            e = self.bridge.entity_registry.async_get(eid)
            # _LOGGER.debug("SFR Registy {} {}: {}".format(name, eid, e))
            if e:
                s = EspNowBinarySensor(self, name, entity=e)
        if (s):
            self.sensors[name] = s
        return s

    def configureSensor(self, name, config):
        s = self.sensors.get(name)
        if not s:
            s = self.addSensor(name, config)

    def configureDeviceAutomationTrigger(self, name, config):
        ev_type = name.lower().replace(" ", "_").replace("-", "_")
        ev_key = None
        ev_data = {}
        if not config:
            ev_key = ev_type
        elif isinstance(config, str):        
            ev_key = config
        elif isinstance(config, dict):
            ev_data = copy.copy(config)
            et = ev_data.pop("t", ev_type)
            sub = ev_data.pop("s", None)
            ev_key = et + '|' + sub if sub else et
        else:
            raise ValueError(f"Invalid Device Automation Trigger config: {config}")
        _LOGGER.info(f"device_automation_trigger: {ev_key} : {ev_data}")
        if self.events.get(name) != ev_key or self.device_automation_triggers.get(ev_key) != ev_data:
            self._updated = True
        self.device_automation_triggers[ev_key] = ev_data
        self.events[name] = ev_key


    @cached_property
    def device_automation_triggers(self) -> dict[tuple[str, str], dict[str, str]]:
        """Return the device automation triggers for this device."""
        # Triggers are defined as: Key: (trigger, subtype) / Value: Event Data Dict
        triggers = {}
        # triggers[("device_offline", "device_offline")]: { "device_event_type": "device_offline" }       
        triggers.update(self.device_automation_triggers)
        for t in self.device_automation_triggers.values():
            triggers.update(t)
        _LOGGER.info("device_automation_triggers: {}".format(triggers))
        return triggers

    def fireEvents(self, events):
        for ev, data in events.items():
            ev_type = ev.lower().replace(" ", "_").replace("-", "_")
            event_data = {}
            event_data[CONF_TYPE] = ev_type
            trigger = self.events.get(ev)
            if trigger:
                ev_type, ev_subtype = self.triggerParts(trigger)
                value = self.device_automation_triggers.get(trigger)
                event_data[CONF_TYPE] = ev_type
                if ev_subtype is not None:
                    event_data["subtype"] = ev_subtype
                if value:
                    event_data.update(value)
            if data is not None:
                if (isinstance(data, dict)):
                    event_data.update(data)            
                else:
                    event_data["value"] = data
            event_data["device_id"] = self.device_id
            event_data["device_name"] = self.device_entry.name
            _LOGGER.info("Fire Event: {} {}".format(ev, event_data))
            self.hass.bus.async_fire(DOMAIN + "_event" , event_data)

    @staticmethod 
    def triggerParts(trigger):
        part = trigger.split('|')
        t = part[0]
        s = part[1] if len(part) > 1 else None
        return (t, s)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.mac)},
            name=self.name,
            model="ESP-NOW Node",
            manufacturer="Carsten",
            sw_version="0.1",
            #device_id=self.device_id,
            #config_entry_id=self.config_entry.entry_id
        )
