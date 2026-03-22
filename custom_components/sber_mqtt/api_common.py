"""Общие вспомогательные функции для API views."""
from __future__ import annotations

import logging
import re
import unicodedata

from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _get_entry_data(hass: HomeAssistant) -> dict | None:
    """Находит данные активной записи интеграции в hass.data.

    Возвращает словарь с ключами: mqtt_client, device_registry,
    serializer, state_tracker, config — или None если интеграция не загружена.
    """
    for val in hass.data.get(DOMAIN, {}).values():
        if isinstance(val, dict) and "mqtt_client" in val:
            return val
    return None


def _slugify(text: str) -> str:
    """Преобразует произвольный текст в допустимый ASCII идентификатор.

    Пример: "Свет в гостиной" → "svet_v_gostinoi"
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text or "device"
