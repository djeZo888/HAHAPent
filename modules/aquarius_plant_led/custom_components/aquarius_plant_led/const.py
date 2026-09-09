"""Constants for the independent Aquarius Plant LED integration."""

from collections.abc import Mapping
from unicodedata import category

DOMAIN = "aquarius_plant_led"
NAME = "Aquarius Plant LED"
VERSION = "0.3.1"
DEFAULT_PORT = 8080
POLL_SECONDS = 30
MAX_BACKOFF_SECONDS = 300
CHANNEL_DEBOUNCE_SECONDS = 0.35
CHANNEL_LABELS = ("A", "B", "C", "D", "E", "F")
CHANNEL_KEYS = tuple(f"channel_{letter.lower()}" for letter in CHANNEL_LABELS)
CONF_CHANNEL_LABELS = "channel_labels"
CONF_CHANNEL_LABELS_VERSION = "channel_labels_version"
CHANNEL_LABELS_VERSION = 1
MAX_CHANNEL_LABEL_LENGTH = 40
CHANNEL_LABEL_CHOICES = ("Daylight white", "Warm white", "Blue", "Ruby red", "Red", "Green")


class InvalidChannelLabels(ValueError):
    """A local display-label validation error, unrelated to lamp state."""

    def __init__(self, field: str, reason: str) -> None:
        super().__init__(reason)
        self.field = field
        self.reason = reason


def default_channel_labels() -> dict[str, str]:
    """Keep protocol letters until a per-lamp mapping is explicitly supplied."""
    return {key: f"Channel {letter}" for key, letter in zip(CHANNEL_KEYS, CHANNEL_LABELS)}


def normalize_channel_labels(values: Mapping) -> dict[str, str]:
    """Require six distinct plain-text labels; never infer colours or channel order."""
    if not isinstance(values, Mapping) or set(values) != set(CHANNEL_KEYS):
        raise InvalidChannelLabels("base", "invalid_labels")
    labels = {}
    seen = set()
    for key in CHANNEL_KEYS:
        value = values[key]
        if not isinstance(value, str) or any(
            category(char).startswith("C") or char in "<>" for char in value
        ):
            raise InvalidChannelLabels(key, "invalid_label")
        label = " ".join(value.split())
        if not label or len(label) > MAX_CHANNEL_LABEL_LENGTH:
            raise InvalidChannelLabels(key, "invalid_label")
        folded = label.casefold()
        if folded in seen:
            raise InvalidChannelLabels(key, "duplicate_label")
        seen.add(folded)
        labels[key] = label
    return labels


def channel_labels_from_options(options: Mapping) -> dict[str, str]:
    """Unknown or malformed label options fall back to the unambiguous defaults."""
    version = options.get(CONF_CHANNEL_LABELS_VERSION)
    if type(version) is not int or version != CHANNEL_LABELS_VERSION:
        return default_channel_labels()
    try:
        return normalize_channel_labels(options.get(CONF_CHANNEL_LABELS))
    except InvalidChannelLabels:
        return default_channel_labels()


# Raw modes are protocol values, not guesses based on the current channel levels.
MODE_MANUAL = 1
MODE_AUTOMATIC = 0
MODE_OPTIONS = {"manual": MODE_MANUAL, "automatic_program": MODE_AUTOMATIC}
