"""Platform for Crestron Light integration."""
import asyncio
from collections import defaultdict
import voluptuous as vol
import logging
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.components.light import (
    LightEntity,
    ColorMode,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN)
from homeassistant.const import CONF_NAME, CONF_TYPE
from .const import (
    HUB,
    DOMAIN,
    CONF_BRIGHTNESS_JOIN,
    CONF_BRIGHTNESS_FB_JOIN,
    CONF_SWITCH_ON_JOIN,
    CONF_SWITCH_OFF_JOIN,
    CONF_SWITCH_FB_JOIN,
    CONF_COLOR_TEMP_JOIN,
    CONF_COLOR_TEMP_FB_JOIN,
    CONF_COLOR_COOL_JOIN,
    CONF_COLOR_WARM_JOIN,
    CONF_COLOR_TEMP_MAX,
    CONF_COLOR_TEMP_MIN)
from . import XPanelClient
from homeassistant.util import color
_LOGGER = logging.getLogger(__name__)
CONF_SWITCH = "switch"
CONF_BRIGHTNESS = "brightness"
CONF_COLOR_TEMP = "color_temp"



CONF_SUPPORT_COLOR_MODES_MAP = {
    CONF_SWITCH: set([ColorMode.ONOFF,]),
    CONF_BRIGHTNESS: set([ColorMode.BRIGHTNESS,]),
    CONF_COLOR_TEMP: set([ColorMode.COLOR_TEMP,]),
}
CONF_COLOR_MODE_MAP = {
    CONF_SWITCH: ColorMode.ONOFF,
    CONF_BRIGHTNESS: ColorMode.BRIGHTNESS,
    CONF_COLOR_TEMP: ColorMode.COLOR_TEMP,
}


PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_TYPE): cv.string,
        vol.Optional(CONF_SWITCH_ON_JOIN): cv.positive_int,
        vol.Optional(CONF_SWITCH_OFF_JOIN): cv.positive_int,
        vol.Optional(CONF_SWITCH_FB_JOIN): cv.positive_int,
        vol.Optional(CONF_BRIGHTNESS_JOIN): cv.positive_int,
        vol.Optional(CONF_BRIGHTNESS_FB_JOIN): cv.positive_int,
        vol.Optional(CONF_COLOR_TEMP_JOIN): cv.positive_int,
        vol.Optional(CONF_COLOR_TEMP_FB_JOIN): cv.positive_int,
        vol.Optional(CONF_COLOR_COOL_JOIN): cv.positive_int,
        vol.Optional(CONF_COLOR_WARM_JOIN): cv.positive_int,
        vol.Optional(CONF_COLOR_TEMP_MAX): cv.positive_int,
        vol.Optional(CONF_COLOR_TEMP_MIN): cv.positive_int,
    },
    extra=vol.ALLOW_EXTRA,
)


def scale_color_temp_to_brightness(channelvalue: tuple, brightness) -> list:
    _LOGGER.info(f"ChannelValue:{channelvalue}")
    brightness_scale = (brightness / 255)
    scaled_ct = []
    for t in channelvalue:
        scaled_ct.append(round(t * brightness_scale))
    return scaled_ct


def scale_color_to_brightness(color: tuple, brightness) -> list:
    """color:(255,255,255),brightness:255"""
    brightness_scale = (brightness / 255)
    scaled_color = []
    for c in color:
        scaled_color.append(c * brightness_scale)
    return scaled_color


def scale_255_to_65535(value: int):
    if value <= 0:
        return 0
    return int(value*65535/255)


def scale_65535_to_255(value: int):
    if value <= 0:
        return 0
    return int(value*255/65535)


def calc_dali_short_addr(short_addr: int) -> tuple[int, int]:
    if short_addr > 79:
        short_addr = 127
    return ((short_addr << 1), (short_addr << 1) | 1)


class CrestronLightBase(LightEntity):
    def __init__(self, client: XPanelClient, config: ConfigType, device_type: str) -> None:
        self._attr_name = config.get(CONF_NAME)
        self._type = device_type
        self._attr_unique_id = f"{self._attr_name}_{self._type}"
        self._attr_is_on = False
        self._attr_brightness = 0
        self._saved_brightness = 255
        self._hub = client
        # self._attr_supported_features = CONF_SUPPORT_MAP.get(self._type)
        self._attr_supported_color_modes = CONF_SUPPORT_COLOR_MODES_MAP.get(
            self._type)
        self._attr_color_mode = CONF_COLOR_MODE_MAP.get(self._type)
        self._attr_extra_state_attributes = {}
        _LOGGER.debug(
            f"{self._attr_name},{self._type} {self._attr_color_mode} {self._attr_supported_color_modes} init")


