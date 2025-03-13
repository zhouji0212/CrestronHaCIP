"""The Crestron Integration Component"""

from .const import (CONF_IP, CONF_IPID, CONF_ROOMID, CONF_PORT,
                    HUB, DOMAIN, CONF_JOIN, CONF_SCRIPT, CONF_TO_HUB, CONF_FROM_HUB)
import asyncio
import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.event import TrackTemplate, async_track_template_result
from homeassistant.helpers.template import Template
from homeassistant.helpers.script import Script
from homeassistant.core import callback, Context
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    CONF_VALUE_TEMPLATE,
    CONF_ATTRIBUTE,
    CONF_ENTITY_ID,
    STATE_ON,
    STATE_OFF,
    CONF_SERVICE,
    CONF_SERVICE_DATA,
)

from.crestroncipsync import *

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
                vol.Required(CONF_IPID): cv.port,
                vol.Optional(CONF_ROOMID, default=""): cv.string,
                vol.Optional(CONF_TO_HUB): vol.All(cv.ensure_list, [TO_JOINS_SCHEMA]),
                vol.Optional(CONF_FROM_HUB): vol.All(cv.ensure_list, [FROM_JOINS_SCHEMA])
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

PLATFORMS = [
    # "binary_sensor",
    # "sensor",
    "switch",
    "light",
    # "climate",
    "cover",
    # "media_player",
]


async def async_setup(hass: HomeAssistant, config):
    """Set up a the crestron component."""

    if config.get(DOMAIN) is not None:
        hass.data[DOMAIN] = {}
        hub = CrestronHub(hass, config[DOMAIN])
        hub.start()
        for platform in PLATFORMS:
            await async_load_platform(hass, platform, DOMAIN, {}, config)

    return True


