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
    RELAY_STATEFUL_DOMAINS,
    RELAY_BUTTON_DOMAINS,
    SCENARIO_BUTTON_STATEFUL_DOMAINS,
    SCENARIO_BUTTON_PUSH_DOMAINS,
    SCENARIO_BUTTON_CLICK,
    SCENARIO_BUTTON_DOUBLE_CLICK,
    HA_HVAC_MODE_TO_SBER,
    HA_VACUUM_STATUS_TO_SBER,
    HA_VALVE_STATE_TO_SBER,
    HA_COVER_STATE_TO_SBER_OPEN_SET,
    HA_COVER_STATE_TO_SBER_OPEN_STATE,
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
                # Кнопки и сценарии не имеют состояния — не отслеживаем
                if domain in RELAY_STATEFUL_DOMAINS:
                    watched.add(entity_id)
                # Энергосенсоры — отслеживаем независимо от домена
                for key in ("power_entity", "current_entity", "voltage_entity"):
                    if attrs.get(key):
                        watched.add(attrs[key])

            elif device_type == DEVICE_TYPE_SENSOR_TEMP:
                # Отслеживаем все заполненные слоты датчика
                for key in ("temperature_entity", "humidity_entity", "battery_entity", "signal_entity"):
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
            energy_entities = {
                attrs.get("power_entity"),
                attrs.get("current_entity"),
                attrs.get("voltage_entity"),
            } - {None, ""}
            # Реагируем на изменение основной сущности или любого энергосенсора
            if changed_entity_id != bound_entity and changed_entity_id not in energy_entities:
                return

            # Определяем новое значение on/off
            # Для media_player: "off" = выключен, остальные состояния (on/idle/playing/paused) = включён
            relay_state = self._hass.states.get(bound_entity)
            if relay_state is None:
                return

            if bound_entity.startswith("media_player."):
                is_on = relay_state.state != "off"
            else:
                is_on = relay_state.state == "on"

            # Читаем показания энергосенсоров
            def _read_sensor(eid: str | None) -> float | None:
                if not eid:
                    return None
                s = self._hass.states.get(eid)
                if not s or s.state in ("unavailable", "unknown", ""):
                    return None
                try:
                    return float(s.state)
                except (ValueError, TypeError):
                    return None

            power   = _read_sensor(attrs.get("power_entity"))
            current = _read_sensor(attrs.get("current_entity"))
            voltage = _read_sensor(attrs.get("voltage_entity"))

            # Проверка на дубль: не отправляем если состояние не изменилось.
            # last_state теперь хранит {"states": [{"key": "on_off", "value": {...}}]}
            last = device.get("last_state", {})
            last_on_off = None
            for s in last.get("states", []):
                if s.get("key") == "on_off":
                    last_on_off = s.get("value", {}).get("bool_value")
                    break
            # Для энергосенсоров не проверяем дубли — всегда публикуем актуальные значения
            if last_on_off == is_on and changed_entity_id == bound_entity and not energy_entities:
                return

            _LOGGER.debug(
                "Relay %s: изменение состояния %s → %s (power=%s current=%s voltage=%s)",
                device_id,
                "on" if last_on_off else "off",
                "on" if is_on else "off",
                power, current, voltage,
            )

            # Публикуем новое состояние в Сбер
            payload = self._serializer.build_relay_state_payload(
                device_id, is_on, power=power, current=current, voltage=voltage
            )
            self._publish_status(payload)

            # Сохраняем полный отправленный payload как last_state
            import json as _json
            self._hass.async_create_task(
                self._update_last_state(device_id, _json.loads(payload)["devices"][device_id])
            )

        elif device_type == DEVICE_TYPE_SCENARIO_BUTTON:
            bound_entity = attrs.get("entity_id", "")
            if bound_entity != changed_entity_id:
                return

            domain = changed_entity_id.split(".")[0]

            if domain in SCENARIO_BUTTON_PUSH_DOMAINS:
                # Кнопки и сценарии: любое срабатывание → click
                event = SCENARIO_BUTTON_CLICK
            elif domain in SCENARIO_BUTTON_STATEFUL_DOMAINS:
                # Статусные домены: включение → click, выключение → double_click
                if domain == "media_player":
                    is_on = new_state.state != "off"
                else:
                    is_on = new_state.state == "on"
                event = SCENARIO_BUTTON_CLICK if is_on else SCENARIO_BUTTON_DOUBLE_CLICK
            else:
                return

            _LOGGER.debug(
                "ScenarioButton %s: отправляем событие '%s' (entity=%s state=%s)",
                device_id, event, changed_entity_id, new_state.state,
            )

            payload = self._serializer.build_scenario_button_event_payload(device_id, event)
            self._publish_status(payload)

            import json as _json
            self._hass.async_create_task(
                self._update_last_state(device_id, _json.loads(payload)["devices"][device_id])
            )

        elif device_type == DEVICE_TYPE_HVAC_AC:
            # Отслеживаем и climate-сущность, и опциональный датчик температуры
            climate_entity = attrs.get("entity_id", "")
            temp_entity    = attrs.get("temperature_entity", "")
            if changed_entity_id not in {climate_entity, temp_entity}:
                return

            # Читаем состояние climate-сущности
            climate_state = self._hass.states.get(climate_entity)
            if not climate_state:
                return

            is_on       = climate_state.state != "off"
            target_temp = climate_state.attributes.get("temperature")
            ha_mode     = climate_state.state if is_on else None
            work_mode   = HA_HVAC_MODE_TO_SBER.get(ha_mode) if ha_mode else None

            # Текущая температура — из внешнего датчика или из атрибутов climate
            current_temp = None
            if temp_entity:
                s = self._hass.states.get(temp_entity)
                if s and s.state not in ("unavailable", "unknown", ""):
                    try:
                        current_temp = float(s.state)
                    except (ValueError, TypeError):
                        pass
            if current_temp is None:
                ct = climate_state.attributes.get("current_temperature")
                if ct is not None:
                    try:
                        current_temp = float(ct)
                    except (ValueError, TypeError):
                        pass

            _LOGGER.debug(
                "HVAC %s: is_on=%s target=%.1f mode=%s current_temp=%s",
                device_id, is_on, target_temp or 0, work_mode, current_temp,
            )

            payload = self._serializer.build_hvac_ac_state_payload(
                device_id, is_on, target_temp, work_mode, current_temp
            )
            self._publish_status(payload)

            import json as _json
            self._hass.async_create_task(
                self._update_last_state(device_id, _json.loads(payload)["devices"][device_id])
            )

        elif device_type == DEVICE_TYPE_VACUUM:
            vacuum_entity  = attrs.get("entity_id", "")
            battery_entity = attrs.get("battery_entity", "")
            if changed_entity_id not in {vacuum_entity, battery_entity}:
                return

            # Читаем состояние vacuum-сущности
            vacuum_state = self._hass.states.get(vacuum_entity)
            if not vacuum_state:
                return

            ha_status   = vacuum_state.state
            sber_status = HA_VACUUM_STATUS_TO_SBER.get(ha_status, "docked")

            # Заряд батареи — из внешнего сенсора или из атрибутов vacuum
            battery = None
            if battery_entity:
                s = self._hass.states.get(battery_entity)
                if s and s.state not in ("unavailable", "unknown", ""):
                    try:
                        battery = float(s.state)
                    except (ValueError, TypeError):
                        pass
            if battery is None:
                bl = vacuum_state.attributes.get("battery_level")
                if bl is not None:
                    try:
                        battery = float(bl)
                    except (ValueError, TypeError):
                        pass

            _LOGGER.debug(
                "Vacuum %s: status=%s→%s battery=%s",
                device_id, ha_status, sber_status, battery,
            )

            payload = self._serializer.build_vacuum_state_payload(device_id, sber_status, battery)
            self._publish_status(payload)

            import json as _json
            self._hass.async_create_task(
                self._update_last_state(device_id, _json.loads(payload)["devices"][device_id])
            )

        elif device_type == DEVICE_TYPE_VALVE:
            entity_id = attrs.get("entity_id", "")
            if changed_entity_id != entity_id:
                return

            valve_state = self._hass.states.get(entity_id)
            if not valve_state:
                return

            ha_state  = valve_state.state
            domain    = entity_id.split(".")[0]

            # open_set: открыт или закрыт
            open_set = HA_VALVE_STATE_TO_SBER.get(ha_state, "close")

            # open_state: детальный статус (opening/closing/open/close/stopped)
            if ha_state == "opening":
                open_state = "opening"
            elif ha_state == "closing":
                open_state = "closing"
            elif open_set == "open":
                open_state = "open"
            else:
                open_state = "close"

            _LOGGER.debug(
                "Valve %s: ha_state=%s → open_set=%s open_state=%s",
                device_id, ha_state, open_set, open_state,
            )

            payload = self._serializer.build_valve_state_payload(device_id, open_set, open_state)
            self._publish_status(payload)

            import json as _json
            self._hass.async_create_task(
                self._update_last_state(device_id, _json.loads(payload)["devices"][device_id])
            )

        elif device_type == DEVICE_TYPE_LIGHT:
            entity_id = attrs.get("entity_id", "")
            if changed_entity_id != entity_id:
                return

            light_state = self._hass.states.get(entity_id)
            if not light_state:
                return

            is_on = light_state.state == "on"
            a     = light_state.attributes

            # Определяем активные фичи из конфига устройства
            features = ["on_off"]
            for feat in ("light_brightness", "light_colour", "light_colour_temp", "light_mode"):
                if attrs.get(feat):
                    features.append(feat)

            # Яркость: HA 0–255 → 0.0–1.0
            brightness_pct = None
            if a.get("brightness") is not None:
                try:
                    brightness_pct = float(a["brightness"]) / 255.0
                except (ValueError, TypeError):
                    pass

            hs_color          = a.get("hs_color")           # (h, s) или None
            # Фолбэк: если hs_color не заполнен, но есть rgb_color — конвертируем
            if hs_color is None and a.get("rgb_color") is not None:
                try:
                    import colorsys
                    r, g, b = [x / 255.0 for x in a["rgb_color"][:3]]
                    h, s, _ = colorsys.rgb_to_hsv(r, g, b)
                    hs_color = (h * 360.0, s * 100.0)
                except Exception:
                    pass
            color_temp_mireds = a.get("color_temp")         # мирады или None
            min_mireds        = a.get("min_mireds")
            max_mireds        = a.get("max_mireds")
            color_mode        = a.get("color_mode")

            _LOGGER.debug(
                "Light %s: is_on=%s brightness=%.2f color_mode=%s",
                device_id, is_on, brightness_pct or 0, color_mode,
            )

            payload = self._serializer.build_light_state_payload(
                device_id=device_id,
                is_on=is_on,
                features=features,
                brightness_pct=brightness_pct,
                hs_color=hs_color,
                color_temp_mireds=color_temp_mireds,
                min_mireds=min_mireds,
                max_mireds=max_mireds,
                color_mode=color_mode,
            )
            self._publish_status(payload)

            import json as _json
            self._hass.async_create_task(
                self._update_last_state(device_id, _json.loads(payload)["devices"][device_id])
            )

        elif device_type == DEVICE_TYPE_COVER:
            entity_id      = attrs.get("entity_id", "")
            battery_entity = attrs.get("battery_entity", "")
            if changed_entity_id not in {entity_id, battery_entity}:
                return

            cover_state = self._hass.states.get(entity_id)
            if not cover_state:
                return

            ha_state     = cover_state.state
            open_set     = HA_COVER_STATE_TO_SBER_OPEN_SET.get(ha_state, "close")
            open_state_v = HA_COVER_STATE_TO_SBER_OPEN_STATE.get(ha_state, "close")

            # current_position: HA 0–100 (0=закрыто, 100=открыто)
            pos = cover_state.attributes.get("current_position")
            try:
                open_percentage = max(0, min(100, round(float(pos)))) if pos is not None else (100 if open_set == "open" else 0)
            except (ValueError, TypeError):
                open_percentage = 0

            # Заряд батареи
            battery = None
            if battery_entity:
                s = self._hass.states.get(battery_entity)
                if s and s.state not in ("unavailable", "unknown", ""):
                    try:
                        battery = float(s.state)
                    except (ValueError, TypeError):
                        pass

            _LOGGER.debug(
                "Cover %s: ha_state=%s → open_set=%s open_state=%s pos=%s battery=%s",
                device_id, ha_state, open_set, open_state_v, open_percentage, battery,
            )

            payload = self._serializer.build_cover_state_payload(
                device_id, open_set, open_state_v, open_percentage, battery
            )
            self._publish_status(payload)

            import json as _json
            self._hass.async_create_task(
                self._update_last_state(device_id, _json.loads(payload)["devices"][device_id])
            )

        elif device_type == DEVICE_TYPE_SENSOR_TEMP:
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
