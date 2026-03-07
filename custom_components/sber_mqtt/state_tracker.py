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

from .const import DEVICE_TYPE_RELAY, DEVICE_TYPE_SENSOR_TEMP, RELAY_STATEFUL_DOMAINS, RELAY_BUTTON_DOMAINS

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
                # Кнопки и сценарии не имеют состояния — не отслеживаем
                if domain in RELAY_STATEFUL_DOMAINS:
                    watched.add(entity_id)

            elif device_type == DEVICE_TYPE_SENSOR_TEMP:
                # Отслеживаем все заполненные слоты датчика
                for key in ("temperature_entity", "humidity_entity", "battery_entity", "signal_entity"):
                    eid = attrs.get(key)
                    if eid:
                        watched.add(eid)

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
        """Обрабатывает изменение состояния для конкретного устройства."""
        device_type = device.get("device_type")
        attrs       = device.get("attributes", {})

        if device_type == DEVICE_TYPE_RELAY:
            bound_entity = attrs.get("entity_id", "")
            if bound_entity != changed_entity_id:
                return  # изменилась не наша сущность

            # Определяем новое значение on/off
            is_on = new_state.state == "on"

            # Проверка на дубль: не отправляем если состояние не изменилось.
            # last_state теперь хранит {"states": [{"key": "on_off", "value": {...}}]}
            last = device.get("last_state", {})
            last_on_off = None
            for s in last.get("states", []):
                if s.get("key") == "on_off":
                    last_on_off = s.get("value", {}).get("bool_value")
                    break
            if last_on_off == is_on:
                return

            _LOGGER.debug(
                "Relay %s: изменение состояния %s → %s",
                device_id,
                "on" if last_on_off else "off",
                "on" if is_on else "off",
            )

            # Публикуем новое состояние в Сбер
            payload = self._serializer.build_relay_state_payload(device_id, is_on)
            self._publish_status(payload)

            # Сохраняем полный отправленный payload как last_state
            import json as _json
            self._hass.async_create_task(
                self._update_last_state(device_id, _json.loads(payload)["devices"][device_id])
            )

        elif device_type == DEVICE_TYPE_SENSOR_TEMP:
            # Проверяем что изменившаяся сущность принадлежит этому датчику
            sensor_entities = {
                attrs.get("temperature_entity"),
                attrs.get("humidity_entity"),
                attrs.get("battery_entity"),
                attrs.get("signal_entity"),
            }
            if changed_entity_id not in sensor_entities:
                return

            _LOGGER.debug("Sensor %s: обновление состояния", device_id)

            # Читаем актуальные значения всех слотов датчика
            def _val(eid: str | None) -> float | None:
                if not eid:
                    return None
                s = self._hass.states.get(eid)
                if not s or s.state in ("unavailable", "unknown", ""):
                    return None
                try:
                    return float(s.state)
                except (ValueError, TypeError):
                    return None

            payload = self._serializer.build_sensor_temp_state_payload(
                device_id,
                _val(attrs.get("temperature_entity")),
                _val(attrs.get("humidity_entity")),
                _val(attrs.get("battery_entity")),
                _val(attrs.get("signal_entity")),
            )
            self._publish_status(payload)

            # Сохраняем полный отправленный payload как last_state
            import json as _json
            self._hass.async_create_task(
                self._update_last_state(device_id, _json.loads(payload)["devices"][device_id])
            )
