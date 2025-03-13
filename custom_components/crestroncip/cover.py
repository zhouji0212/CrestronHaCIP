from typing import Any
from . import XPanelClient,HomeAssistant
import asyncio
import logging
import voluptuous as vol

import homeassistant.helpers.config_validation as cv
from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
    CoverDeviceClass
)
from homeassistant.const import CONF_NAME, CONF_TYPE
from .const import (
    HUB,
    DOMAIN,
    IS_CLOSED_FB_JOIN,
    CONF_POSITION_JOIN,
    CONF_POSITION_FB_JOIN,
    CONF_OPEN_JOIN,
    CONF_CLOSE_JOIN,
    CONF_STOP_JOIN,
    CONF_OPEN_TILT_JOIN,
    CONF_CLOSE_TILT_JOIN,
    CONF_STOP_TILT_JOIN,
    CONF_TILT_POSITION_JOIN,
    CONF_TILT_POSITION_FB_JOIN
)
_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_TYPE): cv.string,
        vol.Optional(CONF_POSITION_JOIN): cv.positive_int,
        vol.Optional(CONF_POSITION_FB_JOIN): cv.positive_int,
        vol.Required(CONF_OPEN_JOIN): cv.positive_int,
        vol.Required(CONF_CLOSE_JOIN): cv.positive_int,
        vol.Required(CONF_STOP_JOIN): cv.positive_int,
        vol.Required(IS_CLOSED_FB_JOIN): cv.positive_int,
        vol.Optional(CONF_OPEN_TILT_JOIN): cv.positive_int,
        vol.Optional(CONF_CLOSE_TILT_JOIN): cv.positive_int,
        vol.Optional(CONF_STOP_TILT_JOIN): cv.positive_int,
        vol.Optional(CONF_TILT_POSITION_JOIN): cv.positive_int,
        vol.Optional(CONF_TILT_POSITION_FB_JOIN): cv.positive_int,
    },
    extra=vol.ALLOW_EXTRA,
)
CONF_COVER_TYPE_MAP = {
    'open_close': (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
    ),
    'position': (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.SET_POSITION | CoverEntityFeature.STOP
    ),
    'tilt': (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.SET_POSITION | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_TILT_POSITION | CoverEntityFeature.STOP_TILT | CoverEntityFeature.OPEN_TILT
        | CoverEntityFeature.CLOSE_TILT
    ),

}


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None):
    hub = hass.data[DOMAIN][HUB]
    type = config.get(CONF_TYPE)
    entity = []
    if type == 'open_close':
        entity = [OpenCloseCurtain(hub, config, type)]
    elif type == 'position':
        entity = [PositionCurtain(hub, config, type)]
    elif type == 'tilt':
        entity = [TiltCurtain(hub, config, type)]
    async_add_entities(entity)


class OpenCloseCurtain(CoverEntity):
    def __init__(self, client: XPanelClient, config, type: str):
        self._hub = client
        self._open_join = config.get(CONF_OPEN_JOIN)
        self._close_join = config.get(CONF_CLOSE_JOIN)
        self._stop_join = config.get(CONF_STOP_JOIN)
        self._attr_name = config.get(CONF_NAME)
        self._attr_device_class = CoverDeviceClass.CURTAIN
        self._attr_unique_id = f"{self._attr_name}_{self._attr_device_class}_{self._stop_join}"
        self._attr_supported_features = CONF_COVER_TYPE_MAP[type]
        self._attr_should_poll = False
        self._is_closed_fb_join = config.get(IS_CLOSED_FB_JOIN)
        self._attr_current_cover_position = 50
        self._attr_is_closed = self._hub.get_digital(self._is_closed_fb_join)

    async def async_added_to_hass(self):
        await self._hub.register_callback(
            "d", self._is_closed_fb_join, self.curtain_is_closed_callback)
        self._is_closed = self._hub.get_digital(self._is_closed_fb_join)
        self.schedule_update_ha_state()

    async def async_will_remove_from_hass(self):
        await self._hub.remove_callback(self.curtain_is_closed_callback)

    def curtain_is_closed_callback(self, sigtype, join, value):
        self._attr_is_closed = value
        self.async_schedule_update_ha_state()

    async def async_open_cover(self, **kwargs):
        self._hub.pulse(self._open_join)
        self._attr_is_closed = False
        self.async_schedule_update_ha_state()

    async def async_close_cover(self, **kwargs):
        self._hub.pulse(self._close_join)
        self._attr_is_closed = True
        self.async_schedule_update_ha_state()

    async def async_stop_cover(self, **kwargs):
        self._hub.pulse(self._stop_join)
        await asyncio.sleep(0.5)
        self._attr_is_closed = self._hub.get_digital(self._is_closed_fb_join)
        self.async_schedule_update_ha_state()


