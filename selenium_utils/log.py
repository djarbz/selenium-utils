"""Module to provide custom logging setup"""

import json
import logging
import os
from logging.handlers import MemoryHandler
from pathlib import Path

from selenium_utils.config import (
    LOG_DIR, LOG_FORMAT, LOG_TRACE, LOG_NOTICE,
    APP_LOGALL, APP_TRACE, APP_DEBUG,
)

def add_logging_level(level_name, level_num, method_name=None):
    if not method_name:
        method_name = level_name.lower()
    if hasattr(logging, level_name):
        raise AttributeError(f"{level_name} already defined in logging module")

    def log_for_level(self, message, *args, **kwargs):
        if self.isEnabledFor(level_num):
            self._log(level_num, message, args, **kwargs)

    def log_to_root(message, *args, **kwargs):
        logging.log(level_num, message, *args, **kwargs)

    logging.addLevelName(level_num, level_name)
    setattr(logging, level_name, level_num)
    setattr(logging.getLoggerClass(), method_name, log_for_level)
    setattr(logging, method_name, log_to_root)


class ExFormatter(logging.Formatter):
    def_keys = [
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message", "taskName",
    ]

    def _handle_extra_keys(self, record: logging.LogRecord) -> dict | None:
        extra = {}
        for key, value in record.__dict__.items():
            if key not in self.def_keys:
                extra[key] = value
        return extra

    def format(self, record):
        record.message = record.getMessage()
        if self.usesTime():
            record.asctime = self.formatTime(record, self.datefmt)
        s = self.formatMessage(record)
        extra = self._handle_extra_keys(record)
        if extra:
            s = f"{s} | extra: {json.dumps(extra)}"
        if record.exc_info and record.exc_info != (None, None, None):
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            if s[-1:] != "\n":
                s = s + "\n"
            s = s + record.exc_text
        if record.stack_info:
            if s[-1:] != "\n":
                s = s + "\n"
            s = s + self.formatStack(record.stack_info)
        return s

    def _format(self, record: logging.LogRecord):
        extra = self._handle_extra_keys(record)
        if extra:
            record.msg = f"{record.msg} | extra: {json.dumps(extra)}"
        return super().format(record)


def setup_logging() -> None:
    add_logging_level("TRACE", LOG_TRACE)
    add_logging_level("NOTICE", LOG_NOTICE)
    add_logging_level("SBase", 5)

    root_logger = logging.getLogger("")
    root_logger.setLevel(logging.NOTSET)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    log_dir_path = Path(LOG_DIR).resolve()
    log_dir_path.mkdir(parents=True, exist_ok=True)

    file_log_level, console_log_level = _get_log_levels()
    formatter = ExFormatter(LOG_FORMAT)

    file_handler = _create_file_handler(formatter, file_log_level, log_dir_path)
    console_handler = _create_console_handler(formatter, console_log_level)
    memory_handler = _create_memory_handler(formatter, log_dir_path)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(memory_handler)
    _log_enabled_levels(log_dir_path)


def _log_level_to_name(level: int) -> str:
    return logging._levelToName.get(level)

def _log_level_to_int(level: str) -> int:
    return logging._nameToLevel.get(level)

def _get_log_levels():
    file_level, console_level = LOG_TRACE, LOG_NOTICE
    if APP_DEBUG:
        file_level, console_level = LOG_TRACE, logging.INFO
    if APP_TRACE:
        file_level, console_level = LOG_TRACE, LOG_TRACE
    if APP_LOGALL:
        file_level, console_level = logging.NOTSET, logging.NOTSET

    file_level = _log_level_to_int(os.environ.get("FILE_LEVEL", _log_level_to_name(file_level)).upper())
    console_level = _log_level_to_int(os.environ.get("CONSOLE_LEVEL", _log_level_to_name(console_level)).upper())
    return file_level, console_level


def _create_file_handler(formatter: logging.Formatter, level: int, log_dir: Path) -> logging.FileHandler:
    log_file = log_dir / "last.log"
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    print(f"Logging to {log_file} with level {level}")
    return file_handler

def _create_console_handler(formatter: logging.Formatter, level: int) -> logging.StreamHandler:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    print(f"Logging to console with level {level}")
    return console_handler

def _create_memory_handler(formatter: logging.Formatter, log_dir: Path) -> MemoryHandler:
    crash_file = log_dir / "crash_dump.log"
    target_handler = logging.FileHandler(crash_file, mode="w")
    target_handler.setLevel(logging.NOTSET)
    target_handler.setFormatter(formatter)
    memory_handler = MemoryHandler(capacity=10000, flushLevel=logging.ERROR, target=target_handler)
    memory_handler.setLevel(LOG_TRACE)
    return memory_handler

def _log_enabled_levels(log_dir: Path):
    if APP_DEBUG or APP_TRACE:
        for level in logging._levelToName:
            logging.log(level, "%s logging enabled!", logging.getLevelName(level))
        logging.log(LOG_TRACE, "Using log file: %s", log_dir / "last.log")
