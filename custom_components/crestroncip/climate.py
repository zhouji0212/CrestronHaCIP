"""Platform for Crestron Thermostat integration."""

import voluptuous as vol
import logging
import asyncio
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from . import XPanelClient, HomeAssistant, HUB
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.climate import ClimateEntity, HVACMode, ClimateEntityFeature
from homeassistant.components.climate.const import (
    FAN_OFF,
    FAN_LOW,
    FAN_HIGH,
    FAN_MEDIUM,
    FAN_AUTO,
    ATTR_HVAC_MODE,
    ATTR_FAN_MODE
)
from homeassistant.const import CONF_NAME, CONF_TYPE, ATTR_TEMPERATURE
from . import XPanelClient
from .const import (
    HUB,
    DOMAIN,
    CONF_AC_POWER_ON_JOIN,
    CONF_AC_POWER_OFF_JOIN,
    CONF_WH_POWER_ON_JOIN,
    CONF_WH_POWER_ON_FB_JOIN,
    CONF_WH_POWER_OFF_JOIN,
    CONF_AC_MODE_JOIN,
    CONF_AC_MODE_FB_JOIN,
    CONF_AC_FAN_MODE_JOIN,
    CONF_AC_FAN_MODE_FB_JOIN,
    CONF_AC_SET_TEMP_JOIN,
    CONF_AC_SET_TEMP_FB_JOIN,
    CONF_AC_MAX_TEMP,
    CONF_AC_MIN_TEMP,
    CONF_AC_CURRENT_TEMP_FB_JOIN,
    CONF_AC_CURRENT_HUMIDITY_FB_JOIN,
    CONF_AC_TEMP_STEP,
    CONF_DIVISOR,

)

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_TYPE): cv.string,
        vol.Optional(CONF_AC_POWER_ON_JOIN): cv.positive_int,
        vol.Optional(CONF_AC_POWER_OFF_JOIN): cv.positive_int,
        vol.Optional(CONF_WH_POWER_ON_JOIN): cv.positive_int,
        vol.Optional(CONF_WH_POWER_ON_FB_JOIN): cv.positive_int,
        vol.Optional(CONF_WH_POWER_OFF_JOIN): cv.positive_int,
        vol.Optional(CONF_AC_MODE_JOIN): cv.positive_int,
        vol.Optional(CONF_AC_MODE_FB_JOIN): cv.positive_int,
        vol.Optional(CONF_AC_SET_TEMP_JOIN): cv.positive_int,
        vol.Optional(CONF_AC_SET_TEMP_FB_JOIN): cv.positive_int,
        vol.Optional(CONF_AC_CURRENT_TEMP_FB_JOIN): cv.positive_int,
        vol.Optional(CONF_AC_CURRENT_HUMIDITY_FB_JOIN, default=1): cv.positive_int,
        vol.Optional(CONF_AC_FAN_MODE_JOIN): cv.positive_int,
        vol.Optional(CONF_AC_FAN_MODE_FB_JOIN): cv.positive_int,
        vol.Optional(CONF_AC_MAX_TEMP, default=35): cv.positive_int,
        vol.Optional(CONF_AC_MIN_TEMP, default=16): cv.positive_int,
        vol.Optional(CONF_AC_TEMP_STEP, default=1): cv.positive_float,
        vol.Optional(CONF_DIVISOR, default=1): cv.positive_int
    },
    extra=vol.ALLOW_EXTRA,
)

CONF_MODES_MAP = {
    "AC": [
        HVACMode.HEAT,
        HVACMode.COOL,
        HVACMode.OFF,
        HVACMode.FAN_ONLY,
        HVACMode.DRY,
        HVACMode.HEAT_COOL
    ],
    "FH": [HVACMode.HEAT, HVACMode.OFF]
}
CONF_SUPPORT_MAP = {
    "AC": ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF,
    "FH": ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
}

CONF_CURRENT_AC_MODE_MAP = {
    0: HVACMode.OFF,
    1: HVACMode.COOL,
    2: HVACMode.HEAT,
    3: HVACMode.DRY,
    4: HVACMode.FAN_ONLY,
    5: HVACMode.HEAT_COOL
}
CONF_CURRENT_FAN_MODE_MAP = {
    0: FAN_OFF,
    1: FAN_HIGH,
    2: FAN_MEDIUM,
    3: FAN_LOW,
    4: FAN_AUTO
}


async def async_setup_platform(hass: HomeAssistant, config, async_add_entities, discovery_info=None) -> None:
    hub: XPanelClient = hass.data[DOMAIN][HUB]
    device_name = config.get(CONF_NAME)
    device_type = config.get(CONF_TYPE)
    entity = []
    if isinstance(device_type, str):
        _LOGGER.debug(f"climate_add_device:{device_name}-{device_type}")
        if device_type == "AC":
            entity = [AcPanel(
                hub, config, hass.config.units.temperature_unit, device_type)]
        if device_type == "FH":
            entity = [FHPanel(
                hub, config, hass.config.units.temperature_unit, device_type)]
        async_add_entities(entity)


