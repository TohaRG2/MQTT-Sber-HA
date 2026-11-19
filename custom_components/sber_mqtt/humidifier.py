"""Увлажнитель воздуха (hvac_humidifier): скорость вентилятора и сущности HA.

В HA увлажнитель — это сущность домена ``humidifier``. Включение, влажность
и режим берутся из неё. Но у части моделей скорость вентилятора вынесена в
отдельную сущность (``number``/``input_number`` «Интенсивность» или
``select``/``input_select``), поэтому пользователь может сопоставить функции
Сбера ``hvac_air_flow_power`` отдельную сущность и её значения.

Модуль не зависит от MQTT: только чтение состояний HA и преобразование
значений Сбера ↔ HA.
"""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import (
    HUMIDIFIER_MODE_ALIASES,
    HUMIDIFIER_NUMBER_DOMAINS,
    HUMIDIFIER_SPEED_VALUES,
    SBER_AIR_FLOW_TO_HA_MODE,
)

_NO_VALUE = ("unavailable", "unknown", "")


def domain_of(entity_id: str) -> str:
    return entity_id.split(".", 1)[0] if entity_id else ""


def clean_speed_map(attrs: dict) -> dict[str, str]:
    """{значение Сбера: опция select или число} — только корректные пары."""
    raw = attrs.get("speed_map") or {}
    if not isinstance(raw, dict):
        return {}
    return {
        k: str(v) for k, v in raw.items()
        if k in HUMIDIFIER_SPEED_VALUES and v not in (None, "")
    }


def speed_domain(attrs: dict) -> str:
    return domain_of(attrs.get("speed_entity", ""))


def is_numeric_speed(attrs: dict) -> bool:
    return speed_domain(attrs) in HUMIDIFIER_NUMBER_DOMAINS


def watched_entities(attrs: dict) -> set[str]:
    """Все сущности HA, изменения которых влияют на состояние увлажнителя."""
    return {
        attrs[key]
        for key in (
            "entity_id",
            "water_percentage_entity",
            "replace_filter_entity",
            "speed_entity",
        )
        if attrs.get(key)
    }


def mode_to_sber(mode) -> str | None:
    """Режим humidifier (например ``boost``) → каноническая скорость Сбера."""
    if mode is None:
        return None
    value = str(mode).strip().casefold()
    if not value:
        return None
    if value in HUMIDIFIER_SPEED_VALUES:
        return value
    for sber, aliases in HUMIDIFIER_MODE_ALIASES.items():
        if value in aliases:
            return sber
    return None


def declared_speed_values(attrs: dict) -> list[str]:
    """Скорости Сбера, которые нужно объявить в модели устройства.

    Приоритет:
      1. явно настроенная сущность скорости (speed_entity + speed_map);
      2. режимы humidifier, сохранённые при добавлении (available_modes);
      3. для старых записей без этих данных — полный набор, чтобы не
         сломать уже работающие устройства.
    """
    smap = clean_speed_map(attrs)
    if attrs.get("speed_entity") and smap:
        return [v for v in HUMIDIFIER_SPEED_VALUES if v in smap]

    if "available_modes" in attrs:
        mapped = {mode_to_sber(m) for m in (attrs.get("available_modes") or [])}
        return [v for v in HUMIDIFIER_SPEED_VALUES if v in mapped]

    return list(HUMIDIFIER_SPEED_VALUES)


def speed_state(hass: HomeAssistant, attrs: dict) -> str | None:
    """Текущая скорость в терминах Сбера (None — не определена).

    Если настроена отдельная сущность скорости — читаем её. Иначе берём
    атрибут ``mode`` самой сущности humidifier и переводим в скорость Сбера
    (``boost`` → ``turbo`` и т.п.).
    """
    entity_id = attrs.get("speed_entity")
    smap = clean_speed_map(attrs)
    if entity_id and smap:
        state = hass.states.get(entity_id)
        if state is None or state.state in _NO_VALUE:
            return None

        if domain_of(entity_id) in HUMIDIFIER_NUMBER_DOMAINS:
            try:
                current = float(state.state)
            except (ValueError, TypeError):
                return None
            for sber in HUMIDIFIER_SPEED_VALUES:
                target = smap.get(sber)
                if target is None:
                    continue
                try:
                    if abs(current - float(target)) < 1e-6:
                        return sber
                except (ValueError, TypeError):
                    continue
            return None

        for sber in HUMIDIFIER_SPEED_VALUES:
            option = smap.get(sber)
            if option is not None and option == state.state:
                return sber
        current = state.state.casefold()
        for sber in HUMIDIFIER_SPEED_VALUES:
            option = smap.get(sber)
            if option is not None and option.casefold() == current:
                return sber
        return None

    state = hass.states.get(attrs.get("entity_id", ""))
    if state is None:
        return None
    return mode_to_sber(state.attributes.get("mode"))


def sber_to_mode(sber: str, available_modes: list | None = None) -> str | None:
    """Скорость Сбера → значение для ``humidifier.set_mode``.

    Учитывает реальные режимы устройства: ``turbo`` превращается в ``boost``,
    если в ``available_modes`` есть ``boost``, и т.п.
    """
    default = SBER_AIR_FLOW_TO_HA_MODE.get(sber)
    modes = [str(m) for m in (available_modes or [])]
    if not modes:
        return default

    candidates = [default, sber, *HUMIDIFIER_MODE_ALIASES.get(sber, ())]
    for candidate in candidates:
        if candidate and candidate in modes:
            return candidate

    by_lower = {m.casefold(): m for m in modes}
    for candidate in candidates:
        if candidate and candidate.casefold() in by_lower:
            return by_lower[candidate.casefold()]
    return default
