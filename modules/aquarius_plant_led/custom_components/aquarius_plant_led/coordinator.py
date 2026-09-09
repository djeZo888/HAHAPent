"""Conservative polling and explicit, serialized controller actions."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import AquariusClient, AquariusError, ConflictError, DeviceState
from .const import (
    CHANNEL_DEBOUNCE_SECONDS,
    DOMAIN,
    MAX_BACKOFF_SECONDS,
    MODE_OPTIONS,
    POLL_SECONDS,
)
from .protocol import (
    MODE_AUTOMATIC,
    MODE_MANUAL,
    MODE_SHUTDOWN,
    SUPPORTED_CONTROL_MODES,
    ProtocolError,
)
from .state_store import AquariusPowerMemory, PowerMemoryError

_LOGGER = logging.getLogger(__name__)
EXPLICIT_COMMAND_TIMEOUT = 3.0


class AquariusCoordinator(DataUpdateCoordinator[DeviceState]):
    """Verify explicit actions; lifecycle reads never restore or replay output."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: AquariusClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=POLL_SECONDS),
            always_update=False,
        )
        self.client = client
        self._io_lock = asyncio.Lock()
        self._failures = 0
        self._stopped = False
        self._quiescing = False
        self._resuming = False
        self._channel_generations = [0] * 6
        self._command_epoch = 0
        self._active_command: asyncio.Task | None = None
        self._active_read: asyncio.Task | None = None
        self.power_memory = AquariusPowerMemory(hass, entry.entry_id)

    async def async_load_power_memory(self) -> None:
        """Read HA memory without issuing any lamp command."""
        await self.power_memory.async_load()

    async def _remember_observation(self, state: DeviceState) -> None:
        try:
            await self.power_memory.async_observe(state)
        except PowerMemoryError:
            # Device readback is still truthful; unsafe persistence is enforced
            # before Off, and missing Manual memory falls back to the schedule.
            _LOGGER.warning("Aquarius power memory could not be saved")

    async def _publish_observation(self, state: DeviceState) -> None:
        """Publish device readback and its memory-dependent attributes together."""
        try:
            await self._remember_observation(state)
        finally:
            # Persistence failure does not erase confirmed physical readback.
            # The enclosing command window marks cancelled actions unavailable.
            self.async_set_updated_data(state)

    def _read_failed(self) -> None:
        # Recovery permits new user actions, never actions queued before a fault.
        self._command_epoch += 1
        self._failures += 1
        self.update_interval = timedelta(
            seconds=min(POLL_SECONDS * 2 ** min(self._failures, 4), MAX_BACKOFF_SECONDS)
        )

    def _read_succeeded(self) -> None:
        self._failures = 0
        self.update_interval = timedelta(seconds=POLL_SECONDS)

    async def _async_update_data(self) -> DeviceState:
        async with self._io_lock:
            if self._stopped or (self._quiescing and not self._resuming):
                raise UpdateFailed("Integration is stopping")
            self._active_read = asyncio.current_task()
            try:
                state = await self.client.refresh()
                self._read_succeeded()
                await self._remember_observation(state)
                return state
            except asyncio.CancelledError:
                self._read_failed()
                self.async_set_update_error(UpdateFailed("Controller read was cancelled"))
                raise
            except (AquariusError, ProtocolError, OSError, TimeoutError):
                self._read_failed()
                raise UpdateFailed("Unable to read the Aquarius controller") from None
            finally:
                self._active_read = None

    def _require_current_state(self) -> None:
        if self._stopped or self._quiescing or not self.last_update_success or self.data is None:
            raise HomeAssistantError("Wait for a successful controller read before changing output")

    def _require_write_supported(self) -> None:
        self._require_current_state()
        if not self.data.system.write_supported:
            raise ServiceValidationError(
                "This controller profile is read-only: bounded hardware write validation "
                "has not passed. Channel and mode changes are disabled for this profile."
            )
        if self.data.system.mode_raw not in SUPPORTED_CONTROL_MODES:
            raise ServiceValidationError(
                "The controller is in an unsupported operating mode. "
                "Only changes from Manual or Automatic have been validated."
            )

    def _require_current_request(self, epoch: int) -> None:
        self._require_write_supported()
        if epoch != self._command_epoch:
            raise HomeAssistantError(
                "Controller communication changed after this request. "
                "Review the current state and submit a new change."
            )

    def _require_power_supported(self) -> None:
        self._require_current_state()
        if not self.data.system.power_supported:
            raise ServiceValidationError(
                "Software On/Off has not been validated for this controller profile"
            )
        if self.data.system.mode_raw not in (MODE_AUTOMATIC, MODE_MANUAL, MODE_SHUTDOWN):
            raise ServiceValidationError("The controller is in an unsupported operating mode")

    def _require_power_request(self, epoch: int) -> None:
        self._require_power_supported()
        if epoch != self._command_epoch:
            raise HomeAssistantError("Controller communication changed; submit a new action")

    @asynccontextmanager
    async def _command_window(self, deadline: float):
        """Expire the entire admitted action, including debounce and lock waits.

        Cancellation propagates through the awaited client transaction and its
        socket cleanup before this scope returns. This is not an HTTP admission
        deadline or a guarantee that already transmitted bytes cannot arrive late.
        """
        task = asyncio.current_task()
        try:
            async with asyncio.timeout_at(deadline):
                yield
        except TimeoutError:
            self._read_failed()
            self.async_set_update_error(UpdateFailed("Controller action deadline expired"))
            raise HomeAssistantError(
                "The change expired before completion. No command was retried. "
                "Read and review the controller state before another change."
            ) from None
        except asyncio.CancelledError:
            self._read_failed()
            self.async_set_update_error(UpdateFailed("Controller command was cancelled"))
            raise
        finally:
            if self._active_command is task:
                self._active_command = None

    @staticmethod
    def _check_command_deadline(deadline: float) -> None:
        # A lock can become ready after a delayed event-loop turn. Do not enter
        # the client merely because its timeout callback has not run yet.
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError

    async def async_set_channel(self, index: int, value: int) -> None:
        """Debounce slider changes, then explicitly save manual output once."""
        deadline = asyncio.get_running_loop().time() + EXPLICIT_COMMAND_TIMEOUT
        if type(index) is not int or index not in range(6):
            raise ServiceValidationError("Channel must be A through F")
        if type(value) is not int or value not in range(101):
            raise ServiceValidationError("Channel level must be an integer from 0 to 100")
        self._require_write_supported()
        epoch = self._command_epoch
        self._channel_generations[index] += 1
        generation = self._channel_generations[index]
        async with self._command_window(deadline):
            await asyncio.sleep(CHANNEL_DEBOUNCE_SECONDS)
            async with self._io_lock:
                self._check_command_deadline(deadline)
                self._require_current_request(epoch)
                if generation != self._channel_generations[index]:
                    return
                self._active_command = asyncio.current_task()
                try:
                    state = await self.client.set_channel(index, value, expected_state=self.data)
                except (AquariusError, ProtocolError, OSError, TimeoutError):
                    self._read_failed()
                    error = UpdateFailed("Controller command could not be verified; read again")
                    self.async_set_update_error(error)
                    raise HomeAssistantError(
                        "The change was not confirmed. No command was retried. "
                        "Wait for a successful read before making another change."
                    ) from None
                self._read_succeeded()
                await self._publish_observation(state)

    async def async_set_mode(self, option: str) -> None:
        """Change mode only for an explicit select action, never during setup."""
        deadline = asyncio.get_running_loop().time() + EXPLICIT_COMMAND_TIMEOUT
        if option not in MODE_OPTIONS:
            raise ServiceValidationError("Unsupported operating mode")
        self._require_write_supported()
        epoch = self._command_epoch
        # An explicit mode choice supersedes slider changes still being debounced.
        self._channel_generations = [value + 1 for value in self._channel_generations]
        async with self._command_window(deadline):
            async with self._io_lock:
                self._check_command_deadline(deadline)
                self._require_current_request(epoch)
                self._active_command = asyncio.current_task()
                try:
                    state = await self.client.set_mode(
                        MODE_OPTIONS[option], expected_state=self.data
                    )
                except (AquariusError, ProtocolError, OSError, TimeoutError):
                    self._read_failed()
                    self.async_set_update_error(
                        UpdateFailed("Controller mode change was not verified")
                    )
                    raise HomeAssistantError(
                        "The mode change was not confirmed. No command was retried. "
                        "Wait for a successful read before making another change."
                    ) from None
                self._read_succeeded()
                await self._publish_observation(state)

    async def async_turn_off(self) -> None:
        """Persist fresh origin before a single explicit software Off command."""
        deadline = asyncio.get_running_loop().time() + EXPLICIT_COMMAND_TIMEOUT
        self._require_power_supported()
        epoch = self._command_epoch
        self._channel_generations = [value + 1 for value in self._channel_generations]
        async with self._command_window(deadline):
            async with self._io_lock:
                self._check_command_deadline(deadline)
                self._require_power_request(epoch)
                self._active_command = asyncio.current_task()
                try:
                    observed = self.data
                    before = await self.client.refresh()
                    if before.system != observed.system or (
                        before.system.mode_raw != MODE_AUTOMATIC
                        and before.channels != observed.channels
                    ):
                        raise ConflictError("controller state changed before Off")
                    self.async_set_updated_data(before)
                    self._require_power_request(epoch)
                    if before.system.mode_raw == MODE_SHUTDOWN:
                        return
                    await self.power_memory.async_prepare_off(before)
                    self._check_command_deadline(deadline)
                    self._require_power_request(epoch)
                    state = await self.client.turn_off(expected_state=before)
                except PowerMemoryError:
                    raise HomeAssistantError(
                        "Off was not sent because its return state could not be saved"
                    ) from None
                except (AquariusError, ProtocolError, OSError, TimeoutError):
                    self._read_failed()
                    self.async_set_update_error(UpdateFailed("Software Off was not confirmed"))
                    raise HomeAssistantError(
                        "Off was not confirmed. No command was retried"
                    ) from None
                self._read_succeeded()
                try:
                    await self.power_memory.async_confirm_off(state)
                except PowerMemoryError:
                    raise HomeAssistantError(
                        "Off was confirmed but its return state could not be saved. "
                        "On will resume the lamp's stored schedule."
                    ) from None
                finally:
                    # Light attributes must observe confirmed memory, not the
                    # pending intent. Equal-state polls may not notify again.
                    self.async_set_updated_data(state)

    async def async_turn_on(self, *, resume_schedule: bool = False) -> None:
        """Restore remembered Manual output or explicitly resume the stored schedule."""
        # Resume works from normal modes without requiring the separate Off gate.
        if resume_schedule and self.data is not None and self.data.system.mode_raw != MODE_SHUTDOWN:
            await self.async_set_mode("automatic_program")
            return
        deadline = asyncio.get_running_loop().time() + EXPLICIT_COMMAND_TIMEOUT
        self._require_power_supported()
        epoch = self._command_epoch
        self._channel_generations = [value + 1 for value in self._channel_generations]
        async with self._command_window(deadline):
            async with self._io_lock:
                self._check_command_deadline(deadline)
                self._require_power_request(epoch)
                self._active_command = asyncio.current_task()
                manual, _reason = self.power_memory.manual_restore(self.data)
                try:
                    state = await self.client.turn_on(
                        manual_channels=None if resume_schedule else manual,
                        expected_state=self.data,
                    )
                except (AquariusError, ProtocolError, OSError, TimeoutError):
                    self._read_failed()
                    self.async_set_update_error(UpdateFailed("Software On was not confirmed"))
                    raise HomeAssistantError(
                        "On was not confirmed. No command was retried"
                    ) from None
                self._read_succeeded()
                await self._publish_observation(state)

    async def async_prepare_unload(self) -> None:
        """Stop accepting commands before native platform unloading can yield."""
        self._quiescing = True
        self._command_epoch += 1
        tasks = {
            task
            for task in (self._active_command, self._active_read)
            if task is not None and task is not asyncio.current_task()
        }
        for task in tasks:
            task.cancel()
        if tasks:
            # A read includes its observation save. Settle that write before a
            # replacement coordinator can load memory or save a new Off intent.
            await asyncio.gather(*tasks, return_exceptions=True)

    async def async_resume_after_failed_unload(self) -> None:
        """Read current state before permitting new actions after failed unloading."""
        self._resuming = True
        try:
            await self.async_refresh()
        finally:
            self._resuming = False
            self._quiescing = False

    async def async_shutdown(self) -> None:
        """Invalidate pending slider work and release the client without writes."""
        self._stopped = True
        await self.async_prepare_unload()
        await super().async_shutdown()
        # Client close cancels any active transaction. Do not wait behind that
        # transaction's lock and let a command continue during unloading.
        await self.client.close()
