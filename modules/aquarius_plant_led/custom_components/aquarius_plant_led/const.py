"""Constants for the independent Aquarius Plant LED integration."""

DOMAIN = "aquarius_plant_led"
NAME = "Aquarius Plant LED"
VERSION = "0.1.0"
DEFAULT_PORT = 8080
POLL_SECONDS = 30
MAX_BACKOFF_SECONDS = 300
CHANNEL_DEBOUNCE_SECONDS = 0.35
CHANNEL_LABELS = ("A", "B", "C", "D", "E", "F")

# Raw modes are protocol values, not guesses based on the current channel levels.
MODE_MANUAL = 1
MODE_AUTOMATIC = 0
MODE_OPTIONS = {"manual": MODE_MANUAL, "automatic_program": MODE_AUTOMATIC}
