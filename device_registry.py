"""Хранилище устройств Sber MQTT.

Устройства сохраняются в файл .storage/sber_mqtt_devices через
стандартный механизм Home Assistant (helpers.storage.Store).
Данные переживают перезапуски HA.

Структура одного устройства:
{
    "id":          "мой_relay",           # Уникальный ID в Сбере (slug)
    "name":        "Свет в гостиной",     # Отображаемое имя
    "room":        "Гостиная",            # Комната (опционально)
    "device_type": "relay",               # Тип: relay | sensor_temp
    "attributes":  {                      # Зависит от типа:
        # Для relay:
        "entity_id":   "switch.light",    #   Привязанная сущность HA
        "entity_name": "Свет",            #   Имя сущности
        # Для sensor_temp:
        "temperature_entity": "sensor.temp",
        "humidity_entity":    "sensor.hum",
        "battery_entity":     "sensor.bat",   # опционально
        "signal_entity":      "sensor.sig",   # опционально
    },
    "last_state":  {}                     # Последнее отправленное состояние (кэш)
}
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


class SberDeviceRegistry:
    """Управляет списком устройств: загрузка, сохранение, CRUD-операции."""

    def __init__(self, hass: HomeAssistant) -> None:
        # Store — обёртка HA для работы с .storage/
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        # Словарь device_id → данные устройства (в памяти)
        self._devices: dict[str, Any] = {}

    @property
    def devices(self) -> dict[str, Any]:
        """Возвращает словарь всех устройств {device_id: device_data}."""
        return self._devices

    # ── Загрузка и сохранение ──────────────────────────────────────────────

    async def async_load(self) -> None:
        """Загружает устройства из .storage/ при старте интеграции.

        Поддерживает два формата хранилища:
        - Новый: {"devices": [{"id": "...", "name": "...", ...}, ...]}
        - Старый: {"devices": {"device_id": {...}, ...}}  (dict вместо list)
        """
        data = await self._store.async_load()
        if not data or "devices" not in data:
            self._devices = {}
            _LOGGER.info("Хранилище устройств пустое — начинаем с чистого листа")
            return

        raw = data["devices"]

        if isinstance(raw, dict):
            # Старый формат: словарь {device_id: device_data}
            _LOGGER.info("Хранилище в старом формате (dict) — конвертируем")
            self._devices = raw
        elif isinstance(raw, list):
            # Новый формат: список устройств
            result = {}
            for item in raw:
                if isinstance(item, dict) and "id" in item:
                    result[item["id"]] = item
                else:
                    _LOGGER.warning("Пропускаем некорректную запись в хранилище: %r", item)
            self._devices = result
        else:
            _LOGGER.error("Неизвестный формат хранилища: %r — сбрасываем", type(raw))
            self._devices = {}

        _LOGGER.info("Загружено %d устройств из хранилища", len(self._devices))

    async def async_save(self) -> None:
        """Сохраняет текущий список устройств в .storage/."""
        await self._store.async_save({"devices": list(self._devices.values())})
        _LOGGER.debug("Сохранено %d устройств в хранилище", len(self._devices))

    # ── CRUD операции ──────────────────────────────────────────────────────

    async def async_add_device(self, device: dict) -> None:
        """Добавляет новое устройство и сохраняет хранилище."""
        device_id = device["id"]
        self._devices[device_id] = device
        await self.async_save()
        _LOGGER.info("Добавлено устройство Sber: %s (%s)", device_id, device.get("name"))

    async def async_remove_device(self, device_id: str) -> bool:
        """Удаляет устройство по ID. Возвращает True если устройство было найдено."""
        if device_id not in self._devices:
            return False
        del self._devices[device_id]
        await self.async_save()
        _LOGGER.info("Удалено устройство Sber: %s", device_id)
        return True

    async def async_update_last_state(self, device_id: str, state: dict) -> None:
        """Обновляет кэш последнего отправленного состояния устройства.

        Используется state_tracker для хранения последнего отправленного
        значения — чтобы не отправлять дубликаты при одинаковом состоянии.
        """
        if device_id not in self._devices:
            return
        self._devices[device_id]["last_state"] = state
        await self.async_save()

    def get_device(self, device_id: str) -> dict | None:
        """Возвращает устройство по ID или None если не найдено."""
        return self._devices.get(device_id)

    def device_exists(self, device_id: str) -> bool:
        """Проверяет существование устройства по ID."""
        return device_id in self._devices

    def get_all_as_list(self) -> list[dict]:
        """Возвращает все устройства в виде списка (для API)."""
        return list(self._devices.values())

    def get_devices_by_ha_entity(self, entity_id: str) -> list[dict]:
        """Находит все устройства привязанные к заданной сущности HA.

        Используется для поиска устройства по entity_id при изменении состояния.
        """
        result = []
        for device in self._devices.values():
            attrs = device.get("attributes", {})
            # Проверяем все поля атрибутов на совпадение с entity_id
            if entity_id in attrs.values():
                result.append(device)
        return result