class Thermostat(ClimateEntity):
    def __init__(self, hub: XPanelClient, config, unit, device_type):
        self._hub = hub
        self._ac_mode_join = config.get(CONF_AC_MODE_JOIN)
        self._ac_mode_fb_join = config.get(CONF_AC_MODE_FB_JOIN)
        self._ac_set_temp_join = config.get(CONF_AC_SET_TEMP_JOIN)
        self._ac_set_temp_fb_join = config.get(CONF_AC_SET_TEMP_JOIN)
        self._ac_current_temp_fb_join = config.get(
            CONF_AC_CURRENT_TEMP_FB_JOIN)
        self._ac_current_humidity_fb_join = config.get(
            CONF_AC_CURRENT_HUMIDITY_FB_JOIN)
        self._attr_available = True
        self._ac_power = False
        self._attr_hvac_modes = CONF_MODES_MAP[device_type]
        self._attr_supported_features = CONF_SUPPORT_MAP[device_type]
        self._attr_should_poll = False
        self._attr_temperature_unit = unit
        self._attr_name = config.get(CONF_NAME)
        self._attr_unique_id = f"hvac_{self._attr_name}_{self._ac_mode_join}"
        self._attr_target_temperature_high = config.get(CONF_AC_MAX_TEMP)
        self._attr_max_temp = self._attr_target_temperature_high
        self._attr_target_temperature_low = config.get(CONF_AC_MIN_TEMP)
        self._attr_min_temp = self._attr_target_temperature_low
        self._attr_target_temperature_step = config.get(
            CONF_AC_TEMP_STEP)
        self._attr_current_humidity = 1
        self._attr_current_temperature = 3
        self._attr_target_temperature = 3
        self._divisor = config.get(CONF_DIVISOR)
        self._enable_turn_on_off_backwards_compatibility = False

    async def async_added_to_hass(self):
        _LOGGER.debug(
            f'reg current_temp_fb_join:{self._ac_current_temp_fb_join}')
        ct = self._hub.get_analog(
            self._ac_current_temp_fb_join)
        if bool(ct):
            self._attr_current_temperature = (ct/self._divisor)
        tt = self._hub.get_analog(
            self._ac_set_temp_fb_join)
        if bool(tt):
            self._attr_target_temperature = (tt/self._divisor)
        await self._hub.register_callback(
            "a", self._ac_current_temp_fb_join, self.process_temp_fb_callback)
        _LOGGER.debug(f'reg set_temp_fb_join:{self._ac_set_temp_fb_join}')
        await self._hub.register_callback(
            "a", self._ac_set_temp_fb_join, self.process_set_temp_fb_callback)

    async def async_will_remove_from_hass(self):
        await self._hub.remove_callback("a", self._ac_set_temp_fb_join)
        await self._hub.remove_callback("a", self._ac_current_temp_fb_join)

    async def async_set_temperature(self, **kwargs):
        _LOGGER.debug(f"settemp:-{kwargs}")
        if ATTR_TEMPERATURE in kwargs.keys():
            self._attr_target_temperature = kwargs[ATTR_TEMPERATURE]
            self._hub.set_analog(self._ac_set_temp_join,
                                 int(self._attr_target_temperature * self._divisor))

    def process_set_temp_fb_callback(self, sigtype, join, value):
        _LOGGER.debug(f'set temp change:{value}')
        self._attr_target_temperature = int(value/self._divisor)
        self.schedule_update_ha_state()

    def process_temp_fb_callback(self, sigtype, join, value):
        _LOGGER.debug(f'current temp change:{value}')
        self._attr_current_temperature = int(value/self._divisor)
        self.schedule_update_ha_state()


