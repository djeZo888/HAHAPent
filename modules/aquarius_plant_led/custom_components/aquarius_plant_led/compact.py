"""Pure, explicit six-channel recipes for approximate compact colour controls.

Roles are independently configured semantics, never inferred from display labels.
Percentages describe controller levels, not calibrated light output or spectra.
All arithmetic stays integral so half-up quantization is reproducible.
"""

from __future__ import annotations

from collections.abc import Mapping

COMPACT_ROLES_VERSION = 1
CONF_CHANNEL_ROLES = "channel_roles"
CONF_CHANNEL_ROLES_VERSION = "channel_roles_version"

_CHANNEL_KEYS = tuple("channel_" + letter for letter in "abcdef")
_ROLES = frozenset({"unused", "red", "green", "blue", "white"})
_PRIMARIES = ("red", "green", "blue")
_ZERO_CHANNELS = (0, 0, 0, 0, 0, 0)


def validate_roles(roles) -> tuple[str, ...]:
    """Validate an already ordered six-role runtime sequence before I/O."""
    if (
        not isinstance(roles, (tuple, list))
        or len(roles) != 6
        or any(not isinstance(role, str) or role not in _ROLES for role in roles)
        or not set(_PRIMARIES).issubset(roles)
    ):
        raise ValueError("six explicit roles including red, green and blue are required")
    return tuple(roles)


def normalize_channel_roles(mapping: Mapping) -> tuple[str, ...]:
    """Validate exactly A–F and return roles in protocol channel order.

    Duplicate primaries and whites are allowed; every primary must be present.
    Options storage retains the keyed mapping, not this immutable runtime tuple.
    """
    if not isinstance(mapping, Mapping) or set(mapping) != set(_CHANNEL_KEYS):
        raise ValueError("roles must contain exactly channel_a through channel_f")
    return validate_roles(tuple(mapping[key] for key in _CHANNEL_KEYS))


def compact_roles_from_options(options: Mapping) -> tuple[str, ...] | None:
    """Return only a complete, explicitly versioned role mapping; never guess."""
    if not isinstance(options, Mapping):
        return None
    version = options.get(CONF_CHANNEL_ROLES_VERSION)
    if type(version) is not int or version != COMPACT_ROLES_VERSION:
        return None
    try:
        return normalize_channel_roles(options.get(CONF_CHANNEL_ROLES))
    except ValueError:
        return None


def _integer_tuple(value, size: int, maximum: int, description: str) -> tuple[int, ...]:
    if (
        not isinstance(value, (tuple, list))
        or len(value) != size
        or any(type(item) is not int or not 0 <= item <= maximum for item in value)
    ):
        raise ValueError(description)
    return tuple(value)


def validate_rgb(value) -> tuple[int, int, int]:
    """Require three integer RGB values in 0–255, excluding bool and floats."""
    return _integer_tuple(value, 3, 255, "RGB must contain three integers from 0 to 255")


def validate_intensity(value) -> int:
    """Require an integer controller percentage, without coercion or clamping."""
    if type(value) is not int or not 0 <= value <= 100:
        raise ValueError("intensity must be an integer from 0 to 100")
    return value


def _channels(value) -> tuple[int, ...]:
    return _integer_tuple(value, 6, 100, "channels must contain six integers from 0 to 100")


def _half_up(numerator: int, denominator: int) -> int:
    """Round an exact nonnegative ratio to the nearest integer, ties upward."""
    return (2 * numerator + denominator) // (2 * denominator)


def mix_rgb(rgb_color, intensity, roles) -> tuple[int, ...]:
    """Build one complete vector from RGB, intensity and explicit channel roles.

    With white channels, extract min(R,G,B) before assigning residual primaries.
    Equal roles receive equal levels; unused channels are zero. Normalize the
    recipe peak, then apply intensity and the input RGB peak/255 once. Positive
    intent below the lamp's one-percent resolution lights all tied peak channels
    at one percent rather than producing an ambiguous all-zero Manual vector.
    """
    rgb = validate_rgb(rgb_color)
    level = validate_intensity(intensity)
    mapping = validate_roles(roles)
    rgb_peak = max(rgb)
    if not level or not rgb_peak:
        return _ZERO_CHANNELS
    white = min(rgb) if "white" in mapping else 0
    components = {role: value - white for role, value in zip(_PRIMARIES, rgb)}
    components.update(white=white, unused=0)
    recipe = tuple(components[role] for role in mapping)
    recipe_peak = max(recipe)
    denominator = 255 * recipe_peak
    result = tuple(_half_up(value * level * rgb_peak, denominator) for value in recipe)
    if not any(result):
        return tuple(1 if value == recipe_peak else 0 for value in recipe)
    return result


def scale_channels(channels, intensity) -> tuple[int, ...]:
    """Scale every freshly observed channel by its common peak, preserving ratios.

    No colour-role filtering applies: detailed per-channel mixes remain intact.
    A positive request cannot invent a mix from a zero basis.
    """
    values = _channels(channels)
    level = validate_intensity(intensity)
    if not level:
        return _ZERO_CHANNELS
    peak = max(values)
    if not peak:
        raise ValueError(
            "positive intensity requires a nonzero channel basis; choose a colour first"
        )
    return tuple(_half_up(value * level, peak) for value in values)


def rgb_from_channels(channels, roles) -> tuple[int, int, int] | None:
    """Approximate a normalized RGB display using max-per-role, never role sums.

    Add the largest white level to each primary, then normalize the largest RGB
    value to 255. Unused-only output has no inferred colour. This display does not
    claim calibrated colour accuracy or a reversible spectral representation.
    """
    values = _channels(channels)
    mapping = validate_roles(roles)
    components = {role: 0 for role in _ROLES}
    for role, value in zip(mapping, values):
        components[role] = max(components[role], value)
    rgb = tuple(components[role] + components["white"] for role in _PRIMARIES)
    peak = max(rgb)
    if not peak:
        return None
    return tuple(_half_up(value * 255, peak) for value in rgb)


def peak_intensity(channels) -> int:
    """Return the largest of six validated controller percentages."""
    return max(_channels(channels))
