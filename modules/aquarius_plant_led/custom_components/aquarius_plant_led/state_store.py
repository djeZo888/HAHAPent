"""Versioned private HA memory; observations never trigger lamp restoration."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .client import DeviceState
from .const import DOMAIN
from .protocol import MODE_AUTOMATIC, MODE_MANUAL, MODE_SHUTDOWN

STORE_VERSION = 1
NO_MANUAL_STATE = "No saved manual state: On resumes the lamp's stored schedule"


class PowerMemoryError(Exception):
    """Power memory could not be safely persisted or interpreted."""


class _PowerStore(Store):
    """No implicit upgrade or downgrade of a safety-related saved intent."""

    async def _async_migrate_func(self, old_major_version, old_minor_version, old_data):
        raise PowerMemoryError("power memory storage version is unsupported")


def _profile(state: DeviceState) -> dict:
    return {
        "controller": list(state.system.controller_bytes),
        "version": list(state.system.version_bytes),
        "count": state.system.channel_count_raw,
    }


def _valid_profile(value) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"controller", "version", "count"}
        and type(value["count"]) is int
        and value["count"] == 6
        and all(
            isinstance(value[key], list)
            and len(value[key]) == 2
            and all(type(item) is int and 0 <= item <= 255 for item in value[key])
            for key in ("controller", "version")
        )
    )


def _valid_channels(value, *, nonzero=False) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 6
        and all(type(item) is int and 0 <= item <= 100 for item in value)
        and (not nonzero or any(value))
    )


def _empty() -> dict:
    return {"schema_version": 1, "revision": "", "last_manual": None, "off_origin": None}


def _existing_record(path: Path) -> bool:
    """Reject corrupt JSON before HA's ordinary Store recovery can rename it."""
    try:
        with path.open(encoding="utf-8") as stream:
            envelope = json.load(stream)
    except FileNotFoundError:
        return False
    if (
        not isinstance(envelope, dict)
        or not {"version", "data"} <= envelope.keys()
        or type(envelope["version"]) is not int
        or type(envelope.get("minor_version", 1)) is not int
    ):
        raise PowerMemoryError("power memory envelope is unreadable")
    return True


def _validate(data) -> bool:
    if (
        not isinstance(data, dict)
        or set(data) != {"schema_version", "revision", "last_manual", "off_origin"}
        or type(data["schema_version"]) is not int
        or data["schema_version"] != 1
        or not isinstance(data["revision"], str)
        or len(data["revision"]) != 32
    ):
        return False
    manual = data["last_manual"]
    if manual is not None and not (
        isinstance(manual, dict)
        and set(manual) == {"profile", "channels"}
        and _valid_profile(manual["profile"])
        and _valid_channels(manual["channels"], nonzero=True)
    ):
        return False
    origin = data["off_origin"]
    return origin is None or (
        isinstance(origin, dict)
        and set(origin) == {"profile", "mode", "manual_channels", "confirmed", "off_channels"}
        and _valid_profile(origin["profile"])
        and type(origin["mode"]) is int
        and origin["mode"] in (MODE_AUTOMATIC, MODE_MANUAL)
        and type(origin["confirmed"]) is bool
        and (
            origin["manual_channels"] is None
            or _valid_channels(origin["manual_channels"], nonzero=True)
        )
        and (
            _valid_channels(origin["off_channels"])
            if origin["confirmed"]
            else origin["off_channels"] is None
        )
    )


