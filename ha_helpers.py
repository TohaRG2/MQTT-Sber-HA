"""Вспомогательные функции для работы с реестрами сущностей и комнат HA.

Используется в API views для формирования списков сущностей
которые пользователь может выбрать при добавлении устройства в панели.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)

_LOGGER = logging.getLogger(__name__)

# Домены HA которые можно привязать как реле
RELAY_DOMAINS = ["switch", "input_boolean", "script", "button", "input_button", "light"]

# Домены для датчиков (только sensor)
SENSOR_TEMP_DOMAINS = ["sensor"]


def get_area_name(hass: HomeAssistant, entity_entry: er.RegistryEntry) -> str:
    """Возвращает название комнаты для сущности.

    Приоритет:
    1. Комната назначенная непосредственно сущности
    2. Комната устройства которому принадлежит сущность
    3. Пустая строка если комната не назначена
    """
    area_reg = ar.async_get(hass)

    # Сначала проверяем комнату самой сущности
    if entity_entry.area_id:
        area = area_reg.async_get_area(entity_entry.area_id)
        if area:
            return area.name

    # Если у сущности нет комнаты — берём комнату её устройства
    if entity_entry.device_id:
        device_reg = dr.async_get(hass)
        device = device_reg.async_get(entity_entry.device_id)
        if device and device.area_id:
            area = area_reg.async_get_area(device.area_id)
            if area:
                return area.name

    return ""


def get_entities_for_relay(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Возвращает список сущностей HA подходящих для привязки как реле.

    Фильтрует по доменам RELAY_DOMAINS, исключает отключённые сущности.
    Каждый элемент: {entity_id, domain, friendly_name, area}
    Список отсортирован по комнате и имени.
    """
    entity_reg = er.async_get(hass)
    result = []

    for entry in entity_reg.entities.values():
        domain = entry.domain

        # Только поддерживаемые домены
        if domain not in RELAY_DOMAINS:
            continue

        # Пропускаем отключённые сущности
        if entry.disabled_by:
            continue

        # Получаем отображаемое имя (приоритет: state > entry.name > entity_id)
        state = hass.states.get(entry.entity_id)
        if state:
            friendly_name = state.attributes.get("friendly_name", entry.entity_id)
        elif entry.name:
            friendly_name = entry.name
        else:
            friendly_name = entry.entity_id

        area = get_area_name(hass, entry)

        result.append({
            "entity_id":     entry.entity_id,
            "domain":        domain,
            "friendly_name": friendly_name,
            "area":          area,
        })

    # Сортируем: сначала по комнате, потом по имени
    result.sort(key=lambda x: (x["area"], x["friendly_name"]))
    return result


def get_sensor_entities(hass: HomeAssistant, device_classes: list[str]) -> list[dict[str, Any]]:
    """Возвращает сенсоры HA отфильтрованные по device_class.

    Используется для выбора датчиков температуры, влажности, батареи и сигнала.
    Каждый элемент: {entity_id, domain, friendly_name, area, device_class}

    device_classes — список допустимых классов, например:
    ["temperature", "humidity", "battery", "signal_strength"]
    """
    entity_reg = er.async_get(hass)
    result = []

    for entry in entity_reg.entities.values():
        # Только сенсоры
        if entry.domain != "sensor":
            continue

        # Пропускаем отключённые
        if entry.disabled_by:
            continue

        # Определяем device_class: приоритет original_device_class > device_class > state
        dc = ""
        if entry.original_device_class:
            dc = entry.original_device_class
        elif entry.device_class:
            dc = entry.device_class
        else:
            state = hass.states.get(entry.entity_id)
            if state:
                dc = state.attributes.get("device_class", "")

        # Фильтруем по запрошенным классам
        if dc not in device_classes:
            continue

        state = hass.states.get(entry.entity_id)
        if state:
            friendly_name = state.attributes.get("friendly_name", entry.entity_id)
        elif entry.name:
            friendly_name = entry.name
        else:
            friendly_name = entry.entity_id

        area = get_area_name(hass, entry)

        result.append({
            "entity_id":     entry.entity_id,
            "domain":        "sensor",
            "friendly_name": friendly_name,
            "area":          area,
            "device_class":  dc,
        })

    result.sort(key=lambda x: (x["area"], x["friendly_name"]))
    return result


def get_entity_info(hass: HomeAssistant, entity_id: str) -> dict[str, Any]:
    """Возвращает имя и комнату для произвольного entity_id.

    Используется при сохранении устройства — чтобы автоматически
    заполнить имя и комнату из данных HA.
    """
    entity_reg = er.async_get(hass)
    entry = entity_reg.async_get(entity_id)

    if not entry:
        # Сущность не в реестре — берём из state если есть
        state = hass.states.get(entity_id)
        friendly_name = state.attributes.get("friendly_name", entity_id) if state else ""
        return {"friendly_name": friendly_name, "area": ""}

    state = hass.states.get(entity_id)
    if state:
        friendly_name = state.attributes.get("friendly_name", entity_id)
    elif entry.name:
        friendly_name = entry.name
    else:
        friendly_name = entity_id

    area = get_area_name(hass, entry)
    return {"friendly_name": friendly_name, "area": area}
