"""Platform for Crestron Binary Sensor integration."""

import voluptuous as vol
import logging

from homeassistant.core import HomeAssistant
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.const import CONF_NAME, CONF_TYPE
import homeassistant.helpers.config_validation as cv
from .const import DOMAIN, CONF_IS_ON_FB_JOIN
from . import XPanelClient, HUB
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_IS_ON_FB_JOIN): cv.positive_int,
        vol.Required(CONF_TYPE): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)

CONF_DEV_CLASS = {'moving': BinarySensorDeviceClass.MOVING,
                  'opening': BinarySensorDeviceClass.OPENING,
                  'garage_door': BinarySensorDeviceClass.GARAGE_DOOR,
                  'window': BinarySensorDeviceClass.WINDOW,
                  'running': BinarySensorDeviceClass.RUNNING,
                  'safety': BinarySensorDeviceClass.SAFETY,
                  'sound': BinarySensorDeviceClass.SOUND,
                  'vibration': BinarySensorDeviceClass.VIBRATION,
                  'moisture': BinarySensorDeviceClass.MOISTURE,
                  'gas': BinarySensorDeviceClass.GAS,
                  'power': BinarySensorDeviceClass.POWER,
                  'motion': BinarySensorDeviceClass.MOTION,
                  'connect': BinarySensorDeviceClass.CONNECTIVITY}

CONST_ADD_ONLINE = False


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities: AddEntitiesCallback, discovery_info=None):
    sensor_list = []
    if HUB in hass.data[DOMAIN].keys():
        hub: XPanelClient = hass.data[DOMAIN][HUB]
        if isinstance(hub,XPanelClient):
            if not callable(hub.online_callback_func):
                    sensor_list.append(OnlineSensor(hub))
            if len(config.keys()) > 0:
                sensor_list.append(BinarySensor(hub, config))
            
    async_add_entities(sensor_list)


class OnlineSensor(BinarySensorEntity):
    def __init__(self, hub: XPanelClient):
        self._hub = hub
        self._attr_name = f'xpanel_{hub.host}_{hub.ip_id}_online'
        self._attr_unique_id = f"b_sensor_{self._attr_name}"
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_is_on = False
        self._hub.online_callback_func = self.process_callback

    async def async_added_to_hass(self):
        if isinstance(self._hub, XPanelClient):
            self._attr_is_on = self._hub.connected
        self.schedule_update_ha_state()

    async def async_will_remove_from_hass(self):
        pass

    def process_callback(self, online: bool):
        self._attr_is_on = online
        self.schedule_update_ha_state()


class BinarySensor(BinarySensorEntity):
    def __init__(self, hub: XPanelClient, config):
        self._hub = hub
        self._attr_name = config.get(CONF_NAME)
        self._join = config.get(CONF_IS_ON_FB_JOIN)
        self._attr_unique_id = f"{self._attr_name}_{self._join}"
        self._cfg_type = config.get(CONF_TYPE)
        self._attr_device_class = CONF_DEV_CLASS.get(self._cfg_type)

    async def async_added_to_hass(self):
        await self._hub.register_callback('d', self._join, self.process_callback)
        self._attr_is_on = bool(self._hub.get_digital(self._join))

    async def async_will_remove_from_hass(self):
        await self._hub.remove_callback('d', self._join, self.process_callback)

    def process_callback(self, cbtype, join, value):
        _LOGGER.debug(f'binary sensor value change:{value}')
        self._attr_is_on = bool(value)
        self.schedule_update_ha_state()