class AquariusPowerMemory:
    """Bind saved intent and nonzero Manual output to this entry and raw profile."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.key = f"{DOMAIN}.{entry_id}.power"
        self._writer = self._store()
        self._record = _empty()
        self.error = False
        self._write_blocked = False

    def _store(self) -> Store:
        return _PowerStore(self.hass, STORE_VERSION, self.key, private=True, atomic_writes=True)

    async def async_load(self) -> None:
        try:
            reader = self._store()
            existed = await self.hass.async_add_executor_job(_existing_record, Path(reader.path))
            data = await reader.async_load()
            # An existing-but-unreadable record must not silently become a new
            # Off cycle. The preflight also preserves invalid JSON in place.
            if data is None and existed:
                raise PowerMemoryError("existing power memory is unreadable")
        except Exception:
            data = None
            self.error = True
            self._write_blocked = True
        if data is not None:
            if _validate(data):
                self._record = deepcopy(data)
            else:
                self.error = True
                self._write_blocked = True

    async def _save(self, record: dict) -> None:
        if self._write_blocked:
            raise PowerMemoryError("incompatible power memory was preserved without changes")
        candidate = deepcopy(record)
        candidate["revision"] = uuid4().hex
        try:
            # HA Store.async_save logs and swallows some write failures. A new
            # revision and a fresh Store load verify this specific durable intent.
            # HA invalidates its shared preload cache before attempting a write;
            # this reader cannot see the writer's instance-local pending data.
            pending = asyncio.create_task(self._writer.async_save(candidate))
            cancelled = False
            # A filesystem executor write cannot be unsent. Settle it before
            # releasing the command lock, so an older write cannot later replace
            # a newer Off intent. Cancellation never proceeds to a lamp command.
            while not pending.done():
                try:
                    await asyncio.shield(pending)
                except asyncio.CancelledError:
                    cancelled = True
            pending.result()
            if cancelled:
                self.error = True
                raise asyncio.CancelledError
            if await self._store().async_load() != candidate:
                raise PowerMemoryError("power memory write could not be verified")
        except asyncio.CancelledError:
            self.error = True
            raise
        except Exception:
            self.error = True
            raise PowerMemoryError("power memory write could not be verified") from None
        self._record = candidate
        self.error = False

    def _observed_record(self, state: DeviceState) -> dict:
        record = deepcopy(self._record)
        if (
            state.system.write_supported
            and state.system.mode_raw == MODE_MANUAL
            and any(state.channels)
        ):
            record["last_manual"] = {"profile": _profile(state), "channels": list(state.channels)}
        if state.system.mode_raw in (MODE_AUTOMATIC, MODE_MANUAL):
            # A subsequent external On invalidates an older remembered Off cycle.
            record["off_origin"] = None
        return record

    async def async_observe(self, state: DeviceState) -> None:
        record = self._observed_record(state)
        if record != self._record:
            await self._save(record)

    async def async_prepare_off(self, state: DeviceState) -> None:
        if state.system.mode_raw not in (MODE_AUTOMATIC, MODE_MANUAL):
            raise PowerMemoryError("Off origin must be Manual or Automatic")
        record = self._observed_record(state)
        manual = record["last_manual"]
        record["off_origin"] = {
            "profile": _profile(state),
            "mode": state.system.mode_raw,
            "manual_channels": (
                manual["channels"]
                if manual is not None and manual["profile"] == _profile(state)
                else None
            ),
            "confirmed": False,
            "off_channels": None,
        }
        await self._save(record)

    async def async_confirm_off(self, state: DeviceState) -> None:
        record = deepcopy(self._record)
        origin = record["off_origin"]
        if (
            origin is None
            or origin["profile"] != _profile(state)
            or state.system.mode_raw != MODE_SHUTDOWN
        ):
            raise PowerMemoryError("Off confirmation does not match the saved intent")
        origin["confirmed"] = True
        origin["off_channels"] = list(state.channels)
        await self._save(record)

    def manual_restore(self, state: DeviceState) -> tuple[tuple[int, ...] | None, str]:
        origin = self._record["off_origin"]
        if (
            self.error
            or origin is None
            or not origin["confirmed"]
            or origin["profile"] != _profile(state)
            or origin["off_channels"] != list(state.channels)
        ):
            return None, NO_MANUAL_STATE
        if origin["mode"] == MODE_AUTOMATIC:
            return None, "On resumes the lamp's stored schedule"
        if origin["manual_channels"] is None:
            return None, NO_MANUAL_STATE
        return tuple(origin["manual_channels"]), "On restores the saved nonzero Manual mix"

    async def async_remove(self) -> None:
        await self._store().async_remove()
