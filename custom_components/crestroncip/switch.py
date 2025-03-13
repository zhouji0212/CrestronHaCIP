"""Platform for Crestron Switch integration."""

import voluptuous as vol
import logging

import homeassistant.helpers.config_validation as cv
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON, STATE_OFF, CONF_NAME, CONF_DEVICE_CLASS
from .const import HUB, DOMAIN, CONF_SWITCH_JOIN
from .crestroncipsync import CIPSocketClient
_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_DEVICE_CLASS): cv.string,
        vol.Required(CONF_SWITCH_JOIN): cv.positive_int,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hub = hass.data[DOMAIN][HUB]
    entity = [CrestronSwitch(hub, config)]
    async_add_entities(entity)


class CrestronSwitch(SwitchEntity):
    def __init__(self, hub: CIPSocketClient, config):
        self._hub = hub
        self._name = config.get(CONF_NAME)
        self._switch_join = config.get(CONF_SWITCH_JOIN)
        self._device_class = config.get(CONF_DEVICE_CLASS, "switch")
        self._state = self._hub.get_digital(self._switch_join)

    async def async_added_to_hass(self):
        self._hub.register_callback(
            "d", self._switch_join, self.process_callback)

    async def async_will_remove_from_hass(self):
        self._hub.remove_callback("d", self._switch_join)

    def process_callback(self, sigtype, join, value):
        self._state = value
        # _LOGGER.info(f"switch state: {value}")
        self.async_write_ha_state()

    @property
    def available(self):
        # return self._hub.is_available()
        return True

    @property
    def name(self):
        return self._name

    @property
    def should_poll(self):
        return False

    @property
    def device_class(self):
        return self._device_class

    @property
    def state(self):
        if self._state != 0:
            return STATE_ON
        else:
            return STATE_OFF

    @property
    def is_on(self):
        return self._state

    async def async_turn_on(self, **kwargs):
        self._hub.set_digital(self._switch_join, 1)

    async def async_turn_off(self, **kwargs):
        self._hub.set_digital(self._switch_join, 0)
