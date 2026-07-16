"""Module to define and manipulate Selenium selectors."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Tuple, Protocol, List

from selenium.common.exceptions import (
    ElementNotInteractableException,
    InvalidElementStateException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from seleniumbase import SB
from seleniumbase.common.exceptions import (
    NoSuchElementException,
    ElementNotVisibleException,
    TimeoutException,
)
from seleniumbase.config import settings
from seleniumbase.fixtures import page_utils
from seleniumbase.undetected.webelement import WebElement

logger = logging.getLogger(__name__)


class ElementCheckError(Exception):
    pass


class InvalidByException(Exception):
    pass


class ElementWaiter(Protocol):
    def __call__(
        self, selector: str, by: str = "css selector", timeout: int | None = None
    ) -> None: ...


class ElementIs(Protocol):
    def __call__(self, selector: any, by: str = "css selector") -> bool: ...


@dataclass
class SeleniumSelector:
    selector: str
    by: str = field(default=By.CSS_SELECTOR)
    name: str | None = field(default=None)
    _web_element: WebElement | None = field(default=None)
    _taking_archive: bool = False
    _recalculated: bool = False
    _validated: bool = False

    def __post_init__(self) -> None:
        self.recalculate_selector()
        self._validate_by()

    def __str__(self) -> str:
        return self.name or self.selector

    def recalculate_selector(self) -> None:
        if self._recalculated:
            return
        self.selector, self.by = page_utils.recalculate_selector(self.by, self.selector)
        self._recalculated = True

    def _validate_by(self) -> None:
        if self._validated:
            return
        if self.by not in vars(By).values():
            raise InvalidByException(f"Invalid 'by' value: {self.by}")
        self._validated = True

    def get(self, addendum: str = "") -> Tuple[str, str]:
        return f"{self.selector}{addendum}", self.by

    def as_kwargs(self) -> Dict[str, str]:
        return {k: v for k, v in vars(self).items() if not k.startswith("_")}

    def as_core(self, addendum: str = "") -> Tuple[str, str]:
        return self.by, f"{self.selector}{addendum}"

    def _is_element_stale(self) -> bool:
        if not self._web_element:
            return True
        try:
            self._web_element.is_enabled()
            return False
        except StaleElementReferenceException:
            return True

    def find_element(
        self, sb: SB, subelement: "SeleniumSelector | None" = None
    ) -> WebElement:
        if not self._web_element or self._is_element_stale():
            self._web_element = sb.find_element(*self.get())
        if subelement:
            return self._web_element.find_element(*subelement.as_core())
        return self._web_element

    def find_elements(
        self, sb: SB, subelement: "SeleniumSelector | None" = None
    ) -> List[WebElement]:
        if subelement:
            return self.find_element(sb).find_elements(*subelement.as_core())
        return sb.find_elements(*self.get())

    def click(self, sb: SB) -> None:
        from selenium_utils.browser import wait_jquery

        if self.is_clickable(sb):
            self.find_element(sb).uc_click()
            wait_jquery(sb)
            return
        raise ElementNotInteractableException(f"{self} is not clickable")

    def click_silently(self, sb: SB) -> bool:
        try:
            self.click(sb)
            return True
        except Exception:
            return False

    def click_js(self, sb):
        """Forces a click via JavaScript DOM injection, bypassing overlays."""
        element = self.find_element(sb)
        sb.execute_script("arguments[0].click();", element)

    def text(self, sb: SB) -> str | None:
        return self.find_element(sb).text

    def get_attribute(self, sb: SB, attribute: str) -> str | None:
        return self.find_element(sb).get_attribute(attribute)

    def value(self, sb: SB) -> str | None:
        return self.get_attribute(sb, "value")

    def clear(self, sb: SB) -> None:
        self.find_element(sb).clear()

    def send_keys(self, sb: SB, value: str | int) -> None:
        from selenium_utils.browser import wait_jquery

        if isinstance(value, Keys):
            sb.send_keys(self.selector, value, self.by)
        else:
            sb.type(self.selector, value, self.by)
        wait_jquery(sb)

    def value_or_text(self, sb: SB) -> str | None:
        value = self.value(sb)
        return value if value else self.text(sb)

    def scroll_to(self, sb: SB) -> None:
        _ = self.find_element(sb).location_once_scrolled_into_view

    def archive(
        self, sb: SB, filename: str, highlight: "SeleniumSelector | None" = None
    ) -> tuple[Path, Path] | None:
        from selenium_utils.archive import element_archive

        if self._taking_archive:
            return None
        self._taking_archive = True
        try:
            return element_archive(sb, self.find_element(sb), filename, highlight)
        finally:
            self._taking_archive = False

    def _run_element_check(
        self,
        check_func: ElementWaiter | ElementIs,
        timeout: int = settings.SMALL_TIMEOUT,
    ) -> None:
        try:
            check_func(*self.get(), timeout=timeout)
        except Exception as e:
            if type(e).__name__ == "Exception":
                if "clickable" in str(e):
                    raise ElementNotInteractableException from e
                if "visible" in str(e):
                    raise ElementNotVisibleException from e
                if "present" in str(e):
                    raise NoSuchElementException from e
                if "enabled" in str(e):
                    raise InvalidElementStateException from e
            raise

    def _is_element_check(
        self,
        sb: SB,
        descriptor: str = None,
        check_func: ElementWaiter | ElementIs = None,
        timeout: int = settings.SMALL_TIMEOUT,
        archive_success: bool = True,
        archive_failed: bool = True,
    ) -> bool:
        if not descriptor:
            descriptor = str(self)
        if not check_func:
            check_func = sb.wait_for_element_present

        match check_func:
            case sb.wait_for_element_present:
                check_type = "PRESENT"
            case sb.wait_for_element_visible:
                check_type = "VISIBLE"
            case sb.is_element_enabled:
                check_type = "ENABLED"
            case sb.wait_for_element_clickable:
                check_type = "CLICKABLE"
            case _:
                raise ValueError("Invalid check_func")

        exception_to_type = {
            NoSuchElementException: "FOUND",
            ElementNotVisibleException: "VISIBLE",
            ElementNotInteractableException: "CLICKABLE",
            InvalidElementStateException: "ENABLED",
        }

        try:
            self._run_element_check(check_func, timeout)
            if archive_success:
                self.archive(sb, f"{descriptor}_{check_type}")
            return True
        except tuple(exception_to_type.keys()) as e:
            exc_type = exception_to_type[type(e)]
            if archive_failed:
                from selenium_utils.archive import full_page_archive

                full_page_archive(sb, f"{descriptor}_NOT_{exc_type}")
            return False
        except TimeoutException:
            if archive_failed:
                from selenium_utils.archive import full_page_archive

                full_page_archive(sb, f"{descriptor}_NOT_{check_type}")
            return False
        except Exception as e:
            if archive_failed:
                from selenium_utils.archive import full_page_archive

                full_page_archive(sb, f"{descriptor}_UNEXPECTED_EXCEPTION")
            raise ElementCheckError("UNEXPECTED EXCEPTION") from e

    def is_present(
        self,
        sb: SB,
        descriptor: str = None,
        timeout: int = settings.SMALL_TIMEOUT,
        archive_success: bool = True,
        archive_failed: bool = True,
    ) -> bool:
        return self._is_element_check(
            sb,
            descriptor,
            sb.wait_for_element_present,
            timeout,
            archive_success,
            archive_failed,
        )

    def is_visible(
        self,
        sb: SB,
        descriptor: str = None,
        timeout: int = settings.SMALL_TIMEOUT,
        archive_success: bool = True,
        archive_failed: bool = True,
    ) -> bool:
        return self._is_element_check(
            sb,
            descriptor,
            sb.wait_for_element_visible,
            timeout,
            archive_success,
            archive_failed,
        )

    def is_clickable(
        self,
        sb: SB,
        descriptor: str = None,
        timeout: int = settings.SMALL_TIMEOUT,
        archive_success: bool = True,
        archive_failed: bool = True,
    ) -> bool:
        return self._is_element_check(
            sb,
            descriptor,
            sb.wait_for_element_clickable,
            timeout,
            archive_success,
            archive_failed,
        )

    def is_enabled(
        self,
        sb: SB,
        descriptor: str = None,
        timeout: int = settings.SMALL_TIMEOUT,
        archive_success: bool = True,
        archive_failed: bool = True,
    ) -> bool:
        return self._is_element_check(
            sb,
            descriptor,
            sb.is_element_enabled,
            timeout,
            archive_success,
            archive_failed,
        )

    def hide(self, sb: SB, description: str = None) -> None:
        if not description:
            description = str(self)
        if not self.is_visible(
            sb, description, archive_success=False, archive_failed=False
        ):
            return
        self.find_element(sb)
        self.scroll_to(sb)
        try:
            sb.safe_execute_script(
                "arguments[0].style.display='none';", self._web_element
            )
        except Exception:
            pass


HTML_DOM = SeleniumSelector("html", By.TAG_NAME, "FULL PAGE SCREENSHOT")


def create_xpath_from_element(element: WebElement) -> str | None:
    try:
        tag_name = element.tag_name.lower()
        attributes = {
            name["name"]: name["value"] for name in element.get_property("attributes")
        }
        xpath_parts = [f"//{tag_name}"]
        attribute_parts = [f"@{k}='{v}'" for k, v in attributes.items() if k != "class"]
        if attribute_parts:
            xpath_parts.append(f"[{' and '.join(attribute_parts)}]")
        return "".join(xpath_parts)
    except Exception:
        return None


def is_valid_css_id(value: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z_][\w-]*", value))


def create_selector_for_parent_with_child_id(
    element: WebElement, name: str
) -> SeleniumSelector | None:
    try:
        children = element.find_elements(By.XPATH, ".//*[@id]")
        if not children:
            return None
        child_id = children[0].get_attribute("id")
        parent_tag = element.tag_name.lower()
        css = (
            f"{parent_tag}:has(#{child_id})"
            if is_valid_css_id(child_id)
            else f'{parent_tag}:has([id="{child_id}"])'
        )
        return SeleniumSelector(By.CSS_SELECTOR, css, name)
    except Exception:
        return None


def get_selenium_selector(sb: SB, element: WebElement, name: str) -> SeleniumSelector:
    element_id = element.get_attribute("id")
    if element_id:
        return SeleniumSelector(By.ID, element_id, name)
    temp = create_selector_for_parent_with_child_id(element, name)
    if temp and len(temp.find_elements(sb)) == 1:
        return temp
    element_classes = element.get_attribute("class").replace(" ", ".")
    if element_classes:
        temp = SeleniumSelector(
            By.CSS_SELECTOR, f"{element.tag_name}.{element_classes}", name
        )
        if len(temp.find_elements(sb)) == 1:
            return temp
    return SeleniumSelector(
        By.XPATH, create_xpath_from_element(element) or f"//{element.tag_name}", name
    )
