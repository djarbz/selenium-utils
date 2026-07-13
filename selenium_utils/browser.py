"""Module to handle browser state, navigation, and waits."""

import logging
import time
from urllib.parse import urlparse, urlunparse

from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait
from seleniumbase import SB
from seleniumbase.common.exceptions import WebDriverException

from selenium_utils.archive import full_page_archive
from selenium_utils.config import LOG_NOTICE

logger = logging.getLogger(__name__)


class JQueryNotReadyError(Exception):
    """Custom exception for when JQuery is not ready."""


class BrowserNotReadyError(Exception):
    """Custom exception for when the browser is not ready."""


class NavigationError(Exception):
    """Custom exception for URL navigation errors."""


class InvalidURLException(Exception):
    """Custom exception for parsing errors."""


def close_extra_windows(sb: SB, url: str) -> None:
    if len(sb.driver.window_handles) == 1:
        return
    for window_handle in sb.driver.window_handles[1:]:
        try:
            sb.switch_to_window(window_handle)
            if not sb.get_current_url().startswith(url):
                sb.driver.close()
        except Exception:
            pass
    sb.switch_to_default_window()


def wait_browser_ready(sb: SB, timeout: int = 30) -> None:
    try:
        WebDriverWait(sb.driver, timeout).until(ec.number_of_windows_to_be(1))
    except Exception as e:
        raise BrowserNotReadyError("Browser not ready!") from e


def wait_jquery(sb: SB, timeout: int = 30, sleep_time: float = 0.2) -> None:
    if not sb.safe_execute_script("return (typeof(jQuery) != 'undefined')"):
        return
    if not sb.wait_for_ready_state_complete(timeout=timeout):
        raise JQueryNotReadyError("JQuery timeout!")
    must_end = time.time() + timeout
    while time.time() < must_end:
        try:
            if sb.safe_execute_script("return jQuery.active == 0"):
                return
        except WebDriverException:
            pass
        time.sleep(sleep_time)
    raise JQueryNotReadyError("JQuery timeout!")


def navigate_url(sb: SB, url: str, desc: str = "page", timeout: int = 30) -> None:
    try:
        parsed_url = urlparse(url)
        scheme = parsed_url.scheme
        netloc = parsed_url.netloc

        if not scheme or not netloc:
            current_domain = sb.get_domain_url(sb.get_current_url())
            current_parsed = urlparse(current_domain)
            if not scheme:
                scheme = current_parsed.scheme or "https"
            if not netloc:
                netloc = current_parsed.netloc

        full_url = urlunparse(
            (
                scheme,
                netloc,
                parsed_url.path,
                parsed_url.params,
                parsed_url.query,
                parsed_url.fragment,
            )
        )
    except Exception as e:
        raise InvalidURLException(f"Failed to parse URL: {url}") from e

    try:
        logger.log(LOG_NOTICE, "Navigating to %s [%s]", desc, full_url)
        sb.uc_open(full_url)
        must_end = time.time() + timeout
        while time.time() < must_end:
            if sb.get_current_url() == full_url:
                wait_jquery(sb)
                full_page_archive(sb, "NAVIGATE")
                return
            time.sleep(1)
        raise NavigationError(f"Failed to navigate to {full_url}")
    except Exception as e:
        raise NavigationError(f"Failed to navigate to {full_url}: {e}") from e