class SwitchLight(CrestronLightBase):
    def __init__(self, client: XPanelClient, config, device_type: str):
        super().__init__(client, config, device_type)
        self._switch_join_on = config.get(CONF_SWITCH_ON_JOIN)
        self._switch_join_off = config.get(CONF_SWITCH_OFF_JOIN)
        self._switch_join_fb = config.get(CONF_SWITCH_FB_JOIN)
        self._state = client.get_digital(self._switch_join_fb)
        self._attr_unique_id = f"{self._attr_unique_id}_{self._switch_join_on}"

    async def async_added_to_hass(self):
        await self._hub.register_callback(
            "d", self._switch_join_fb, self.process_switch_callback)

    async def async_will_remove_from_hass(self):
        await self._hub.remove_callback("d", self._switch_join_fb)

    async def async_turn_on(self, **kwargs):
        self._hub.pulse(self._switch_join_on)

    async def async_turn_off(self, **kwargs):
        self._hub.pulse(self._switch_join_off)

    def process_switch_callback(self, sigtype, join, value):
        self._attr_is_on = bool(value)
        self.schedule_update_ha_state()


class BrightnessLight(CrestronLightBase):

    def __init__(self, client: XPanelClient, config: ConfigType, device_type: str):
        super().__init__(client, config, device_type)
        self._brightness_join = config.get(CONF_BRIGHTNESS_JOIN)
        self._brightness_fb_join = config.get(CONF_BRIGHTNESS_FB_JOIN)
        self._attr_unique_id = f"{self._attr_unique_id}_{self._brightness_join}"
        self._attr_brightness = self._hub.get_analog(
            self._brightness_fb_join)*255/65535
        self._attr_is_on = bool(self._attr_brightness)

    async def async_added_to_hass(self):
        await self._hub.register_callback(
            "a", self._brightness_fb_join, self.process_bright_callback
        )

    async def async_will_remove_from_hass(self):
        await self._hub.remove_callback("a", self._brightness_fb_join)

    async def async_turn_on(self, **kwargs):
        _LOGGER.debug(f"Turn on:{kwargs}")
        if ATTR_BRIGHTNESS in kwargs:
            self._attr_brightness = kwargs[ATTR_BRIGHTNESS]
            if bool(self._attr_brightness):
                self._attr_is_on = True
            self._hub.set_analog(self._brightness_join, int(
                kwargs[ATTR_BRIGHTNESS]*65535/255))
        else:
            if not bool(self._attr_brightness):
                self._hub.set_analog(self._brightness_join, 65535)
        self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        self._hub.set_analog(self._brightness_join, 0)

    def process_bright_callback(self, sigtype, join, value):
        self._attr_brightness = (value*255/65535)
        self._attr_is_on = bool(self._attr_brightness)
        self.schedule_update_ha_state()


class ColorTempLight(BrightnessLight):
    def __init__(self, client: XPanelClient, config: ConfigType, device_type):
        super().__init__(client, config, device_type)
        self._color_temp_join = config.get(CONF_COLOR_TEMP_JOIN)
        self._color_temp_fb_join = config.get(CONF_COLOR_TEMP_FB_JOIN)
        self._attr_max_color_temp_kelvin = config.get(
            CONF_COLOR_TEMP_MAX) or 6500
        self._attr_min_color_temp_kelvin = config.get(
            CONF_COLOR_TEMP_MIN) or 3000
        self._attr_color_temp_kelvin = self._hub.get_analog(
            self._color_temp_fb_join)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        await self._hub.register_callback(
            "a", self._color_temp_fb_join, self.process_color_temp_callback
        )

    async def async_will_remove_from_hass(self):
        await super().async_will_remove_from_hass()
        await self._hub.remove_callback("a", self._color_temp_fb_join)

    async def async_turn_on(self, **kwargs):
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            self._hub.set_analog(
                self._color_temp_join,
                int(kwargs[ATTR_COLOR_TEMP_KELVIN])
            )
            self._attr_color_temp_kelvin = int(kwargs[ATTR_COLOR_TEMP_KELVIN])
        await super().async_turn_on(**kwargs)

    async def async_turn_off(self, **kwargs):
        await super().async_turn_off(**kwargs)

    def process_color_temp_callback(self, sigtype, join, value):
        if value > 0:
            self._attr_color_temp_kelvin = int(value)
        self.schedule_update_ha_state()



CONST_LIGHT_DEVICE_ENTITY_MAP = {
    CONF_SWITCH: SwitchLight,
    CONF_BRIGHTNESS: BrightnessLight,
    CONF_COLOR_TEMP: ColorTempLight,
}


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hub: XPanelClient = hass.data[DOMAIN][HUB]
    device_type = config.get(CONF_TYPE)
    if isinstance(device_type, str) and (device_type != ""):
        light_list = [CONST_LIGHT_DEVICE_ENTITY_MAP[device_type]
                        (hub, config, device_type)]
        async_add_entities(light_list)
