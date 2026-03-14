"""Формирование MQTT payload текущего состояния устройства.

Единственное место, где читается состояние из HA и преобразуется
в payload для Сбера. Используется из:
  - __init__.py  — при запросе состояний от Сбера (on_status_request)
  - state_tracker.py — при изменении состояния сущности HA

Сигнатура основной функции:
    build_current_state_payload(hass, device_id, device, serializer) -> str | None
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant

from .const import (
    RELAY_BUTTON_DOMAINS,
    SCENARIO_BUTTON_PUSH_DOMAINS,
    SCENARIO_BUTTON_STATEFUL_DOMAINS,
    SCENARIO_BUTTON_CLICK,
    SCENARIO_BUTTON_DOUBLE_CLICK,
    HA_HVAC_MODE_TO_SBER,
    HA_VACUUM_STATUS_TO_SBER,
    HA_VALVE_STATE_TO_SBER,
    HA_COVER_STATE_TO_SBER_OPEN_SET,
    HA_COVER_STATE_TO_SBER_OPEN_STATE,
    HA_MODE_TO_SBER_AIR_FLOW,
    HA_AC_FAN_MODE_TO_SBER,
    HA_AC_PRESET_TO_SBER_AIR_FLOW,
    HA_AC_SWING_TO_SBER,
    DEVICE_TYPE_SMOKE,
)

if TYPE_CHECKING:
    from .sber_serializer import SberSerializer

_LOGGER = logging.getLogger(__name__)


def _safe_float(state_obj, attr: str | None = None) -> float | None:
    """Безопасно читает float из state или атрибута."""
    try:
        val = state_obj.attributes.get(attr) if attr else state_obj.state
        return float(val) if val not in (None, "", "unavailable", "unknown") else None
    except (ValueError, TypeError):
        return None


def _sensor_float(hass: HomeAssistant, entity_id: str | None) -> float | None:
    """Читает float из сенсора HA."""
    if not entity_id:
        return None
    s = hass.states.get(entity_id)
    if not s or s.state in ("unavailable", "unknown", ""):
        return None
    try:
        return float(s.state)
    except (ValueError, TypeError):
        return None


def _sensor_bool(hass: HomeAssistant, entity_id: str | None) -> bool | None:
    """Читает bool из binary_sensor / switch HA."""
    if not entity_id:
        return None
    s = hass.states.get(entity_id)
    if not s or s.state in ("unavailable", "unknown", ""):
        return None
    return s.state == "on"


def build_current_state_payload(
    hass: HomeAssistant,
    device_id: str,
    device: dict,
    serializer: "SberSerializer",
) -> str | None:
    """Читает текущее состояние из HA и формирует MQTT payload для Сбера.

    Возвращает None если состояние недоступно или тип устройства неизвестен.
    """
    device_type = device.get("device_type")
    attrs = device.get("attributes", {})

    # ── Реле ─────────────────────────────────────────────────────────────
    if device_type == "relay":
        entity_id = attrs.get("entity_id", "")
        domain = entity_id.split(".")[0] if entity_id else ""
        if domain in RELAY_BUTTON_DOMAINS:
            is_on = False
        else:
            state = hass.states.get(entity_id)
            if state:
                is_on = (state.state != "off") if domain == "media_player" else (state.state == "on")
            else:
                is_on = False
        return serializer.build_relay_state_payload(device_id, is_on)

    # ── Датчик температуры/влажности ─────────────────────────────────────
    if device_type == "sensor_temp":
        return serializer.build_sensor_temp_state_payload(
            device_id,
            _sensor_float(hass, attrs.get("temperature_entity")),
            _sensor_float(hass, attrs.get("humidity_entity")),
            _sensor_float(hass, attrs.get("battery_entity")),
        )

    # ── Сценарная кнопка ─────────────────────────────────────────────────
    if device_type == "scenario_button":
        entity_id = attrs.get("entity_id", "")
        domain = entity_id.split(".")[0] if entity_id else ""
        if domain in SCENARIO_BUTTON_PUSH_DOMAINS:
            event = SCENARIO_BUTTON_CLICK
        elif domain in SCENARIO_BUTTON_STATEFUL_DOMAINS:
            state = hass.states.get(entity_id)
            if state:
                is_on = (state.state != "off") if domain == "media_player" else (state.state == "on")
            else:
                is_on = False
            event = SCENARIO_BUTTON_CLICK if is_on else SCENARIO_BUTTON_DOUBLE_CLICK
        else:
            return None
        return serializer.build_scenario_button_event_payload(device_id, event)

    # ── Кондиционер ──────────────────────────────────────────────────────
    if device_type == "hvac_ac":
        entity_id = attrs.get("entity_id", "")
        cs = hass.states.get(entity_id)
        if not cs:
            return None

        is_on     = cs.state != "off"
        ha_mode   = cs.state if is_on else None
        work_mode = HA_HVAC_MODE_TO_SBER.get(ha_mode) if ha_mode else None

        # Текущая температура — из внешнего датчика или из атрибутов climate
        current_temp = _sensor_float(hass, attrs.get("temperature_entity"))
        if current_temp is None:
            current_temp = _safe_float(cs, "current_temperature")

        # Скорость вентилятора: preset приоритетнее fan_mode
        air_flow_power: str | None = None
        if cs.attributes.get("fan_modes"):
            preset = cs.attributes.get("preset_mode", "none")
            if preset and preset != "none":
                air_flow_power = HA_AC_PRESET_TO_SBER_AIR_FLOW.get(preset)
            if air_flow_power is None:
                air_flow_power = HA_AC_FAN_MODE_TO_SBER.get(cs.attributes.get("fan_mode", ""))

        # Направление потока — из swing_mode
        air_flow_direction: str | None = None
        if cs.attributes.get("swing_modes"):
            swing = cs.attributes.get("swing_mode", "")
            if swing:
                air_flow_direction = HA_AC_SWING_TO_SBER.get(swing)

        return serializer.build_hvac_ac_state_payload(
            device_id, is_on, cs.attributes.get("temperature"), work_mode,
            current_temp, air_flow_power, air_flow_direction,
        )

    # ── Пылесос ──────────────────────────────────────────────────────────
    if device_type == "vacuum_cleaner":
        entity_id = attrs.get("entity_id", "")
        vs = hass.states.get(entity_id)
        if not vs:
            return None

        sber_status = HA_VACUUM_STATUS_TO_SBER.get(vs.state, "docked")

        battery = _sensor_float(hass, attrs.get("battery_entity"))
        if battery is None:
            battery = _safe_float(vs, "battery_level")

        return serializer.build_vacuum_state_payload(device_id, sber_status, battery)

    # ── Кран / вентиль ───────────────────────────────────────────────────
    if device_type == "valve":
        entity_id = attrs.get("entity_id", "")
        vs = hass.states.get(entity_id)
        if not vs:
            return None

        ha_state  = vs.state
        open_set  = HA_VALVE_STATE_TO_SBER.get(ha_state, "close")
        if ha_state == "opening":
            open_state = "opening"
        elif ha_state == "closing":
            open_state = "closing"
        elif open_set == "open":
            open_state = "open"
        else:
            open_state = "close"

        return serializer.build_valve_state_payload(device_id, open_set, open_state)

    # ── Лампа ────────────────────────────────────────────────────────────
    if device_type == "light":
        entity_id = attrs.get("entity_id", "")
        ls = hass.states.get(entity_id)
        if not ls:
            return None

        is_on = ls.state == "on"
        a = ls.attributes

        features = ["on_off"]
        for feat in ("light_brightness", "light_colour", "light_colour_temp", "light_mode"):
            if attrs.get(feat):
                features.append(feat)

        brightness_pct = None
        if a.get("brightness") is not None:
            try:
                brightness_pct = float(a["brightness"]) / 255.0
            except (ValueError, TypeError):
                pass

        hs_color = a.get("hs_color")
        if hs_color is None and a.get("rgb_color") is not None:
            try:
                import colorsys
                r, g, b = [x / 255.0 for x in a["rgb_color"][:3]]
                h, s, _ = colorsys.rgb_to_hsv(r, g, b)
                hs_color = (h * 360.0, s * 100.0)
            except Exception:
                pass

        color_temp_mireds = a.get("color_temp")
        if color_temp_mireds is None and a.get("color_temp_kelvin") is not None:
            try:
                color_temp_mireds = 1_000_000 / float(a["color_temp_kelvin"])
            except (ValueError, TypeError, ZeroDivisionError):
                pass

        min_mireds = a.get("min_mireds")
        max_mireds = a.get("max_mireds")
        if min_mireds is None and a.get("max_color_temp_kelvin") is not None:
            try:
                min_mireds = 1_000_000 / float(a["max_color_temp_kelvin"])
            except (ValueError, TypeError, ZeroDivisionError):
                pass
        if max_mireds is None and a.get("min_color_temp_kelvin") is not None:
            try:
                max_mireds = 1_000_000 / float(a["min_color_temp_kelvin"])
            except (ValueError, TypeError, ZeroDivisionError):
                pass

        return serializer.build_light_state_payload(
            device_id=device_id,
            is_on=is_on,
            features=features,
            brightness_pct=brightness_pct,
            hs_color=hs_color,
            color_temp_mireds=color_temp_mireds,
            min_mireds=min_mireds,
            max_mireds=max_mireds,
            color_mode=a.get("color_mode"),
        )

    # ── Рулонные шторы / жалюзи ──────────────────────────────────────────
    if device_type == "cover":
        entity_id = attrs.get("entity_id", "")
        cs = hass.states.get(entity_id)
        if not cs:
            return None

        ha_state     = cs.state
        open_set     = HA_COVER_STATE_TO_SBER_OPEN_SET.get(ha_state, "close")
        open_state_v = HA_COVER_STATE_TO_SBER_OPEN_STATE.get(ha_state, "close")

        pos = cs.attributes.get("current_position")
        try:
            open_percentage = max(0, min(100, round(float(pos)))) if pos is not None else (100 if open_set == "open" else 0)
        except (ValueError, TypeError):
            open_percentage = 0

        return serializer.build_cover_state_payload(
            device_id, open_set, open_state_v, open_percentage,
            _sensor_float(hass, attrs.get("battery_entity")),
        )

    # ── Датчик протечки ──────────────────────────────────────────────────
    if device_type == "water_leak":
        entity_id = attrs.get("entity_id", "")
        ls = hass.states.get(entity_id)
        if not ls:
            return None
        return serializer.build_water_leak_state_payload(
            device_id,
            ls.state == "on",
            _sensor_float(hass, attrs.get("battery_entity")),
        )

    # ── Датчик дыма ──────────────────────────────────────────────────────
    if device_type == DEVICE_TYPE_SMOKE:
        entity_id = attrs.get("entity_id", "")
        ss = hass.states.get(entity_id)
        if not ss:
            return None
        return serializer.build_smoke_state_payload(
            device_id,
            ss.state == "on",
            _sensor_float(hass, attrs.get("battery_entity")),
            _sensor_bool(hass, attrs.get("alarm_mute_entity")),
        )

    # ── Увлажнитель воздуха ──────────────────────────────────────────────
    if device_type == "humidifier":
        entity_id = attrs.get("entity_id", "")
        state = hass.states.get(entity_id)
        if not state:
            return None

        is_on = state.state not in ("off", "unavailable", "unknown")
        ha_mode = state.attributes.get("mode")
        air_flow_power = HA_MODE_TO_SBER_AIR_FLOW.get(ha_mode) if ha_mode else None

        replace_filter: bool | None = None
        rfe = attrs.get("replace_filter_entity")
        if rfe:
            rs = hass.states.get(rfe)
            if rs and rs.state not in ("unavailable", "unknown", ""):
                replace_filter = rs.state == "on"

        return serializer.build_humidifier_state_payload(
            device_id, is_on,
            current_humidity=_safe_float(state, "current_humidity"),
            target_humidity=_safe_float(state, "humidity"),
            air_flow_power=air_flow_power,
            replace_filter=replace_filter,
            water_percentage=_sensor_float(hass, attrs.get("water_percentage_entity")),
        )

    # ── Розетка с энергомониторингом ─────────────────────────────────────
    if device_type == "socket":
        entity_id = attrs.get("entity_id", "")
        state = hass.states.get(entity_id)
        is_on = state.state == "on" if state else False
        return serializer.build_socket_state_payload(
            device_id, is_on,
            power=_sensor_float(hass, attrs.get("power_entity")),
            current=_sensor_float(hass, attrs.get("current_entity")),
            voltage=_sensor_float(hass, attrs.get("voltage_entity")),
        )

    _LOGGER.warning("build_current_state_payload: неизвестный тип устройства '%s'", device_type)
    return None
