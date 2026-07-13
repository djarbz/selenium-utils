"""Module to provide miscellaneous tooling."""

import inspect
import logging
import os
import sys
import textwrap
from pathlib import Path
from shutil import get_terminal_size
from typing import Any, Dict, Callable
from pathvalidate import sanitize_filename

from seleniumbase.fixtures import page_utils
from selenium_utils.config import LOG_DIR

logger = logging.getLogger(__name__)

RUN_REPORT: Dict[str, Any] = {}


class StepCounter:
    """Keep track of the current step index and allow progress."""

    def __init__(self, initial_value: int = 0):
        self._count = initial_value

    def increment(self, inc: int = 1) -> int:
        self._count += inc
        return self._count

    def get(self) -> int:
        return self._count


step_tracker = StepCounter()


class TerminalWidth:
    def __init__(self, fallback: int = 160):
        self._fallback = fallback
        self._width: int | None = None
        self._get_width()

    def _get_width(self) -> None:
        if self._width is not None:
            return
        try:
            env_width = int(os.environ.get("TERMINAL_WIDTH", self._fallback))
        except ValueError:
            env_width = self._fallback
        try:
            if sys.stdout.isatty():
                self._width = get_terminal_size().columns
            else:
                self._width = env_width
        except OSError:
            self._width = self._fallback
        if self._width is None:
            self._width = self._fallback

    def get_width(self) -> int:
        self._get_width()
        return self._width


TERMINAL_WIDTH = TerminalWidth()


class MisconfigurationError(Exception):
    """Custom exception for misconfiguration."""


def validate_url(url: str) -> str:
    if not isinstance(url, str):
        raise TypeError(f"URL must be a string, not {type(url)}")
    if not page_utils.is_valid_url(url):
        raise ValueError(f"Invalid URL: {url}")
    return url


def print_terminal(message: str) -> None:
    if not isinstance(message, str):
        raise TypeError(f"Message must be a string, not {type(message)}")
    try:
        wrapped_message = textwrap.wrap(
            message, width=TERMINAL_WIDTH.get_width(), break_long_words=False
        )
        print("\n".join(wrapped_message))
    except Exception as e:
        logger.exception("Printing message to Terminal [%s] FAILED: %s", message, e)


def center_string(text: str, fill_char: str = "*") -> None:
    padded_text = f"  {text}  "
    print(padded_text.center(TERMINAL_WIDTH.get_width(), fill_char))


def add_run_report_item(key: str, value: Any) -> None:
    if not isinstance(key, str):
        raise TypeError(f"key must be a string, not {type(key)}")
    RUN_REPORT[key] = value


def is_function_in_call_stack(func: Callable) -> bool:
    if not callable(func):
        raise TypeError(f"Func must be callable, not {type(func)}")
    for frame_info in inspect.stack():
        if (
            frame_info.function == func.__name__
            and frame_info.frame.f_code is func.__code__
        ):
            return True
    return False


def hash2hex(text: str) -> str:
    running_hash = 0
    for ch in text:
        running_hash = (running_hash * 281 ^ ord(ch) * 997) & 0xFFFFFFFF
    return hex(running_hash)[2:].upper().zfill(8)


def generate_clean_filename(file_name: str, new_ext: str) -> Path:
    if not new_ext.startswith("."):
        new_ext = "." + new_ext

    clean_name = Path(
        sanitize_filename(
            os.path.basename(f"{step_tracker.increment():02d}-{file_name}"),
            validate_after_sanitize=True,
        )
    )

    if clean_name.suffix.lower() in [".txt", ".html", ".png"]:
        file_path = Path(clean_name).with_suffix(new_ext).name
    else:
        file_path = clean_name.name + new_ext

    full_path = Path(LOG_DIR).joinpath(file_path).resolve()
    full_path.parent.mkdir(parents=True, exist_ok=True)
    return full_path
