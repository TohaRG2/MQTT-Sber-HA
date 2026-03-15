"""Отслеживание изменений состояний HA и отправка обновлений в Сбер.

Логика работы:
1. При старте (или после добавления/удаления устройства) вызывается refresh()
2. Собирается список всех entity_id привязанных к устройствам
3. Подписываемся на изменения этих сущностей через async_track_state_change_event
4. При изменении состояния — формируем payload и отправляем в Сбер
5. Для защиты от дублей: сравниваем новое значение с last_state

Типы устройств:
- relay (switch, light, input_boolean): отслеживаем on/off
- relay (script, button, input_button): НЕ отслеживаем (нет состояния)
- sensor_temp: отслеживаем все 4 слота (temp, humidity, battery, signal)
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    DEVICE_TYPE_RELAY,
    DEVICE_TYPE_SENSOR_TEMP,
    DEVICE_TYPE_SCENARIO_BUTTON,
    DEVICE_TYPE_HVAC_AC,
    DEVICE_TYPE_VACUUM,
    DEVICE_TYPE_VALVE,
    DEVICE_TYPE_LIGHT,
    DEVICE_TYPE_COVER,
    DEVICE_TYPE_WATER_LEAK,
    DEVICE_TYPE_HUMIDIFIER,
    DEVICE_TYPE_SOCKET,
    DEVICE_TYPE_SMOKE,
    DEVICE_TYPE_KETTLE,
    RELAY_STATEFUL_DOMAINS,
    RELAY_BUTTON_DOMAINS,
    SCENARIO_BUTTON_STATEFUL_DOMAINS,
    SCENARIO_BUTTON_PUSH_DOMAINS,
)

_LOGGER = logging.getLogger(__name__)


class StateTracker:
    """Подписывается на изменения сущностей HA и публикует состояния в Сбер."""

    def __init__(
        self,
        hass: HomeAssistant,
        serializer,
        publish_status_fn: Callable[[str], None],
        get_devices_fn: Callable[[], dict],
        update_last_state_fn: Callable,
    ) -> None:
        self._hass              = hass
        self._serializer        = serializer
        self._publish_status    = publish_status_fn      # функция отправки в MQTT
        self._get_devices       = get_devices_fn         # получить текущий список устройств
        self._update_last_state = update_last_state_fn   # сохранить последнее состояние

        # Функция отмены подписки (возвращается async_track_state_change_event)
        self._unsubscribe: Callable | None = None

    def start(self) -> None:
        """Запускает отслеживание — подписывается на изменения сущностей."""
        self.refresh()

    def stop(self) -> None:
        """Останавливает отслеживание — отменяет все подписки."""
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    def refresh(self) -> None:
        """Пересобирает список отслеживаемых сущностей.

        Вызывается при добавлении или удалении устройства,
        чтобы подписки были актуальными.
        """
        # Сначала отменяем старые подписки
        self.stop()

        # Собираем entity_id всех сущностей которые нужно отслеживать
        watched: set[str] = set()
        devices = self._get_devices()

        for device in devices.values():
            device_type = device.get("device_type")
            attrs       = device.get("attributes", {})

            if device_type == DEVICE_TYPE_RELAY:
                entity_id = attrs.get("entity_id", "")
                domain    = entity_id.split(".")[0] if entity_id else ""
                if domain in RELAY_STATEFUL_DOMAINS:
                    watched.add(entity_id)

            elif device_type == DEVICE_TYPE_SENSOR_TEMP:
                # Отслеживаем все заполненные слоты датчика
                for key in ("temperature_entity", "humidity_entity", "battery_entity"):
                    eid = attrs.get(key)
                    if eid:
                        watched.add(eid)

            elif device_type == DEVICE_TYPE_SCENARIO_BUTTON:
                entity_id = attrs.get("entity_id", "")
                domain    = entity_id.split(".")[0] if entity_id else ""
                # Кнопки/сценарии отслеживаем через их специфическое состояние
                # Для доменов со статусом (switch, light и т.д.) — следим за on/off
                # Для push-доменов (button, input_button, script) — следим за last_triggered/state
                if entity_id:
                    watched.add(entity_id)

            elif device_type == DEVICE_TYPE_HVAC_AC:
                # Отслеживаем climate-сущность и опциональный датчик температуры
                entity_id = attrs.get("entity_id", "")
                if entity_id:
                    watched.add(entity_id)
                temp_entity = attrs.get("temperature_entity", "")
                if temp_entity:
                    watched.add(temp_entity)

            elif device_type == DEVICE_TYPE_VACUUM:
                # Отслеживаем vacuum-сущность и опциональный датчик батареи
                entity_id = attrs.get("entity_id", "")
                if entity_id:
                    watched.add(entity_id)
                battery_entity = attrs.get("battery_entity", "")
                if battery_entity:
                    watched.add(battery_entity)

            elif device_type == DEVICE_TYPE_VALVE:
                entity_id = attrs.get("entity_id", "")
                if entity_id:
                    watched.add(entity_id)

            elif device_type == DEVICE_TYPE_LIGHT:
                entity_id = attrs.get("entity_id", "")
                if entity_id:
                    watched.add(entity_id)

            elif device_type == DEVICE_TYPE_COVER:
                entity_id = attrs.get("entity_id", "")
                if entity_id:
                    watched.add(entity_id)
                battery_entity = attrs.get("battery_entity", "")
                if battery_entity:
                    watched.add(battery_entity)

            elif device_type == DEVICE_TYPE_WATER_LEAK:
                entity_id = attrs.get("entity_id", "")
                if entity_id:
                    watched.add(entity_id)
                battery_entity = attrs.get("battery_entity", "")
                if battery_entity:
                    watched.add(battery_entity)

            elif device_type == DEVICE_TYPE_HUMIDIFIER:
                entity_id = attrs.get("entity_id", "")
                if entity_id:
                    watched.add(entity_id)
                for key in ("water_percentage_entity", "replace_filter_entity"):
                    if attrs.get(key):
                        watched.add(attrs[key])

            elif device_type == DEVICE_TYPE_SOCKET:
                entity_id = attrs.get("entity_id", "")
                if entity_id:
                    watched.add(entity_id)
                for key in ("power_entity", "current_entity", "voltage_entity"):
                    if attrs.get(key):
                        watched.add(attrs[key])

            elif device_type == DEVICE_TYPE_SMOKE:
                entity_id = attrs.get("entity_id", "")
                if entity_id:
                    watched.add(entity_id)
                for key in ("battery_entity", "alarm_mute_entity"):
                    if attrs.get(key):
                        watched.add(attrs[key])

            elif device_type == DEVICE_TYPE_KETTLE:
                entity_id = attrs.get("entity_id", "")
                if entity_id:
                    watched.add(entity_id)

        if not watched:
            _LOGGER.debug("Нет сущностей для отслеживания")
            return

        _LOGGER.debug("Отслеживаем %d сущностей HA для Сбера", len(watched))

        # Подписываемся на изменения всех собранных сущностей
        self._unsubscribe = async_track_state_change_event(
            self._hass,
            list(watched),
            self._handle_state_change,
        )

    @callback
    def _handle_state_change(self, event: Event) -> None:
        """Обработчик изменения состояния сущности HA.

        Вызывается в event loop HA при изменении состояния любой
        из отслеживаемых сущностей.
        """
        entity_id = event.data.get("entity_id", "")
        new_state  = event.data.get("new_state")

        if new_state is None or new_state.state in ("unavailable", "unknown"):
            # Игнорируем недоступные состояния
            return

        # Находим все устройства Сбера привязанные к этой сущности
        devices = self._get_devices()
        for device_id, device in devices.items():
            self._process_device_state_change(device_id, device, entity_id, new_state)

    def _process_device_state_change(
        self, device_id: str, device: dict, changed_entity_id: str, new_state
    ) -> None:
        """Проверяет принадлежность changed_entity_id к устройству,
        формирует payload через state_builder и публикует в Сбер.
        """
        import json as _json
        from .state_builder import build_current_state_payload

        device_type = device.get("device_type")
        attrs       = device.get("attributes", {})

        # ── Определяем набор сущностей этого устройства ──────────────────
        if device_type == DEVICE_TYPE_RELAY:
            watched = {attrs.get("entity_id", "")}

        elif device_type == DEVICE_TYPE_SCENARIO_BUTTON:
            watched = {attrs.get("entity_id", "")}

        elif device_type == DEVICE_TYPE_HVAC_AC:
            watched = {attrs.get("entity_id", ""), attrs.get("temperature_entity", "")}

        elif device_type == DEVICE_TYPE_VACUUM:
            watched = {attrs.get("entity_id", ""), attrs.get("battery_entity", "")}

        elif device_type == DEVICE_TYPE_VALVE:
            watched = {attrs.get("entity_id", "")}

        elif device_type == DEVICE_TYPE_LIGHT:
            watched = {attrs.get("entity_id", "")}

        elif device_type == DEVICE_TYPE_COVER:
            watched = {attrs.get("entity_id", ""), attrs.get("battery_entity", "")}

        elif device_type == DEVICE_TYPE_WATER_LEAK:
            watched = {attrs.get("entity_id", ""), attrs.get("battery_entity", "")}

        elif device_type == DEVICE_TYPE_SMOKE:
            watched = {
                attrs.get("entity_id", ""),
                attrs.get("battery_entity", ""),
                attrs.get("alarm_mute_entity", ""),
            }

        elif device_type == DEVICE_TYPE_HUMIDIFIER:
            watched = {
                attrs.get("entity_id", ""),
                attrs.get("water_percentage_entity", ""),
                attrs.get("replace_filter_entity", ""),
            }

        elif device_type == DEVICE_TYPE_SOCKET:
            watched = {
                attrs.get("entity_id", ""),
                attrs.get("power_entity", ""),
                attrs.get("current_entity", ""),
                attrs.get("voltage_entity", ""),
            }

        elif device_type == DEVICE_TYPE_SENSOR_TEMP:
            watched = {
                attrs.get("temperature_entity", ""),
                attrs.get("humidity_entity", ""),
                attrs.get("battery_entity", ""),
            }

        elif device_type == DEVICE_TYPE_KETTLE:
            watched = {attrs.get("entity_id", "")}

        else:
            return

        # Убираем пустые строки и проверяем принадлежность
        watched -= {""}
        if changed_entity_id not in watched:
            return

        # ── Для реле — дедупликация по last_state ────────────────────────
        if device_type == DEVICE_TYPE_RELAY:
            relay_state = self._hass.states.get(attrs.get("entity_id", ""))
            if relay_state is None:
                return
            bound_entity = attrs.get("entity_id", "")
            is_on = (relay_state.state != "off") if bound_entity.startswith("media_player.") else (relay_state.state == "on")
            last = device.get("last_state", {})
            for s in last.get("states", []):
                if s.get("key") == "on_off" and s.get("value", {}).get("bool_value") == is_on:
                    return  # состояние не изменилось

        # ── Сценарная кнопка — button_event только при реальном срабатывании ──
        if device_type == DEVICE_TYPE_SCENARIO_BUTTON:
            entity_id = attrs.get("entity_id", "")
            domain    = entity_id.split(".")[0] if entity_id else ""

            if domain in SCENARIO_BUTTON_PUSH_DOMAINS:
                # button/input_button/script — любое изменение = click
                payload = self._serializer.build_scenario_button_event_payload(device_id, "click")
            elif domain in SCENARIO_BUTTON_STATEFUL_DOMAINS:
                # switch/light/etc — click при включении, double_click при выключении
                state = self._hass.states.get(entity_id)
                if state is None:
                    return
                is_on = (state.state != "off") if domain == "media_player" else (state.state == "on")
                from .const import SCENARIO_BUTTON_CLICK, SCENARIO_BUTTON_DOUBLE_CLICK
                event   = SCENARIO_BUTTON_CLICK if is_on else SCENARIO_BUTTON_DOUBLE_CLICK
                payload = self._serializer.build_scenario_button_event_payload(device_id, event)
            else:
                return

            _LOGGER.debug("StateTracker %s (scenario_button): button_event", device_id)
            self._publish_status(payload)
            self._hass.async_create_task(
                self._update_last_state(device_id, _json.loads(payload)["devices"][device_id])
            )
            return

        # ── Формируем payload через state_builder ────────────────────────
        payload = build_current_state_payload(self._hass, device_id, device, self._serializer)
        if not payload:
            return

        _LOGGER.debug("StateTracker %s (%s): публикуем состояние", device_id, device_type)
        self._publish_status(payload)

        self._hass.async_create_task(
            self._update_last_state(device_id, _json.loads(payload)["devices"][device_id])
        )
