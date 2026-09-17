"""Native power and explicitly configured approximate colour controls."""

from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .compact import compact_roles_from_options, peak_intensity, rgb_from_channels, validate_rgb
from .entity import AquariusEntity
from .protocol import MODE_AUTOMATIC, MODE_MANUAL, MODE_SHUTDOWN

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([AquariusPower(entry.runtime_data)])


class AquariusPower(AquariusEntity, LightEntity):
    """An enabled schedule is On even when its current output is zero."""

    _attr_translation_key = "power"
    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF
    _attr_icon = "mdi:lightbulb"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "power")
        self._roles = compact_roles_from_options(coordinator.config_entry.options)
        if self._roles is not None:
            self._attr_supported_color_modes = {ColorMode.RGB}
            self._attr_color_mode = ColorMode.RGB

    @property
    def brightness(self) -> int | None:
        if self._roles is None:
            return None
        if self.coordinator.data.system.mode_raw == MODE_SHUTDOWN:
            return 0
        return (peak_intensity(self.coordinator.data.channels) * 255 + 50) // 100

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        if self._roles is None:
            return None
        state = self.coordinator.data
        channels = state.channels
        if state.system.mode_raw == MODE_SHUTDOWN:
            channels, _reason = self.coordinator.power_memory.manual_restore(state)
            if channels is None:
                return None
        return rgb_from_channels(channels, self._roles)

    @property
    def is_on(self) -> bool | None:
        mode = self.coordinator.data.system.mode_raw
        if mode == MODE_SHUTDOWN:
            return False
        return True if mode in (MODE_AUTOMATIC, MODE_MANUAL) else None

    @property
    def extra_state_attributes(self) -> dict:
        _channels, reason = self.coordinator.power_memory.manual_restore(self.coordinator.data)
        attributes = {
            "power_control_validated": self.coordinator.data.system.power_supported,
            "on_behavior": reason,
            "compact_control_configured": self._roles is not None,
        }
        if self._roles is not None:
            attributes["colour_representation"] = "Approximate preview from channel levels"
            attributes["intensity_basis"] = "Highest channel percentage; not measured luminosity"
        return attributes

    async def async_turn_on(self, **kwargs) -> None:
        rgb = kwargs.get(ATTR_RGB_COLOR)
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if rgb is None and brightness is None:
            await self.coordinator.async_turn_on()
            return
        if self._roles is None:
            raise ServiceValidationError("Configure the compact channel roles before using colour")
        try:
            rgb = validate_rgb(rgb) if rgb is not None else None
        except ValueError as error:
            raise ServiceValidationError(str(error)) from error
        if brightness is not None and (type(brightness) is not int or not 0 <= brightness <= 255):
            raise ServiceValidationError("Brightness must be an integer from 0 to 255")
        if brightness == 0 or rgb == (0, 0, 0):
            await self.coordinator.async_turn_off()
            return
        # HA already converts brightness_pct to 0..255 and other colour formats
        # to RGB. Preserve RGB's own amplitude: the mixer applies it exactly once.
        intensity = max(1, (brightness * 100 + 127) // 255) if brightness is not None else None
        await self.coordinator.async_set_compact(rgb_color=rgb, intensity=intensity)

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_turn_off()
