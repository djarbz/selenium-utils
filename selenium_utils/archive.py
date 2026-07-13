"""Module to handle archiving HTML source and screenshots."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from bs4 import BeautifulSoup, ParserRejectedMarkup
from selenium.common.exceptions import JavascriptException, StaleElementReferenceException
from seleniumbase import SB
from seleniumbase.common.exceptions import TimeoutException, WebDriverException
from seleniumbase.undetected.webelement import WebElement

from selenium_utils.config import WINDOW_WIDTH, WINDOW_HEIGHT, LOG_TRACE
from selenium_utils.misc import generate_clean_filename

if TYPE_CHECKING:
    from selenium_utils.selectors import SeleniumSelector

logger = logging.getLogger(__name__)

class ScreenshotError(Exception):
    """Custom exception for screenshot-related errors."""

class SaveSourceError(Exception):
    """Custom exception for save_source errors."""

class ElementSourceError(Exception):
    """Custom exception for element source related errors."""

def element_archive(sb: SB, element: WebElement, filename: str, highlight: "SeleniumSelector | None" = None) -> tuple[Path, Path]:
    try:
        source = element.get_attribute("outerHTML")
        if not source:
            raise ElementSourceError("Element outerHTML returned None or empty string.")
        source_pretty = BeautifulSoup(source, "html.parser").prettify()
        source_path = generate_clean_filename(filename, "html")
        logger.info("Saving HTML source to file: %s", source_path.resolve())
    except WebDriverException as e:
        raise ElementSourceError("Failed to get element outer HTML.") from e
    except ParserRejectedMarkup as e:
        raise ElementSourceError(f"Failed to pretty-format HTML: {e}") from e
    except Exception as e:
        raise ElementSourceError(f"Failed to save HTML source: {e}") from e

    try:
        with source_path.open("w", encoding="utf-8") as source_file:
            source_file.write(source_pretty)
    except Exception as e:
        raise SaveSourceError("Failed to save HTML source to file") from e

    try:
        image_path = element_screenshot(sb, element, filename, highlight)
    except WebDriverException as e:
        image_path = None
        logger.error("Failed to capture screenshot of the element [%s]: %s", filename, e)

    return source_path, image_path

def element_screenshot(sb: SB, element: WebElement, filename: str, highlight: "SeleniumSelector | None" = None) -> Path:
    logger.log(LOG_TRACE, "Taking a screenshot of %s", filename)
    try:
        _ = element.location_once_scrolled_into_view
        if highlight:
            sb.highlight(*highlight.get())
        image_path = generate_clean_filename(filename, "png")
        if not element.screenshot(str(image_path.resolve())):
            raise ScreenshotError(f"Failed to write screenshot to file: {image_path.resolve()}")
        logger.info("Screenshot Saved [%s]", image_path.resolve())
        return image_path
    except TimeoutException as e:
        raise ScreenshotError("Screenshot Timed Out") from e
    except Exception as e:
        raise ScreenshotError("Failed to take screenshot") from e

def full_page_archive(sb: SB, descriptor: str = None) -> tuple[Path, Path] | None:
    from selenium_utils.browser import wait_jquery
    from selenium_utils.selectors import HTML_DOM

    wait_jquery(sb)
    parsed_url = urlparse(sb.get_current_url())
    domain = parsed_url.netloc
    path = parsed_url.path.replace("/", ".").lstrip(".")
    filename_parts = [domain]
    if path and path != ".":
        filename_parts.append(path)
    filename = "-".join(filename_parts)
    if descriptor:
        filename = f"{descriptor}-{filename}"

    try:
        full_width = sb.driver.execute_script("return document.body.parentNode.scrollWidth")
        full_height = sb.driver.execute_script("return document.body.parentNode.scrollHeight")
        sb.set_window_size(full_width, full_height)
    except JavascriptException as e:
        logger.exception("Failed to Maximize browser window: %s", e)

    try:
        return HTML_DOM.archive(sb, filename)
    except StaleElementReferenceException as e:
        logger.exception("Failed to get full page screenshot: %s", e)
        return None
    finally:
        sb.set_window_size(WINDOW_WIDTH, WINDOW_HEIGHT)
