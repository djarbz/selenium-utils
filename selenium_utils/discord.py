"""Module to provide notification via Discord Webhook."""

import logging
import os
import re
import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Protocol, Union

from discord_webhook import DiscordWebhook, DiscordEmbed
from selenium_utils.config import LOG_NOTICE, LOG_TRACE
from selenium_utils.misc import validate_url

logger = logging.getLogger(__name__)

_web_hook: DiscordWebhook | None = None  # pylint: disable=invalid-name
_web_hook_url: str | None = None  # pylint: disable=invalid-name

class WebhookError(Exception):
    """Custom exception for Webhook errors."""

class WebhookConfigError(Exception):
    """Custom exception for Webhook configuration errors."""

class ImageSetter(Protocol):
    def __call__(self, url: str, **kwargs: Union[str, int]) -> None: ...

def is_valid_hex_color(color: str) -> bool:
    if not isinstance(color, str):
        return False
    return bool(re.fullmatch(r"[0-9a-fA-F]{6}", color))

@dataclass
class WebhookConfig:
    title: str
    description: str = None
    color: str = "03b2f8"
    clear: bool = True
    image_filepath: Path = None
    thumbnail_filepath: Path = None
    additional_fields: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        self._validate()

    def _validate(self) -> None:
        if not isinstance(self.title, str):
            raise WebhookConfigError("Title field expects a string")
        if self.description is not None and not isinstance(self.description, str):
            raise WebhookConfigError("Description field expects a string or None")
        if not is_valid_hex_color(self.color):
            raise WebhookConfigError(f"Invalid hex color: {self.color}")

def init_webhook() -> None:
    global _web_hook, _web_hook_url
    _web_hook_url = os.environ.get("APP_DISCORD_WEBHOOK_URL", "")
    logger.info("Preparing Discord Webhook: %s", _web_hook_url)
    try:
        validate_url(_web_hook_url)
        _web_hook = DiscordWebhook(url=_web_hook_url)
        logger.log(LOG_NOTICE, "Discord Webhook configured!")
    except ValueError as e:
        logger.error("Invalid Discord Webhook URL: %s", _web_hook_url)
        _web_hook = None

def send_webhook(config: WebhookConfig, **kwargs: Any) -> None:
    if _web_hook is None:
        init_webhook()
    if _web_hook is None:
        return
    try:
        if config.clear:
            _clear_webhook_state()

        embed = _create_embed(config)
        _add_files_to_embed(embed, config.image_filepath, config.thumbnail_filepath)
        _add_fields_to_embed(embed, **{"Host": socket.getfqdn()})
        _add_fields_to_embed(embed, **config.additional_fields)
        _add_fields_to_embed(embed, **kwargs)
        _check_field_limits(embed)

        _web_hook.add_embed(embed)
        response = _web_hook.execute(remove_embeds=True)
        _log_webhook_response(response)
    except Exception as e:
        raise WebhookError("Sending webhook failed.") from e
    finally:
        _clear_webhook_state()

def _clear_webhook_state() -> None:
    if _web_hook:
        try:
            _web_hook.remove_embeds()
            _web_hook.remove_files()
        except Exception as e:
            raise WebhookError("Clearing Webhook State FAILED.") from e

def _create_embed(config: WebhookConfig) -> DiscordEmbed:
    app_name = os.environ.get("APP_NAME", "Selenium Bot")
    title = _truncate_string(config.title, 256, "Discord title")
    embed = DiscordEmbed(title=title)
    if config.description:
        embed.set_description(_truncate_string(config.description, 2048, "Discord description"))
    if config.color and is_valid_hex_color(config.color):
        embed.set_color(config.color)
    embed.set_author(name=f"{app_name} Automation")
    embed.set_timestamp()
    return embed

def _add_files_to_embed(embed: DiscordEmbed, image_filepath: Path = None, thumbnail_filepath: Path = None) -> None:
    for filepath, method in [(image_filepath, embed.set_image), (thumbnail_filepath, embed.set_thumbnail)]:
        if filepath and filepath.is_file():
            file = _add_file_to_webhook(filepath)
            if file:
                method(url=f"attachment://{file}")

def _add_file_to_webhook(filepath: Path) -> str | None:
    try:
        with filepath.open("rb") as file:
            _web_hook.add_file(file=file.read(), filename=filepath.name)
        return filepath.name
    except Exception as e:
        logger.exception("Adding file FAILED: %s", e)
        return None

def _truncate_string(text: str, max_length: int, error_name: str) -> str:
    if len(text) > max_length:
        return text[:max_length]
    return text

def _add_fields_to_embed(embed: DiscordEmbed, **kwargs: Any) -> None:
    for key, value in kwargs.items():
        try:
            key = _truncate_string(str(key), 256, "field name")
            value = _truncate_string(str(value), 1024, "field value")
            embed.add_embed_field(name=key, value=value, inline=False)
        except Exception:
            pass

def _check_field_limits(embed: DiscordEmbed) -> None:
    fields = embed.get_embed_fields()
    while len(fields) > 25:
        embed.delete_embed_field(len(fields) - 1)
        fields = embed.get_embed_fields()

def _log_webhook_response(response):
    if response.status_code == 200:
        logger.info("Webhook sent successfully!")
    else:
        logger.warning("Webhook failed with status code %s", response.status_code)
