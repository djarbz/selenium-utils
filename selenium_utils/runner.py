"""Universal wrapper to orchestrate the standard SeleniumBase runtime."""

import logging
from typing import Callable

from seleniumbase import SB

from selenium_utils import exceptions
from selenium_utils.archive import full_page_archive
from selenium_utils.browser import wait_browser_ready
from selenium_utils.config import WINDOW_HEIGHT, WINDOW_WIDTH
from selenium_utils.discord import init_webhook
from selenium_utils.log import setup_logging
from selenium_utils.misc import RUN_REPORT

logger = logging.getLogger(__name__)


def _initialize_selenium() -> SB:
    """Initializes SeleniumBase with standard shared arguments."""
    logger.info("Initializing Selenium Session...")
    return SB(
        test="Output",
        raise_test_failure=True,
        browser="chrome",
        headless2=True,
        undetectable=True,
        dark_mode=True,
        is_mobile=True,
        incognito=True,
        save_screenshot=True,
    )


def _log_run_report() -> None:
    """Logs the run report details if populated."""
    if not RUN_REPORT:
        return
    logger.info("--- RUN REPORT ---")
    for key, value in RUN_REPORT.items():
        logger.info("%s: %s", key, value)


def run_automation(
    app_name: str, start_url: str, logic_callback: Callable[[SB], None]
) -> int:
    """
    The universal automation wrapper.

    Args:
        app_name: The name of the project to display in webhook/logs.
        start_url: The initial URL to navigate to.
        logic_callback: A function containing the project-specific automation logic.
    """
    import os

    os.environ["APP_NAME"] = app_name  # Makes it available for Discord webhook

    setup_logging()
    init_webhook()
    sb_init = False
    current_url = "SB INIT"

    try:
        logger.info("Preparing [%s] Automation...", app_name)
        with _initialize_selenium() as sb:
            try:
                browser_ver = sb.driver.capabilities.get("browserVersion", "Unknown")
                logger.info("Using Browser version [%s]", browser_ver)
            except Exception:
                pass

            sb.uc_open_with_reconnect(start_url, 10)
            wait_browser_ready(sb)
            current_url = sb.get_current_url()

            sb.set_window_size(WINDOW_WIDTH, WINDOW_HEIGHT)
            sb.set_default_timeout(15)
            full_page_archive(sb, "BEGIN")
            sb_init = True

            # Hand control back to the project-specific logic
            logic_callback(sb)

            logger.info("[%s] Automation Complete!", app_name)

    except Exception as e:
        if not sb_init:
            exceptions.handle("SB Initialization Failed", e, None, "SB>Init")
        else:
            exceptions.handle("Automation Failed", e, sb, "SB>Loop", url=current_url)
    finally:
        _log_run_report()

    return exceptions.EXIT_CODE
