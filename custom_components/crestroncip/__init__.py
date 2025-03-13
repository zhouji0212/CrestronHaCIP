"""The Crestron Integration Component"""

from .const import (CONF_IP, CONF_IP_ID, CONF_ROOM_ID, CONF_PORT,
                    HUB, DOMAIN, CONF_JOIN, CONF_SCRIPT)
import asyncio
import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import load_platform
from homeassistant.helpers.event import TrackTemplate, async_track_template_result
from homeassistant.helpers.template import Template
from homeassistant.helpers.script import Script
from homeassistant.core import callback, Context
from homeassistant.const import (
    Platform,
    EVENT_HOMEASSISTANT_STOP,
    CONF_VALUE_TEMPLATE,
    CONF_ATTRIBUTE,
    CONF_ENTITY_ID,
    STATE_ON,
    STATE_OFF,
    CONF_SERVICE,
    CONF_SERVICE_DATA,
)

from .cipasync import XPanelClient

_LOGGER = logging.getLogger(__name__)

TO_JOINS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_JOIN): cv.string,
        vol.Optional(CONF_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_ATTRIBUTE): cv.string,
        vol.Optional(CONF_VALUE_TEMPLATE): cv.template
    }
)

FROM_JOINS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_JOIN): cv.string,
        vol.Required(CONF_SCRIPT): cv.SCRIPT_SCHEMA
    }
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_IP): cv.string,
                vol.Required(CONF_PORT): cv.port,
                vol.Required(CONF_IP_ID): cv.port,
                vol.Optional(CONF_ROOM_ID, default=""): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.LIGHT,
    Platform.COVER,
]


async def async_setup(hass: HomeAssistant, config:dict):
    """Set up a the crestron component."""
    load_state = False
    if config.get(DOMAIN) is not None:
        hass.data[DOMAIN] = {}
        cip_config = config.get(DOMAIN)
        _port = cip_config.get(CONF_PORT)
        _ip = cip_config.get(CONF_IP)
        _ip_id = cip_config.get(CONF_IP_ID)
        _room_id = cip_config.get(CONF_ROOM_ID)
        xpanel_client = XPanelClient(
            hass, _ip, _ip_id, room_id=_room_id, port=_port)
        hass.data[DOMAIN][HUB] = xpanel_client
        await xpanel_client.start()
        load_state = True
        for platform in PLATFORMS:
            load_platform(hass, platform, DOMAIN, None, config)
    return load_state