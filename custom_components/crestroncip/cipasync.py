# Standard Imports
import binascii
import logging
import queue
import asyncio
from homeassistant.core import HomeAssistant
from asyncio import Lock, Transport, Protocol, Future, AbstractEventLoop, Task
_logger = logging.getLogger(__name__)


class TcpProtocol(Protocol):

    def __init__(self, conn_on_callback, conn_off_callback, receive_callback):
        self.receive_callback = receive_callback
        self.connect_on_callback = conn_on_callback
        self.connect_off_callback = conn_off_callback

    def connection_made(self, transport: Transport):
        self.tr = transport
        if self.connect_on_callback is not None:
            self.connect_on_callback()

    def data_received(self, data):
        if self.receive_callback is not None:
            self.receive_callback(data)

    def connection_lost(self, exc: Exception):
        _logger.error(f"conn lost :{exc}")
        if self.connect_off_callback is not None:
            self.connect_off_callback()

    def eof_received(self):
        if self.connect_off_callback is not None:
            self.connect_off_callback()


class XPanelClient:
    """Facilitate communications with a Crestron control processor via CIP."""

    _cip_packet = {
        "d": b"\x05\x00\x06\x00\x00\x03\x00",  # standard digital join
        "db": b"\x05\x00\x06\x00\x00\x03\x27",  # button-style digital join
        "dp": b"\x05\x00\x06\x00\x00\x03\x27",  # pulse-style digital join
        "a": b"\x05\x00\x08\x00\x00\x05\x14",  # analog join
        "s": b"\x12\x00\x00\x00\x00\x00\x00\x34",  # serial join
    }

    def __init__(self, hass: HomeAssistant, host: str, ip_id: int, room_id: str = "", port: int = 41794, timeout: int = 2):
        """Set up CIP client instance."""
        self.hass = hass
        self.host = host
        self.ip_id = ip_id.to_bytes(length=1, byteorder="big")
        self.port = port
        self.room_id = str.upper(room_id)
        self._timeout = timeout
        self._stop_connection = False
        self._restart_connection = False
        self.connected = False
        self._send_lock = Lock()
        self._restart_lock = Lock()
        self.buttons_pressed = {}
        self._buttons_lock = Lock()
        self._tx_queue = queue.Queue()
        self._event_queue = queue.Queue()
        self._loop: AbstractEventLoop
        self._tcp_cli: TcpProtocol
        self._transport: Transport
        self._check_conn_task: Task
        self._send_msg_task: Task
        self._join_lock = Lock()
        self._joins_dic = {
            "in": {"d": {}, "a": {}, "s": {}},
            "out": {"d": {}, "a": {}, "s": {}},
        }
        self._callbacks = set()
        self._sync_all_joins_callback = None
        self._available = False
        self.online_callback_func = None
        self.receive_callback_func = None

    async def stop(self):
        """Stop the CIP client instance."""
        if self._transport is not None:
            async with self._send_lock:
                self._stop_connection = True
                _logger.info('stop cip client')
                await asyncio.sleep(1)
                self._send_msg_task.cancel()
                self._check_conn_task.cancel()
                self._transport.close()

    async def start(self):
        # asyncio.create_task(self._create_conn())
        await self._create_conn()
        self._check_conn_task = self.hass.async_create_background_task(
            self._check_conn_state(), 'check_conn')
        self._send_msg_task = self.hass.async_create_background_task(
            self._send_queue(), 'send_msg')
        self.send_event_task = self.hass.async_create_background_task(
            self._start_event(), 'send_event')

    async def _create_conn(self):
        """Start the YeeLight client instance."""
        self._loop = self.hass.loop
        if not self.connected:
            self._transport, self._tcp_cli = await self._loop.create_connection(
                lambda: TcpProtocol(self._conn_online, self._conn_offline,
                                    self._handle_incoming_message),
                self.host, self.port)

    def _conn_online(self):
        self.connected = True
        # self._update_request()
        self._restart_connection = False
        if self.online_callback_func is not None:
            self.online_callback_func(True)

    def _conn_offline(self):
        self.connected = False
        if self._stop_connection is False:
            self._restart_connection = True
        if self.online_callback_func is not None:
            self.online_callback_func(False)

    async def _check_conn_state(self):
        while (not self._stop_connection):
            try:
                if (self._restart_connection is True):
                    _logger.error("conn err,restart reconnect")
                    if self._transport is not None:
                        try:
                            self._transport.close()
                            _logger.warning('close xpanel client')
                        except Exception as ex:
                            _logger.error(f'close xpanel client err:{ex}')
                    # self._transport = None
                    self._conn_offline()
                    await asyncio.sleep(10)
                await self._create_conn()
            except Exception as e:
                _logger.error(f"conn state check err:{e}")
            finally:
                await asyncio.sleep(10)

    def set(self, sigtype, join, value):
        """Set an outgoing join."""
        if sigtype == "d":
            if (value != 0) and (value != 1):
                _logger.error(
                    f"set(): '{value}' is not a valid digital signal state")
                return
        elif sigtype == "a":
            if (type(value) is not int) or (value > 65535):
                _logger.error(
                    f"set(): '{value}' is not a valid analog signal value")
                return
        elif sigtype == "s":
            value = str(value)
        else:
            _logger.debug(f"set(): '{sigtype}' is not a valid signal type")
            return

        self._event_queue.put(("out", sigtype, join, value))

    def press(self, join):
        """Set a digital output join to the active state using CIP button logic."""
        self._event_queue.put(("out", "db", join, 1))

    def release(self, join):
        """Set a digital output join to the inactive state using CIP button logic."""
        self._event_queue.put(("out", "db", join, 0))

    def pulse(self, join):
        """Generate an active-inactive pulse on the specified digital output join."""
        self._event_queue.put(("out", "dp", join, 1))
        self._event_queue.put(("out", "dp", join, 0))

    def get(self, sigtype, join, direction="in"):
        """Get the current value of a join."""
        if (direction != "in") and (direction != "out"):
            raise ValueError(
                f"get(): '{direction}' is not a valid signal direction")
        if (sigtype != "d") and (sigtype != "a") and (sigtype != "s"):
            raise ValueError(f"get(): '{sigtype}' is not a valid signal type")

        # with self.join_lock:
        try:
            value = self._joins_dic[direction][sigtype][join][0]
        except KeyError:
            if sigtype == "s":
                value = ""
            else:
                value = 0
        return value

    def update_request(self):
        """Send an update request to the control processor."""
        if self.connected is True:
            self._tx_queue.put(b"\x05\x00\x05\x00\x00\x02\x03\x00")
        else:
            _logger.debug(
                "update_request(): not currently connected")

    async def subscribe(self, sigtype, join, callback, direction="in"):
        """Subscribe to join change events by specifying callback functions."""
        if (direction != "in") and (direction != "out"):
            raise ValueError(
                f"subscribe(): '{direction}' is not a valid signal direction"
            )
        if (sigtype != "d") and (sigtype != "a") and (sigtype != "s"):
            raise ValueError(
                f"subscribe(): '{sigtype}' is not a valid signal type")

        async with self._join_lock:
            if join not in self._joins_dic[direction][sigtype]:
                if sigtype == "s":
                    value = ""
                else:
                    value = 0
                self._joins_dic[direction][sigtype][join] = [
                    value,
                ]
            self._joins_dic[direction][sigtype][join].append(callback)

    async def unsubscribe(self, sigtype, join, direction="in"):
        async with self._join_lock:
            if join not in self._joins_dic[direction][sigtype]:
                if sigtype == "s":
                    value = ""
                else:
                    value = 0
                self._joins_dic[direction][sigtype][join] = [
                    value,
                ]

    async def _send_queue(self):
        """Start the CIP outgoing packet processing thread."""
        _logger.debug("started")
        time_asleep_heartbeat = 0
        time_asleep_buttons = 0
        while (not self._stop_connection):
            while not self._tx_queue.empty():
                tx = self._tx_queue.get()
                if self._restart_connection is False:
                    _logger.debug(
                        f"TX: <{str(binascii.hexlify(tx), 'ascii')}>")
                    try:
                        self._transport.write(tx)
                    except Exception as e:
                        _logger.debug(f"send err:{e}")
                        async with self._restart_lock:
                            self._restart_connection = True
                    time_asleep_heartbeat = 0
                await asyncio.sleep(0.001)
            if self.connected is True and self._restart_connection is False:
                time_asleep_heartbeat += 0.01
                if time_asleep_heartbeat >= 15:
                    self._tx_queue.put(b"\x0D\x00\x02\x00\x00")
                    time_asleep_heartbeat = 0
                time_asleep_buttons += 0.01
                if time_asleep_buttons >= 0.50 and len(self.buttons_pressed):
                    async with self._buttons_lock:
                        for join in self.buttons_pressed:
                            try:
                                if self._joins_dic["out"]["d"][join][0] == 1:
                                    self._tx_queue.put(
                                        self.buttons_pressed[join]
                                    )
                            except KeyError:
                                pass
                    time_asleep_buttons = 0
            await asyncio.sleep(0.001)
        _logger.debug("stopped")

    def _handle_incoming_message(self, rx: bytes):
        try:
            _logger.debug(f'RX: <{rx.hex()}>')
            position = 0
            length = len(rx)
            while position < length:
                if (length - position) < 4:
                    _logger.warning("Packet is too short")
                    break

                payload_length = (
                    rx[position + 1] << 8) + rx[position + 2]
                packet_length = payload_length + 3

                if (length - position) < packet_length:
                    _logger.warning("Packet length mismatch")
                    break

                packet_type = rx[position]
                payload = rx[position +
                             3: position + 3 + payload_length]

                self._processPayload(packet_type, payload)
                position += packet_length
            # else:
            #     time.sleep(0.1)
        except Exception as e:
            _logger.error(f'handle in come msg err:{e}')
            if e.args[0] != "timed out":
                # with self.restart_lock:
                self._restart_connection = True

    async def _start_event(self):
        """Start the join event processing thread."""
        _logger.debug("send event started")
        while not self._stop_connection:
            if not self._event_queue.empty():
                direction, sigtype, join, value = self._event_queue.get()
                async with self._join_lock:
                    try:
                        self._joins_dic[direction][sigtype[0]][join][0] = value
                        # 处理join注册的所有回调
                        for callback in self._joins_dic[direction][sigtype[0]][join][1:]:
                            callback(sigtype[0], join, value)
                    except KeyError:
                        self._joins_dic[direction][sigtype[0]][join] = [
                            value,
                        ]
                _logger.debug(f"  : {sigtype} {direction} {join} = {value}")

                if direction == "out":
                    tx = bytearray(self._cip_packet[sigtype])
                    if join is not None:
                        cip_join:int = join - 1
                        if sigtype[0] == "d":
                            packed_join = (cip_join // 256) + \
                                ((cip_join % 256) * 256)
                            if value == 0:
                                packed_join |= 0x80
                            tx += packed_join.to_bytes(2, "big")
                            if sigtype == "db":
                                async with self._buttons_lock:
                                    if value == 1:
                                        self.buttons_pressed[join] = tx
                                    elif join in self.buttons_pressed:
                                        self.buttons_pressed.pop(join)
                        elif sigtype == "a":
                            tx += cip_join.to_bytes(2, "big")
                            tx += value.to_bytes(2, "big")
                        elif sigtype == "s":
                            tx[2] = 8 + len(value)
                            tx[6] = 4 + len(value)
                            tx += cip_join.to_bytes(2, "big")
                            tx += b"\x03"
                            tx += bytearray(value, "ascii")
                        if (
                            self.connected is True
                            and self._restart_connection is False
                        ):
                            self._tx_queue.put(tx)
            await asyncio.sleep(0.001)
        _logger.debug("send event stopped")

    def _processPayload(self, ciptype:int, payload:bytes):
        """Process CIP packets."""
        _logger.debug(
            f'> Type 0x{ciptype:02x} <{payload.hex()}>'
        )
        length = len(payload)
        restartRequired = False

        if ciptype == 0x0D or ciptype == 0x0E:
            # heartbeat
            _logger.debug("  Heartbeat")
        elif ciptype == 0x05:
            # data
            datatype = payload[3]

            if datatype == 0x00:
                # digital join
                join = (((payload[5] & 0x7F) << 8) | payload[4]) + 1
                state = ((payload[5] & 0x80) >> 7) ^ 0x01
                self._event_queue.put(("in", "d", join, state))
                _logger.debug(f"  Incoming Digital Join {join:04} = {state}")
                self.hass.bus.fire(
                    'xpanel_receive', {'type': 'd', 'join': join, 'value': state})
            elif datatype == 0x14:
                join = ((payload[4] << 8) | payload[5]) + 1
                value = (payload[6] << 8) + payload[7]
                self._event_queue.put(("in", "a", join, value))
                _logger.debug(f"  Incoming Analog Join {join:04} = {value}")
                self.hass.bus.fire(
                    'xpanel_receive', {'type': 'a', 'join': join, 'value': value})
            elif datatype == 0x03:
                # update request
                update_request_type = payload[4]
                if update_request_type == 0x00:
                    # standard update request
                    _logger.debug("  Standard update request")
                elif update_request_type == 0x16:
                    # penultimate update request
                    _logger.debug("  Mysterious penultimate update-response")
                elif update_request_type == 0x1C:
                    # end-of-query
                    _logger.debug("  End-of-query")
                    self._tx_queue.put(b"\x05\x00\x05\x00\x00\x02\x03\x1d")
                    self._tx_queue.put(b"\x0D\x00\x02\x00\x00")
                    self.connected = True
                    # with self.join_lock:
                    for sigtype, joins in self._joins_dic["out"].items():
                        for j in joins:
                            self.set(sigtype, j, joins[j][0])
                elif update_request_type == 0x1D:
                    # end-of-query acknowledgement
                    _logger.debug("  End-of-query acknowledgement")
                else:
                    # unexpected update request packet
                    _logger.debug(
                        "! We don't know what to do with this update request")
            elif datatype == 0x08:
                # date/time
                cip_date = str(binascii.hexlify(payload[4:]), "ascii")
                _logger.debug(
                    f"  Received date/time from control processor <"
                    f"{cip_date[2:4]}:{cip_date[4:6]}:"
                    f"{cip_date[6:8]} {cip_date[8:10]}/"
                    f"{cip_date[10:12]}/20{cip_date[12:]}>"
                )
            else:
                # unexpected data packet
                _logger.debug("! We don't know what to do with this data")
        elif ciptype == 0x12:
            join = ((payload[5] << 8) | payload[6]) + 1
            hex_str = str(binascii.hexlify(payload[8:]), "ascii")
            self.hass.bus.async_fire(
                'xpanel_receive', {'type': 's', 'join': join, 'value': hex_str})
            value = str(payload[8:], "ascii")
            self._event_queue.put(("in", "s", join, value))
            _logger.debug(f"  Incoming Serial Join {join:04} = {value}")
        elif ciptype == 0x0F:
            # registration request
            _logger.debug("  Client registration request")
            if self.room_id == "":
                tx = (
                    b"\x01\x00\x0b\x00\x00\x00\x00\x00"
                    + self.ip_id
                    + b"\x40\xff\xff\xf1\x01"
                )
                self._tx_queue.put(tx)
            else:
                room_bytes = bytearray(f"{self.room_id}", "ascii")
                tx = (
                    b"\x26\x00\xd5\x00"
                    + self.ip_id
                    + b"\x40\xf1\x01\x00\x00\x00\x01"
                    + b"\xff\xff\xff\xff\xff\xff"  # mac add
                    + bytearray("Crestron", "ascii")
                    + b"\x00"*42
                    + bytearray("XPanel", "ascii")
                    + b"\x00"*44
                    + room_bytes
                    + b"\x00"*(32-len(room_bytes))
                    + bytearray("XPanel -FF-FF-FF-FF-FF-FF", "ascii")
                    + b"\x00"*41
                )
                self._tx_queue.put(tx)
        elif ciptype == 0x02:
            # registration result
            ip_id_string = str(binascii.hexlify(self.ip_id), "ascii")

            if length == 3 and payload == b"\xff\xff\x02":
                _logger.error(
                    f"! The specified IPID (0x{ip_id_string}) does not exist")
                restartRequired = True
            elif length == 4 and payload == b"\x00\x00\x00\x1f":
                _logger.debug(f"  Registered IPID 0x{ip_id_string}")
                # 0500050000020300 send query
                self._tx_queue.put(b"\x05\x00\x05\x00\x00\x02\x03\x00")
            else:
                _logger.error(f"! Error registering IPID 0x{ip_id_string}")
                restartRequired = True
        elif ciptype == 0x03:
            # control system disconnect
            _logger.debug("! Control system disconnect")
            restartRequired = True
        elif ciptype == 0x27:
            # registration result
            ip_id_string = str(binascii.hexlify(self.ip_id), "ascii")
            # _logger.debug(f"lenth:{len(payload)}__{payload[0:4]}")
            if length == 38 and payload[0:3] == b"\xff\xff\x02":
                _logger.error(
                    f"! The specified IPID (0x{ip_id_string}) does not exist")
                restartRequired = True
            elif length == 38 and payload[0:4] == b"\x00\x00\x00\x1f":
                _logger.debug(f"  Registered IPID 0x{ip_id_string}")
                # 0500050000020300 send query
                self._tx_queue.put(b"\x05\x00\x05\x00\x00\x02\x03\x00")
            else:
                _logger.error(f"! Error registering IPID 0x{ip_id_string}")
                restartRequired = True
        else:
            # unexpected packet
            # 27 00 26 00 01 00 1F 00 00 00 08 56 43 2D 34 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00

            _logger.debug("! We don't know what to do with this packet")

        if restartRequired:
            # with self.restart_lock:
            self._restart_connection = True

    def register_sync_all_joins_callback(self, callback) -> None:
        """ Allow callback to be registred for when control system requests an update to all joins """
        _logger.debug("Sync-all-joins callback registered")
        self._sync_all_joins_callback = callback

    async def register_callback(self, sigtype, join, callback):
        """ Allow callbacks to be registered for when dict entries change """
        await self.subscribe(sigtype, join, callback)

    async def remove_callback(self, sigtype, join):
        """ Allow callbacks to be de-registered """
        await self.unsubscribe(sigtype, join)

    def is_available(self):
        return self._available

    def get_analog(self, join):
        """ Return analog value for join"""
        return int(self.get("a", join))

    def get_digital(self, join):
        """ Return digital value for join"""
        return bool(self.get("d", join))

    def get_serial(self, join):
        """ Return serial value for join"""
        return self.get("s", join)

    def set_analog(self, join, value):
        self.set("a", join, int(value))

    def set_digital(self, join, value):
        self.set("d", join, value)

    def set_serial(self, join, string):
        self.set("s", join, string)
