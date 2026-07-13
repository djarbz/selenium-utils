"""Module to provide Exception handling for the project."""

import linecache
import logging
import sys
import traceback
from pathlib import Path
from typing import Any

from seleniumbase import SB

from selenium_utils.misc import add_run_report_item
from selenium_utils.discord import send_webhook, WebhookConfig
from selenium_utils.config import APP_DEBUG, LOG_TRACE
from selenium_utils.selectors import SeleniumSelector
from selenium_utils.archive import full_page_archive, generate_clean_filename

logger = logging.getLogger(__name__)

EXIT_CODE = 0


def increment_exit_code(inc: int = 1) -> int:
    global EXIT_CODE
    EXIT_CODE += inc
    return EXIT_CODE


class ExceptionHandlerError(Exception):
    """Custom exception for error in exception handler."""


def get_most_recent_project_frame(
    project_root: str = None,
) -> tuple[str, str, int] | None:
    _, _, exc_traceback = sys.exc_info()
    if exc_traceback is None:
        return None
    if project_root is None:
        project_root = str(Path(__file__).resolve().parent.parent)
    last_project_frame = None
    frame = exc_traceback
    while frame:
        filename = frame.tb_frame.f_code.co_filename
        if project_root in filename:
            last_project_frame = frame
        frame = frame.tb_next
    if last_project_frame:
        return (
            last_project_frame.tb_frame.f_code.co_filename,
            last_project_frame.tb_frame.f_code.co_name,
            last_project_frame.tb_lineno,
        )
    frame = exc_traceback
    while frame.tb_next:
        frame = frame.tb_next
    return (
        frame.tb_frame.f_code.co_filename,
        frame.tb_frame.f_code.co_name,
        frame.tb_lineno,
    )


def handle_exception(
    message: str,
    exc_obj: Exception,
    sb: SB = None,
    name: str = None,
    zoom: SeleniumSelector = None,
    **kwargs: Any,
) -> Path | None:
    increment_exit_code()
    add_run_report_item(f"EXCEPTION>{EXIT_CODE:03d}", message)
    image_filepath: Path | None = None

    try:
        if hasattr(exc_obj, "stacktrace"):
            exc_obj.stacktrace = None
        e_vars = _extract_exception_details(exc_obj)
        logger.error("EXCEPTION DETAIL: %s >>> %s", message, exc_obj, extra=e_vars)

        _log_traceback_frames(exc_obj, e_vars)
        _log_frame_details(exc_obj)

        current_url, image_filepath = _handle_selenium_details(sb, name, zoom)
        write_exception_to_file(image_filepath, exc_obj, message)

        send_webhook(
            WebhookConfig(
                title="EXCEPTION SOURCE",
                description=message or e_vars.get("MESSAGE"),
                image_filepath=image_filepath,
                additional_fields=kwargs,
            ),
            Url=current_url,
            EXIT_CODE=EXIT_CODE,
            **e_vars,
        )
    except Exception as inner_e:
        logger.exception("Failed to handle exception: %s", inner_e)

    if sb:
        try:
            full_page_archive(sb, "EXCEPTION")
        except Exception:
            pass
    return image_filepath


def write_exception_to_file(
    filepath: Path, exception: Exception = None, additional_message: str = None
) -> None:
    try:
        exc_path = filepath.with_suffix(".EXCEPTION.txt")
        with exc_path.open("a", encoding="utf-8") as file:
            if additional_message:
                file.write(f"{additional_message}\n")
            if exception is None:
                file.write(traceback.format_exc())
            else:
                tb_lines = traceback.format_exception(
                    type(exception), exception, exception.__traceback__
                )
                file.write("".join(tb_lines))
    except Exception:
        pass


def _log_traceback_frames(e: Exception, e_vars: dict[str, Any]) -> None:
    try:
        tb = e.__traceback__
        tbi = 0
        while tb:
            tbi += 1
            try:
                code_line = linecache.getline(
                    tb.tb_frame.f_code.co_filename, tb.tb_lineno
                )
            except OSError:
                code_line = "<could not retrieve code line>"
            e_vars[f"Traceback frame #{tbi:02}"] = (
                f"File: {tb.tb_frame.f_code.co_filename}, Line: {tb.tb_lineno}\nFunction: {tb.tb_frame.f_code.co_name}\nCode: {code_line}"
            )
            tb = tb.tb_next
    except Exception:
        pass


def _handle_selenium_details(
    sb: SB = None, name: str = "EXCEPTION", zoom: SeleniumSelector = None
) -> tuple[str, Path]:
    current_url = name
    image_filepath = generate_clean_filename(name or "EXCEPTION", ".txt")
    if not sb:
        return current_url, image_filepath
    try:
        if zoom:
            _, image_filepath = zoom.archive(sb, name or "EXCEPTION")
        else:
            _, image_filepath = full_page_archive(sb, name or "EXCEPTION")
        current_url = sb.get_current_url()
    except Exception:
        pass
    return current_url, image_filepath


def _log_frame_details(e: Exception) -> None:
    if not APP_DEBUG:
        return
    try:
        tb = e.__traceback__
        tbi = 0
        while tb:
            tbi += 1
            code_line = linecache.getline(tb.tb_frame.f_code.co_filename, tb.tb_lineno)
            logger.log(
                LOG_TRACE,
                "Frame[%d] %s in %s:%s [%s]",
                tbi,
                tb.tb_frame.f_code.co_name,
                tb.tb_frame.f_code.co_filename,
                tb.tb_lineno,
                code_line,
                extra={"Frame Vars": tb.tb_frame.f_locals},
            )
            tb = tb.tb_next
    except Exception:
        pass


def _extract_exception_details(exc_obj: Exception) -> dict[str, Any]:
    e_vars = {}
    try:
        frame_info = get_most_recent_project_frame()
        if frame_info:
            e_vars["FILE"], e_vars["FUNC"], e_vars["LINE"] = frame_info
            e_vars["CODE"] = linecache.getline(
                e_vars["FILE"], int(e_vars["LINE"])
            ).strip()
        e_vars["TYPE"] = str(sys.exc_info()[0])
        e_vars["MESSAGE"] = getattr(exc_obj, "msg", str(exc_obj))
        e_vars["TRACEBACK"] = "".join(
            traceback.format_exception(type(exc_obj), exc_obj, exc_obj.__traceback__)
        )
    except Exception:
        pass
    return e_vars
