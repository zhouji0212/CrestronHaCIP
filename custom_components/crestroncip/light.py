"""Platform for Crestron Light integration."""
import voluptuous as vol
import logging
import math
import homeassistant.helpers.config_validation as cv
from homeassistant.components.light import (
    LightEntity,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR_TEMP,
    SUPPORT_COLOR,
    COLOR_MODE_BRIGHTNESS,
    COLOR_MODE_COLOR_TEMP,
    COLOR_MODE_HS,)
from homeassistant.const import CONF_NAME, CONF_TYPE
from .const import (
    HUB,
    DOMAIN,
    CONF_BRIGHTNESS_JOIN,
    CONF_COLOR_TEMP_JOIN,
    CONF_COLOR_H_JOIN,
    CONF_COLOR_S_JOIN)
from .crestroncipsync import CIPSocketClient
from homeassistant.util import color
CONF_BRIGHT = "brightness"
CONF_COLOR_HS = "color_hs"
CONF_COLOR_TEMP = "color_temp"
_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_TYPE): cv.string,
        vol.Required(CONF_BRIGHTNESS_JOIN): cv.positive_int,
        vol.Optional(CONF_COLOR_TEMP_JOIN): cv.positive_int,
        vol.Optional(CONF_COLOR_H_JOIN): cv.positive_int,
        vol.Optional(CONF_COLOR_S_JOIN): cv.positive_int
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
        self._supported_colormodes = set([COLOR_MODE_BRIGHTNESS])
        self._color_mode = COLOR_MODE_BRIGHTNESS
        self._hub = client
        self._name = config.get(CONF_NAME)
        self._type = config.get(CONF_TYPE)
        self._brightness_join = config.get(CONF_BRIGHTNESS_JOIN)
        # self._brightness_join = self._hub.get_analog()
        self._brightness = self._hub.get_analog(self._brightness_join)
        self._color_temp_join = 0
        self._color_temp_min = color.color_temperature_kelvin_to_mired(6000)
        self._color_temp_max = color.color_temperature_kelvin_to_mired(3000)
        self._color_h_join = 0
        self._color_s_join = 0
        self._color_hs = (0, 0)
        _LOGGER.debug(f"{self._name},{self._type},{self._brightness_join}")
        if self._type == CONF_BRIGHT:
            self._supported_features = SUPPORT_BRIGHTNESS
        elif self._type == CONF_COLOR_TEMP:
            self._supported_features = (
                SUPPORT_BRIGHTNESS | SUPPORT_COLOR_TEMP)
            self._color_temp_join = config.get(CONF_COLOR_TEMP_JOIN)
            self._supported_colormodes = set(
                [COLOR_MODE_COLOR_TEMP, COLOR_MODE_BRIGHTNESS])
            self._color_mode = COLOR_MODE_COLOR_TEMP
            self._color_temp = self._hub.get_analog(self._color_temp_join)
        elif self._type == CONF_COLOR_HS:
            self._supported_features = (
                SUPPORT_BRIGHTNESS | SUPPORT_COLOR)
            self._supported_colormodes = set(
                [COLOR_MODE_HS, COLOR_MODE_BRIGHTNESS])
            self._color_mode = COLOR_MODE_HS
            self._color_h_join = config.get(CONF_COLOR_H_JOIN)
            self._color_s_join = config.get(CONF_COLOR_S_JOIN)
            self._color_h = self._hub.get_analog(self._color_h_join)
            self._color_s = self._hub.get_analog(self._color_h_join)

        self._save_brightness = 100

    async def async_added_to_hass(self):
        if self._type == CONF_COLOR_TEMP:
            self._hub.register_callback(
                "a", self._color_temp_join, self.process_color_temp_callback
            )
        if self._type == CONF_COLOR_HS:
            self._hub.register_callback(
                "a", self._color_h_join, self.process_color_callback
            )
            self._hub.register_callback(
                "a", self._color_s_join, self.process_color_callback
            )

        self._hub.register_callback(
            "a", self._brightness_join, self.process_bright_callback
        )

    async def async_will_remove_from_hass(self):
        self._hub.remove_callback("a", self._brightness_join)
        if self._type == CONF_COLOR_TEMP:
            self._hub.remove_callback("a", self._color_temp_join)
        if self._type == CONF_COLOR_HS:
            self._hub.remove_callback("a", self._color_h_join)
            self._hub.remove_callback("a", self._color_s_join)

    def process_bright_callback(self, sigtype, join, value):
        self._brightness = value*255/100
        self.async_write_ha_state()

    def process_color_temp_callback(self, sigtype, join, value):
        if value > 0:
            self._color_temp = color.color_temperature_kelvin_to_mired(value)
        self.async_write_ha_state()

    def process_color_callback(self, sigtype, join, value):
        if join == self._color_h_join:
            self._color_hs = (float(value), float(self._color_hs[1]))
        if join == self._color_s_join:
            self._color_hs = (float(self._color_hs[0]), float(value))
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
        if self._brightness > 0:
            return self._brightness
        else:
            return 0

    @property
    def supported_color_modes(self):
        return self._supported_colormodes

    @property
    def color_mode(self):
        return self._color_mode

    @property
    def color_temp(self):
        return self._color_temp

    @property
    def hs_color(self):
        return self._color_hs

    @property
    def min_mireds(self):
        return self._color_temp_min

    @property
    def max_mireds(self):
        return self._color_temp_max

    @property
    def is_on(self):
        if self._brightness > 0:
            return True
        else:
            return False

    async def async_turn_on(self, **kwargs):
        _LOGGER.info(f"on..{kwargs}")
        if "brightness" in kwargs:
            self._save_brightness = int(kwargs["brightness"]*100/255)
            self._hub.set_analog(self._brightness_join, self._save_brightness)
        if "color_temp" in kwargs:
            self._hub.set_analog(
                self._color_temp_join,
                round(color.color_temperature_mired_to_kelvin(
                    int(kwargs["color_temp"]))/100)*100
            )
        if "hs_color" in kwargs:
            self._hub.set_analog(
                self._color_h_join,
                int(kwargs["hs_color"][0])
            )
            self._hub.set_analog(
                self._color_s_join,
                int(kwargs["hs_color"][1])
            )

        else:
            self._hub.set_analog(self._brightness_join, self._save_brightness)
        await self.async_update_ha_state()

    async def async_turn_off(self, **kwargs):
        self._hub.set_analog(self._brightness_join, 0)
        await self.async_update_ha_state()
