import voluptuous as vol
import logging

import homeassistant.helpers.config_validation as cv
from homeassistant.components.switch import SwitchEntity
from homeassistant.const import (
    CONF_NAME, CONF_DEVICE_CLASS)
from .const import (HUB, DOMAIN, CONF_SWITCH_ON_JOIN,
                    CONF_SWITCH_OFF_JOIN, CONF_SWITCH_FB_JOIN)
from . import XPanelClient
_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_SWITCH_ON_JOIN): cv.positive_int,
        vol.Required(CONF_SWITCH_OFF_JOIN): cv.positive_int,
        vol.Optional(CONF_SWITCH_ON_JOIN, default=0): cv.positive_int,
        vol.Optional(CONF_DEVICE_CLASS, default="switch"): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hub = hass.data[DOMAIN][HUB]
    device_name = config.get(CONF_NAME)
    if type(device_name) == str and device_name != "":
        entity = [CrestronSwitch(hub, config)]
        async_add_entities(entity)


class CrestronSwitch(SwitchEntity):
    def __init__(self, hub: XPanelClient, config):
        self._hub = hub
        self._attr_name = config.get(CONF_NAME)
        self._attr_is_on = False
        self._switch_join_on = config.get(CONF_SWITCH_ON_JOIN)
        self._attr_unique_id = f"{self._attr_name}_{self._switch_join_on}"
        self._switch_join_off = config.get(CONF_SWITCH_OFF_JOIN)
        self._switch_join_fb = config.get(CONF_SWITCH_FB_JOIN)
        self._device_class = config.get(CONF_DEVICE_CLASS)
        if self._switch_join_fb == 0:
            self._switch_join_fb = self._switch_join_on

    async def async_added_to_hass(self):
        await self._hub.register_callback(
            "d", self._switch_join_fb, self.process_callback)
        self._attr_is_on = self._hub.get_digital(self._switch_join_fb)
        self.schedule_update_ha_state()

    async def async_will_remove_from_hass(self):
        await self._hub.remove_callback("d", self._switch_join_fb)

    def process_callback(self, sigtype, join, value):
        self._attr_is_on = value
        self.schedule_update_ha_state()

    async def async_turn_on(self, **kwargs):
        self._hub.pulse(self._switch_join_on)
        # self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        self._hub.pulse(self._switch_join_off)
        # await self.async_update_ha_state()
