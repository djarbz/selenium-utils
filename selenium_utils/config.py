"""Global configuration for the shared automation framework."""

import logging
import os

def get_bool_env(name: str, default_value: bool = None) -> bool:
    """Get a boolean from an environment variable with a default value."""
    true_values = ("true", "1", "t", "yes", "y", "on")
    false_values = ("false", "0", "f", "no", "n", "off")

    value = os.getenv(name)
    if value is None:
        if default_value is None:
            raise ValueError(f"Variable `{name}` not set!")
        return default_value

    value_lower = value.lower()
    if value_lower in true_values:
        return True
    if value_lower in false_values:
        return False

    raise ValueError(f"Invalid value `{value}` for variable `{name}`")


APP_DEBUG = get_bool_env("DEBUG", False)
APP_TRACE = get_bool_env("TRACE", False)
APP_LOGALL = get_bool_env("LOGALL", False)

LOG_DIR = "latest_logs"
LOG_FORMAT = "%(levelname)-8s | %(module)s:%(funcName)s:%(lineno)04d | %(message)s"
LOG_TRACE = logging.DEBUG + 5
LOG_NOTICE = logging.INFO + 5

WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 1904