class AcPanel(Thermostat):
    def __init__(self, hub: XPanelClient, config, unit, device_type):
        super().__init__(hub, config, unit, device_type)
        self._ac_power_on_join = config.get(CONF_AC_POWER_ON_JOIN)
        self._ac_power_off_join = config.get(CONF_AC_POWER_OFF_JOIN)
        self._attr_fan_modes = [FAN_OFF, FAN_HIGH,
                                FAN_MEDIUM, FAN_LOW, FAN_AUTO]
        self._ac_fan_mode_join = config.get(CONF_AC_FAN_MODE_JOIN)
        self._ac_fan_mode_fb_join = config.get(CONF_AC_FAN_MODE_FB_JOIN)
        self._attr_hvac_mode = CONF_CURRENT_AC_MODE_MAP.get(int(self._hub.get_analog(
            self._ac_mode_fb_join)))
        self._attr_fan_mode = CONF_CURRENT_FAN_MODE_MAP.get(int(self._hub.get_analog(
            self._ac_fan_mode_fb_join)))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)},
            name=self._attr_name,
            model=f'HVAC_Panel',
            via_device=(DOMAIN, 'Climate'),
            sw_version='1.0',
            manufacturer='Jack_Zhou',
        )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        await self._hub.register_callback(
            "a", self._ac_mode_fb_join, self._process_mode_fb_callback)
        await self._hub.register_callback(
            "a", self._ac_fan_mode_fb_join, self._process_fan_mode_fb_callback)
        if isinstance(self._ac_current_humidity_fb_join, int):
            hmi = self._hub.get_analog(
                self._ac_current_humidity_fb_join)
            self._attr_current_humidity = hmi
            await self._hub.register_callback(
                "a", self._ac_current_humidity_fb_join, self._process_humidity_fb_callback)

    async def async_will_remove_from_hass(self):
        await super().async_will_remove_from_hass()
        await self._hub.remove_callback("a", self._ac_mode_fb_join)
        await self._hub.remove_callback("a", self._ac_fan_mode_fb_join)

    def _set_power_on(self):
        self._hub.pulse(self._ac_power_on_join)

    def _set_power_off(self):
        self._hub.pulse(self._ac_power_off_join)

    def turn_on(self) -> None:
        if not self._ac_power:
            self._set_power_on()

    def turn_off(self) -> None:
        self._set_power_off()

    async def async_set_temperature(self, **kwargs):
        await super().async_set_temperature(**kwargs)
        if ATTR_HVAC_MODE in kwargs.keys():
            await self.async_set_hvac_mode(kwargs[ATTR_HVAC_MODE])

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode != '':
            self._attr_hvac_mode = hvac_mode
            if hvac_mode == HVACMode.OFF:
                self._set_power_off()
                await asyncio.sleep(0.1)
                self._hub.set_analog(self._ac_mode_join, 0)
                await asyncio.sleep(0.1)
                self._hub.set_analog(self._ac_fan_mode_join, 0)
            else:
                if not self._ac_power:
                    self._set_power_on()
                    await asyncio.sleep(0.5)
                if hvac_mode == HVACMode.COOL:
                    self._hub.set_analog(self._ac_mode_join, 1)
                if hvac_mode == HVACMode.HEAT:
                    self._hub.set_analog(self._ac_mode_join, 2)
                if hvac_mode == HVACMode.DRY:
                    self._hub.set_analog(self._ac_mode_join, 3)
                if hvac_mode == HVACMode.FAN_ONLY:
                    self._hub.set_analog(self._ac_mode_join, 4)
                if hvac_mode == HVACMode.HEAT_COOL:
                    self._hub.set_analog(self._ac_mode_join, 5)
            self.schedule_update_ha_state()

    async def async_set_fan_mode(self, fan_mode):
        if fan_mode != '':
            self._attr_fan_mode = fan_mode
            if fan_mode == FAN_HIGH:
                self._hub.set_analog(self._ac_fan_mode_join, 1)
            if fan_mode == FAN_MEDIUM:
                self._hub.set_analog(self._ac_fan_mode_join, 2)
            if fan_mode == FAN_LOW:
                self._hub.set_analog(self._ac_fan_mode_join, 3)
            if fan_mode == FAN_AUTO:
                self._hub.set_analog(self._ac_fan_mode_join, 4)
            if fan_mode == FAN_OFF:
                self._hub.set_analog(self._ac_fan_mode_join, 0)
            self.schedule_update_ha_state()

    def _process_mode_fb_callback(self, sigtype, join, value):
        _LOGGER.debug(f'receive mode fb:{value}')
        self._attr_hvac_mode = CONF_CURRENT_AC_MODE_MAP.get(value)
        if self._attr_hvac_mode != HVACMode.OFF:
            self._ac_power = True
        else:
            self._ac_power = False
        self.schedule_update_ha_state()

    def _process_fan_mode_fb_callback(self, sigtype, join, value):
        _LOGGER.debug(f'receive fan fb:{value}')
        self._attr_fan_mode = CONF_CURRENT_FAN_MODE_MAP.get(value)
        self.schedule_update_ha_state()

    def _process_humidity_fb_callback(self, sigtype, join, value):
        _LOGGER.debug(f'humidity change:{value}')
        self._attr_current_humidity = int(value)
        self.schedule_update_ha_state()


class FHPanel(Thermostat):
    def __init__(self, hub: XPanelClient, config, unit, device_type):
        super().__init__(hub, config, unit, device_type)
        self._fh_power_on_join = config.get(CONF_WH_POWER_ON_JOIN)
        self._fh_power_off_join = config.get(CONF_WH_POWER_OFF_JOIN)
        self._fh_power_on_fb_join = config.get(CONF_WH_POWER_ON_FB_JOIN)
        self._fh_state = self._hub.get_digital(self._fh_power_on_fb_join)

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        await self._hub.register_callback(
            "d", self._fh_power_on_fb_join, self.process_power_fb_callback)

    async def async_will_remove_from_hass(self):
        await super().async_will_remove_from_hass()
        await self._hub.remove_callback("a", self._ac_mode_fb_join)

    @property
    def hvac_mode(self):
        if self._fh_state:
            return HVACMode.HEAT
        else:
            return HVACMode.OFF

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.HEAT:
            self._hub.pulse(self._fh_power_on_join)
        elif hvac_mode == HVACMode.OFF:
            self._hub.pulse(self._fh_power_off_join)

    def process_power_fb_callback(self, sigtype, join, value):
        self._fh_state = value
        self.async_schedule_update_ha_state()
