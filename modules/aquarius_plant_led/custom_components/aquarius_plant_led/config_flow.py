"""Manual local setup; no network discovery and no configuration writes."""

import re
from ipaddress import ip_address

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .client import AquariusClient, AquariusError
from .const import DEFAULT_PORT, DOMAIN, NAME
from .protocol import ProtocolError


def _normalize_host(value: str) -> str:
    """Canonicalize endpoints for duplicate checks without inventing device IDs."""
    value = value.strip().lower().rstrip(".")
    try:
        return str(ip_address(value))
    except ValueError:
        if (
            not value
            or len(value) > 253
            or any(
                not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in value.split(".")
            )
        ):
            raise vol.Invalid("Enter an IP address or hostname, without a URL or port") from None
        return value


def _schema(defaults: dict | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): vol.All(
                str, _normalize_host
            ),
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): vol.All(
                vol.Coerce(int), vol.Range(min=1, max=65535)
            ),
        }
    )


class AquariusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure one controller endpoint with stable config-entry identity."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._target: tuple[str, int] | None = None

    @callback
    def is_matching(self, other_flow) -> bool:
        """Reserve an endpoint while its read-only connection check is running."""
        return self._target is not None and self._target == getattr(other_flow, "_target", None)

    def _duplicate_reason(self, data: dict, entry_id: str | None = None) -> str | None:
        self._target = (data[CONF_HOST], data[CONF_PORT])
        for entry in self._async_current_entries(include_ignore=True):
            if entry.entry_id == entry_id:
                continue
            if self._target == (
                _normalize_host(entry.data[CONF_HOST]),
                entry.data.get(CONF_PORT, DEFAULT_PORT),
            ):
                return "already_configured"
        if self.hass.config_entries.flow.async_has_matching_flow(self):
            return "already_in_progress"
        return None

    async def _async_validate(self, data: dict) -> str | None:
        client = AquariusClient(data[CONF_HOST], data[CONF_PORT])
        try:
            await client.refresh()
        except ProtocolError:
            return "invalid_response"
        except (AquariusError, OSError, TimeoutError):
            return "cannot_connect"
        finally:
            await client.close()
        return None

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Add a manually specified lamp after a read-only protocol check."""
        errors = {}
        if user_input is not None:
            user_input = _schema()(user_input)
            if reason := self._duplicate_reason(user_input):
                return self.async_abort(reason=reason)
            if error := await self._async_validate(user_input):
                errors["base"] = error
                self._target = None
            else:
                # The protocol has no verified immutable identifier. The native
                # entry_id, never the host or raw controller bytes, anchors entities.
                return self.async_create_entry(title=NAME, data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(user_input), errors=errors)

    async def async_step_reconfigure(self, user_input=None) -> FlowResult:
        """Change access details in place, retaining device/entity registry IDs."""
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            user_input = _schema()(user_input)
            if reason := self._duplicate_reason(user_input, entry.entry_id):
                return self.async_abort(reason=reason)
            if error := await self._async_validate(user_input):
                errors["base"] = error
                self._target = None
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input, reason="reconfigure_successful"
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(user_input or dict(entry.data)),
            errors=errors,
        )
