"""Platform for Crestron Light integration."""
import voluptuous as vol
import logging

import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import LightEntity, SUPPORT_BRIGHTNESS, SUPPORT_COLOR_TEMP
from homeassistant.const import CONF_NAME, CONF_TYPE
from .const import HUB, DOMAIN, CONF_BRIGHTNESS_JOIN
from .crestroncipsync import CIPSocketClient

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_TYPE): cv.string,
        vol.Required(CONF_BRIGHTNESS_JOIN): cv.positive_int,
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hub = hass.data[DOMAIN][HUB]
    entity = [CrestronLight(hub, config)]
    async_add_entities(entity)


class CrestronLight(LightEntity):
    def __init__(self, client: CIPSocketClient, config):

        self._supported_features = SUPPORT_BRIGHTNESS
        self._hub = client
        self._name = config.get(CONF_NAME)
        self._brightness_join = config.get(CONF_BRIGHTNESS_JOIN)
        if config.get(CONF_TYPE) == "brightness":
            self._supported_features = SUPPORT_BRIGHTNESS
        self._brightness = self._hub.get_analog(self._brightness_join)
        self._save_brightness = 100

    async def async_added_to_hass(self):
        self._hub.register_callback(
            "a", self._brightness_join, self.process_callback)

    async def async_will_remove_from_hass(self):
        self._hub.remove_callback("a", self._brightness_join)

    def process_callback(self, sigtype, join, value):
        self._brightness = value*255/100
        self.async_write_ha_state()

    @property
    def available(self):
        return self._hub.is_available()

    @property
    def name(self):
        return self._name

    @property
    def supported_features(self):
        return self._supported_features

    @property
    def should_poll(self):
        return False

    @property
    def brightness(self):
        if self._supported_features == SUPPORT_BRIGHTNESS:
            return self._brightness

    @property
    def is_on(self):
        if self._supported_features == SUPPORT_BRIGHTNESS:
            if self._brightness > 0:
                return True
            else:
                return False

    async def async_turn_on(self, **kwargs):
        if "brightness" in kwargs:
            self._save_brightness = int(kwargs["brightness"]*100/255)
        self._hub.set_analog(self._brightness_join, self._save_brightness)

    async def async_turn_off(self, **kwargs):
        self._hub.set_analog(self._brightness_join, 0)