class CrestronHub:
    ''' Wrapper for the CrestronXsig library '''

    def __init__(self, hass, config):
        self.hass = hass
        self.port = config.get(CONF_PORT)
        self.ip = config.get(CONF_IP)
        self.ip_id = config.get(CONF_IPID)
        self.room_id = config.get(CONF_ROOMID)
        self.cip_client = hass.data[DOMAIN][HUB] = CIPSocketClient(
            self.ip, self.ip_id, room_id=self.room_id)
        self.context = Context()
        self.to_hub = {}
        # self.hub.register_sync_all_joins_callback(self.sync_joins_to_hub)
        # 配置文件解析？
        # to_hub: to_joins
        if CONF_TO_HUB in config:
            pass
            # track_templates = []
            # for entity in config[CONF_TO_HUB]:
            #     template_string = None
            #     if CONF_VALUE_TEMPLATE in entity:
            #         template = entity[CONF_VALUE_TEMPLATE]
            #         self.to_hub[entity[CONF_JOIN]] = template
            #         track_templates.append(TrackTemplate(template, None))
            #     elif CONF_ATTRIBUTE in entity and CONF_ENTITY_ID in entity:
            #         template_string = (
            #             "{{state_attr('"
            #             + entity[CONF_ENTITY_ID]
            #             + "','"
            #             + entity[CONF_ATTRIBUTE]
            #             + "')}}"
            #         )
            #         template = Template(template_string, hass)
            #         self.to_hub[entity[CONF_JOIN]] = template
            #         track_templates.append(TrackTemplate(template, None))
            #     elif CONF_ENTITY_ID in entity:
            #         template_string = "{{states('" + \
            #             entity[CONF_ENTITY_ID] + "')}}"
            #         template = Template(template_string, hass)
            #         self.to_hub[entity[CONF_JOIN]] = template
            #         track_templates.append(TrackTemplate(template, None))
            # self.tracker = async_track_template_result(
            #     self.hass, track_templates, self.template_change_callback
            # )
        # 注册回调？
        if CONF_FROM_HUB in config:
            self.from_hub = config[CONF_FROM_HUB]
            # self.hub.register_callback(self.join_change_callback)

    def start(self):
        self.cip_client.start()

    def stop(self, event):
        """ remove callback(s) and template trackers """
        # self.hub.remove_callback(self.join_change_callback)
        # self.tracker.async_remove()
        self.cip_client.stop()

    async def join_change_callback(self, sigtype, join, value):
        """ Call service for tracked join change (from_hub)"""
        for join in self.from_hub:
            if cbtype == join[CONF_JOIN]:
                # For digital joins, ignore on>off transitions  (avoids double calls to service for momentary presses)
                if cbtype[:1] == "d" and value == "0":
                    pass
                else:
                    if CONF_SERVICE in join and CONF_SERVICE_DATA in join:
                        data = dict(join[CONF_SERVICE_DATA])
                        _LOGGER.debug(
                            f"join_change_callback calling service {join[CONF_SERVICE]} with data = {data} from join {cbtype} = {value}"
                        )
                        domain, service = join[CONF_SERVICE].split(".")
                        await self.hass.services.async_call(domain, service, data)
                    elif CONF_SCRIPT in join:
                        sequence = join[CONF_SCRIPT]
                        script = Script(
                            self.hass, sequence, "Crestron Join Change", DOMAIN
                        )
                        await script.async_run({"value": value}, self.context)
                        _LOGGER.debug(
                            f"join_change_callback calling script {join[CONF_SCRIPT]} from join {cbtype} = {value}"
                        )

    @callback
    def template_change_callback(self, event, updates):
        """ Set join from value_template (to_hub)"""
        # track_template_result = updates.pop()
        for track_template_result in updates:
            update_result = track_template_result.result
            update_template = track_template_result.template
            if update_result != "None":
                for join, template in self.to_hub.items():
                    if template == update_template:
                        _LOGGER.debug(
                            f"processing template_change_callback for join {join} with result {update_result}"
                        )
                        # Digital Join
                        if join[:1] == "d":
                            value = None
                            if update_result == STATE_ON or update_result == "True":
                                value = True
                            elif update_result == STATE_OFF or update_result == "False":
                                value = False
                            if value is not None:
                                _LOGGER.debug(
                                    f"template_change_callback setting digital join {int(join[1:])} to {value}"
                                )
                                self.cip_client.set(
                                    "d", (int(join[1:]), value))
                        # Analog Join
                        if join[:1] == "a":
                            _LOGGER.debug(
                                f"template_change_callback setting analog join {int(join[1:])} to {int(update_result)}"
                            )
                            self.cip_client.set("a",
                                                int(join[1:]), int(update_result))
                        # Serial Join
                        if join[:1] == "s":
                            _LOGGER.debug(
                                f"template_change_callback setting serial join {int(join[1:])} to {str(update_result)}"
                            )
                            self.cip_client.set("s",
                                                int(join[1:]), str(update_result))

    async def sync_joins_to_hub(self):
        _LOGGER.debug("Syncing joins to control system")
        for join, template in self.to_hub.items():
            result = template.async_render()
            # Digital Join
            if join[:1] == "d":
                value = None
                if result == STATE_ON or result == "True":
                    value = True
                elif result == STATE_OFF or result == "False":
                    value = False
                if value is not None:
                    _LOGGER.debug(
                        f"sync_joins_to_hub setting digital join {int(join[1:])} to {value}"
                    )
                    self.cip_client.set("d", (int(join[1:]), value))
            # Analog Join
            if join[:1] == "a":
                if result != "None":
                    _LOGGER.debug(
                        f"sync_joins_to_hub setting analog join {int(join[1:])} to {int(result)}"
                    )
                    self.cip_client.set("a", (int(join[1:]), int(result)))
            # Serial Join
            if join[:1] == "s":
                if result != "None":
                    _LOGGER.debug(
                        f"sync_joins_to_hub setting serial join {int(join[1:])} to {str(result)}"
                    )
                    self.cip_client.set("s", (int(join[1:]), str(result)))