class PositionCurtain(OpenCloseCurtain):
    def __init__(self, client: XPanelClient, config, device_type: str):
        super().__init__(client, config, device_type)
        self._pos_join = config.get(CONF_POSITION_JOIN)
        self._pos_join_fb = config.get(CONF_POSITION_FB_JOIN)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        await self._hub.register_callback(
            "a", self._pos_join_fb, self.curtain_position_callback)
        self._attr_current_cover_position = self._hub.get_analog(
            self._pos_join_fb)
        self._attr_is_closed = self._hub.get_digital(self._is_closed_fb_join)
        self.schedule_update_ha_state()

    async def async_will_remove_from_hass(self):
        await super().async_will_remove_from_hass()
        await self._hub.remove_callback("a", self._pos_join_fb)

    async def async_set_cover_position(self, **kwargs):
        position = int(kwargs["position"])
        self._attr_current_cover_position = position
        self._hub.set_analog(self._pos_join, position)
        self._attr_is_closed = not bool(position)
        self.schedule_update_ha_state()

    def curtain_position_callback(self, sigtype, join, value):
        self._attr_is_closed = not bool(value)
        self._attr_current_cover_position = value
        self.schedule_update_ha_state()

    async def async_stop_cover(self, **kwargs):
        self._hub.pulse(self._stop_join)
        self.schedule_update_ha_state()


class TiltCurtain(PositionCurtain):
    def __init__(self, client: XPanelClient, config, device_type: str):
        super().__init__(client, config, device_type)
        self._attr_device_class = CoverDeviceClass.BLIND
        self._cover_tilt_open_join = config.get(CONF_OPEN_TILT_JOIN)
        self._cover_tilt_close_join = config.get(CONF_CLOSE_TILT_JOIN)
        self._cover_tilt_stop_join = config.get(CONF_STOP_TILT_JOIN)
        self._cover_tilt_pos_join = config.get(CONF_TILT_POSITION_JOIN)
        self._cover_tilt_pos_join_fb = config.get(CONF_TILT_POSITION_FB_JOIN)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        await self._hub.register_callback(
            "a", self._cover_tilt_pos_join, self.curtain_tilt_callback)
        self._attr_current_cover_tilt_position = self._hub.get_analog(
            self._cover_tilt_pos_join_fb)

    async def async_will_remove_from_hass(self):
        await super().async_will_remove_from_hass()
        await self._hub.remove_callback("a", self._cover_tilt_pos_join_fb)

    async def async_open_cover_tilt(self, **kwargs):
        self._hub.pulse(self._cover_tilt_open_join)
        self._attr_current_cover_tilt_position = 100
        self.schedule_update_ha_state()

    async def async_close_cover_tilt(self, **kwargs):
        self._hub.pulse(self._cover_tilt_close_join)
        self._attr_current_cover_tilt_position = 0
        self.schedule_update_ha_state()

    async def async_stop_cover_tilt(self, **kwargs):
        self._hub.pulse(self._cover_tilt_stop_join)

    async def async_set_cover_tilt_position(self, **kwargs: Any):
        # _LOGGER.debug(f'tilt:{kwargs}')
        self._hub.set_analog(self._cover_tilt_pos_join,
                             int(kwargs["tilt_position"]))

    def curtain_tilt_callback(self, sigtype, join, value):
        self._attr_current_cover_tilt_position = value
        self.async_schedule_update_ha_state()
