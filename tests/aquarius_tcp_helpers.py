"""Synthetic loopback device; no real lamp targets or captured data."""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
from pathlib import Path

PACKAGE = "_hahapent_aquarius_protocol_tests"
ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "modules/aquarius_plant_led/custom_components/aquarius_plant_led"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(COMPONENT)]
    sys.modules[PACKAGE] = package
protocol = importlib.import_module(PACKAGE + ".protocol")
client = importlib.import_module(PACKAGE + ".client")

SYNTHETIC_PROFILES = frozenset({((0x12, 0x3C), (2, 5), 6), ((0x14, 0x32), (2, 5), 6)})


def system_reply(mode=1, controller=(0x12, 0x3C), version=(2, 5), count=6):
    frame = bytearray(20)
    frame[0:3] = b"\xf1\xe1\xfc"
    frame[4] = mode
    frame[7:9] = bytes(version)
    frame[9:11] = bytes(controller)
    frame[11] = count
    frame[-1] = 0xF3
    return bytes(frame)


def channels_reply(values=(10, 20, 30, 40, 50, 60), operation=0xFC):
    return b"\xf1\xe2" + bytes((operation,)) + bytes(values) + b"\0" * 10 + b"\xf3"


def extended_reply(payload):
    return b"\x01\xfe\x68" + bytes((len(payload),)) + payload + b"\x67\xfd\x02"


class SyntheticLamp:
    """Minimal simulated six-channel state with optional faults and interference."""

    def __init__(self):
        self.mode = 1
        self.channels = (10, 20, 30, 40, 50, 60)
        self.controller = (0x12, 0x3C)
        self.version = (2, 5)
        self.count = 6
        self.channel_operation = 0xFC
        self.fragment = False
        self.prelude = b""
        self.ignore_writes = False
        self.echo_writes = False
        self.hook = None
        self.response_override = None
        self.observed = []
        self.connections = 0
        self.tasks = set()
        self.writers = set()
        self.server = None

    async def start(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def close(self):
        self.server.close()
        await self.server.wait_closed()
        for writer in tuple(self.writers):
            writer.close()
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    def wire_channels(self):
        values = list(self.channels)
        if self.controller == (0x14, 0x32):
            values[2], values[3] = values[3], values[2]
        return tuple(values)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        self.writers.add(writer)
        self.connections += 1
        connection = self.connections
        try:
            while True:
                frame = await reader.readexactly(20)
                self.observed.append((connection, frame, asyncio.get_running_loop().time()))
                if self.hook:
                    await self.hook(connection, frame)
                response = None
                if frame == protocol.SYSTEM_QUERY:
                    response = system_reply(self.mode, self.controller, self.version, self.count)
                elif frame == protocol.CHANNEL_QUERY:
                    response = channels_reply(self.wire_channels(), self.channel_operation)
                elif frame[1:3] == b"\xe2\xfa":
                    if not self.ignore_writes:
                        values = list(frame[3:9])
                        if self.controller == (0x14, 0x32):
                            values[2], values[3] = values[3], values[2]
                        self.channels = tuple(values)
                    response = frame if self.echo_writes else b"\xf5"
                elif frame[1:4] == b"\xe1\xfa\xdb":
                    if not self.ignore_writes:
                        self.mode = frame[4]
                    response = b"\xf5"
                else:
                    raise AssertionError("unexpected synthetic request")
                if self.response_override is not None:
                    response = self.response_override(frame, response)
                if response is None:
                    continue
                data = self.prelude + response
                if self.fragment:
                    for offset in range(0, len(data), 3):
                        writer.write(data[offset : offset + 3])
                        await writer.drain()
                        await asyncio.sleep(0)
                else:
                    writer.write(data)
                    await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            self.writers.discard(writer)
            self.tasks.discard(task)

    @property
    def frames(self):
        return [frame for _, frame, _ in self.observed]

    @property
    def writes(self):
        return [frame for frame in self.frames if frame[2] == 0xFA]
