"""Формирование MQTT-сообщений для брокера Сбера.

Правильный формат конфигурационного payload (восстановлен из рабочего плагина):
{
  "devices": [
    {
      // Корневой HUB — обязателен, без него Сбер не принимает конфиг
      "id": "root",
      "name": "...",
      "hw_version": "2.0.12",
      "sw_version": "2.0.12",
      "model": {
        "id": "ID_root_hub",
        "manufacturer": "TM",
        "model": "VHub",
        "description": "...",
        "category": "hub",
        "features": ["online"]
      }
    },
    {
      // Обычное устройство (реле, датчик и т.д.)
      "id": "мой_id",
      "name": "Имя устройства",
      "room": "Комната",
      "hw_version": "hw:2.0.12",
      "sw_version": "sw:2.0.12",
      "model": {
        "id": "ID_relay",
        "manufacturer": "TM",
        "model": "Model_relay",
        "category": "relay",
        "features": ["online", "on_off"]
      },
      "model_id": ""
    }
  ]
}

Формат payload состояния:
{
  "devices": {
    "мой_id": {
      "states": [
        {"key": "online",  "value": {"type": "BOOL",    "bool_value": true}},
        {"key": "on_off",  "value": {"type": "BOOL",    "bool_value": true}},
        {"key": "temperature", "value": {"type": "INTEGER", "integer_value": 215}},  // 21.5°C × 10
        {"key": "humidity",    "value": {"type": "INTEGER", "integer_value": 55}},
        {"key": "signal_strength", "value": {"type": "ENUM", "enum_value": "high"}}  // low/medium/high
      ]
    }
  }
}
"""
from __future__ import annotations

import json
import logging
from typing import Any

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
    DEVICE_TYPE_SENSOR_DOOR,
    DEVICE_TYPE_SENSOR_AIR,
    DEVICE_TYPE_HVAC_RADIATOR,
    DEVICE_TYPE_HVAC_FAN,
    DEVICE_TYPE_TV,
    DEVICE_TYPE_INTERCOM,
    DEVICE_TYPE_SENSOR_PIR,
    DEVICE_TYPE_EVENT_BUTTON,
    DEVICE_TYPE_AIR_PURIFIER,
    HA_HVAC_MODE_TO_SBER,
    HA_MODE_TO_SBER_AIR_FLOW,
    SIGNAL_STRENGTH_LOW_THRESHOLD,
    SIGNAL_STRENGTH_HIGH_THRESHOLD,
    LIGHT_BRIGHTNESS_MIN,
    LIGHT_BRIGHTNESS_MAX,
    LIGHT_COLOUR_TEMP_MIN,
    LIGHT_COLOUR_TEMP_MAX,
    HA_COLOR_MODE_TO_SBER_LIGHT_MODE,
)

_LOGGER = logging.getLogger(__name__)

# Версии прошивки — передаются в конфиге каждого устройства
HW_VERSION   = "hw:2.0.12"
SW_VERSION   = "sw:2.0.12"
MANUFACTURER = "TM"

# Корневой HUB-девайс — обязательный элемент конфига.
# Без него Сбер возвращает ошибку "value must contain at least 1 item(s)"
# даже если реальные устройства присутствуют.
ROOT_DEVICE = {
    "id": "root",
    "name": "HA MQTT SberGate HUB",
    "hw_version": "2.0.12",
    "sw_version": "2.0.12",
    "model": {
        "id": "ID_root_hub",
        "manufacturer": MANUFACTURER,
        "model": "VHub",
        "description": "HA MQTT SberGate HUB",
        "category": "hub",
        "features": ["online"],
    },
}


class SberSerializer:
    """Формирует MQTT payload для брокера Сбера."""

    # ── Конфигурационные payload ───────────────────────────────────────────

    def build_config_payload(self, devices: dict[str, Any]) -> str:
        """Формирует полный конфиг всех устройств для отправки в Сбер.

        Всегда включает корневой HUB-девайс первым элементом списка,
        затем все зарегистрированные пользователем устройства.
        """
        result = [ROOT_DEVICE]  # HUB всегда первый
        for device_id, device in devices.items():
            entry = self._build_device_config_entry(device_id, device)
            if entry:
                result.append(entry)
        return json.dumps({"devices": result}, ensure_ascii=False)

    def _build_device_config_entry(self, device_id: str, device: dict) -> dict | None:
        """Формирует запись конфига для одного устройства по его типу."""
        device_type = device.get("device_type")
        if device_type == DEVICE_TYPE_RELAY:
            return self._relay_config(device_id, device)
        if device_type == DEVICE_TYPE_SENSOR_TEMP:
            return self._sensor_temp_config(device_id, device)
        if device_type == DEVICE_TYPE_SCENARIO_BUTTON:
            return self._scenario_button_config(device_id, device)
        if device_type == DEVICE_TYPE_HVAC_AC:
            return self._hvac_ac_config(device_id, device)
        if device_type == DEVICE_TYPE_VACUUM:
            return self._vacuum_config(device_id, device)
        if device_type == DEVICE_TYPE_VALVE:
            return self._valve_config(device_id, device)
        if device_type == DEVICE_TYPE_LIGHT:
            return self._light_config(device_id, device)
        if device_type == DEVICE_TYPE_COVER:
            return self._cover_config(device_id, device)
        if device_type == DEVICE_TYPE_WATER_LEAK:
            return self._water_leak_config(device_id, device)
        if device_type == DEVICE_TYPE_HUMIDIFIER:
            return self._humidifier_config(device_id, device)
        if device_type == DEVICE_TYPE_SOCKET:
            return self._socket_config(device_id, device)
        if device_type == DEVICE_TYPE_SMOKE:
            return self._smoke_config(device_id, device)
        if device_type == DEVICE_TYPE_KETTLE:
            return self._kettle_config(device_id, device)
        if device_type == DEVICE_TYPE_SENSOR_DOOR:
            return self._sensor_door_config(device_id, device)
        if device_type == DEVICE_TYPE_SENSOR_AIR:
            return self._sensor_air_config(device_id, device)
        if device_type == DEVICE_TYPE_HVAC_RADIATOR:
            return self._hvac_radiator_config(device_id, device)
        if device_type == DEVICE_TYPE_HVAC_FAN:
            return self._hvac_fan_config(device_id, device)
        if device_type == DEVICE_TYPE_TV:
            return self._tv_config(device_id, device)
        if device_type == DEVICE_TYPE_INTERCOM:
            return self._intercom_config(device_id, device)
        if device_type == DEVICE_TYPE_SENSOR_PIR:
            return self._sensor_pir_config(device_id, device)
        if device_type == DEVICE_TYPE_EVENT_BUTTON:
            return self._event_button_config(device_id, device)
        if device_type == DEVICE_TYPE_AIR_PURIFIER:
            return self._air_purifier_config(device_id, device)
        _LOGGER.warning("Неизвестный тип устройства: %s", device_type)
        return None

    def _relay_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для реле (switch, light, button и т.д.) — только вкл/выкл."""
        model: dict = {
            "id": "ID_relay",
            "manufacturer": MANUFACTURER,
            "model": "Model_relay",
            "category": DEVICE_TYPE_RELAY,
            "features": ["online", "on_off"],
        }
        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": model,
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _sensor_temp_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для датчика температуры/влажности.

        Список features формируется динамически — только те параметры,
        для которых пользователь указал сущность HA.
        """
        attrs = device.get("attributes", {})

        # Собираем список поддерживаемых параметров датчика
        features = ["online"]
        if attrs.get("temperature_entity"):
            features.append("temperature")
        if attrs.get("humidity_entity"):
            features.append("humidity")
        if attrs.get("battery_entity"):
            features.append("battery_percentage")

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_sensor_temp",
                "manufacturer": MANUFACTURER,
                "model": "Model_sensor_temp",
                "category": DEVICE_TYPE_SENSOR_TEMP,
                "features": features,
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _scenario_button_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для сценарной кнопки.

        Поддерживает события button_event: click (включение / нажатие кнопки)
        и double_click (выключение). Долгое нажатие не используется.
        """
        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_scenario_button",
                "manufacturer": MANUFACTURER,
                "model": "Model_scenario_button",
                "category": DEVICE_TYPE_SCENARIO_BUTTON,
                "features": ["online", "button_event"],
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _hvac_ac_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для кондиционера (hvac_ac).

        Обязательные функции: online, on_off, hvac_temp_set, hvac_work_mode.
        hvac_air_flow_power — если кондиционер поддерживает fan_modes.
        temperature — если задан датчик текущей температуры.
        allowed_values — ограничивает допустимые значения hvac_work_mode, hvac_air_flow_power
          и диапазон hvac_temp_set на основе атрибутов климат-сущности HA.
        """
        from .const import HA_HVAC_MODE_TO_SBER, HA_AC_FAN_MODE_TO_SBER, HA_AC_PRESET_TO_SBER_AIR_FLOW

        attrs = device.get("attributes", {})
        features = ["online", "on_off", "hvac_temp_set", "hvac_work_mode"]
        if attrs.get("fan_modes"):
            features.append("hvac_air_flow_power")
        if attrs.get("swing_modes"):
            features.append("hvac_air_flow_direction")
        if attrs.get("temperature_entity"):
            features.append("temperature")

        # ── allowed_values ────────────────────────────────────────────────
        allowed_values: dict = {}

        # hvac_work_mode — только режимы, реально поддерживаемые устройством
        ha_modes = attrs.get("hvac_modes", [])
        sber_work_modes = [
            HA_HVAC_MODE_TO_SBER[m] for m in ha_modes
            if m != "off" and m in HA_HVAC_MODE_TO_SBER
        ]
        # убираем дубли, сохраняем порядок
        seen: set = set()
        sber_work_modes = [m for m in sber_work_modes if not (m in seen or seen.add(m))]
        if sber_work_modes:
            allowed_values["hvac_work_mode"] = {
                "type": "ENUM",
                "enum_values": {"values": sber_work_modes},
            }

        # hvac_temp_set — диапазон и шаг из атрибутов кондиционера
        min_temp  = attrs.get("min_temp")
        max_temp  = attrs.get("max_temp")
        temp_step = attrs.get("target_temp_step")
        if min_temp is not None and max_temp is not None and temp_step is not None:
            try:
                allowed_values["hvac_temp_set"] = {
                    "type": "INTEGER",
                    "integer_values": {
                        "min":  str(round(float(min_temp))),
                        "max":  str(round(float(max_temp))),
                        "step": str(round(float(temp_step))),
                    },
                }
            except (ValueError, TypeError):
                pass

        # hvac_air_flow_power — только значения, реально доступные на устройстве
        if attrs.get("fan_modes"):
            sber_flow_values: list[str] = []
            seen_flow: set = set()
            # fan_modes → прямые значения скорости
            for fm in attrs["fan_modes"]:
                sv = HA_AC_FAN_MODE_TO_SBER.get(fm)
                if sv and sv not in seen_flow:
                    sber_flow_values.append(sv)
                    seen_flow.add(sv)
            # preset_modes → turbo / quiet
            for pm, sv in HA_AC_PRESET_TO_SBER_AIR_FLOW.items():
                if sv not in seen_flow:
                    preset_modes = attrs.get("preset_modes", [])
                    if pm in preset_modes:
                        sber_flow_values.append(sv)
                        seen_flow.add(sv)
            if sber_flow_values:
                allowed_values["hvac_air_flow_power"] = {
                    "type": "ENUM",
                    "enum_values": {"values": sber_flow_values},
                }

        # hvac_air_flow_direction — только направления, реально поддерживаемые устройством
        if attrs.get("swing_modes"):
            from .const import HA_AC_SWING_TO_SBER
            sber_dir_values: list[str] = []
            seen_dir: set = set()
            for sm in attrs["swing_modes"]:
                sv = HA_AC_SWING_TO_SBER.get(sm)
                if sv and sv not in seen_dir:
                    sber_dir_values.append(sv)
                    seen_dir.add(sv)
            if sber_dir_values:
                allowed_values["hvac_air_flow_direction"] = {
                    "type": "ENUM",
                    "enum_values": {"values": sber_dir_values},
                }

        model: dict = {
            "id": "ID_hvac_ac",
            "manufacturer": MANUFACTURER,
            "model": "Model_hvac_ac",
            "category": DEVICE_TYPE_HVAC_AC,
            "features": features,
        }
        if allowed_values:
            model["allowed_values"] = allowed_values

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": model,
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _vacuum_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для пылесоса (vacuum_cleaner).

        Обязательные функции: online.
        Рабочие: vacuum_cleaner_command, vacuum_cleaner_status, battery_percentage.
        """
        attrs = device.get("attributes", {})
        features = ["online", "vacuum_cleaner_command", "vacuum_cleaner_status"]
        if attrs.get("battery_entity"):
            features.append("battery_percentage")

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_vacuum_cleaner",
                "manufacturer": MANUFACTURER,
                "model": "Model_vacuum_cleaner",
                "category": DEVICE_TYPE_VACUUM,
                "features": features,
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _valve_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для крана (valve).

        Категория Сбера: valve.
        Обязательные функции: online, open_state, open_set.
        """
        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_valve",
                "manufacturer": MANUFACTURER,
                "model": "Model_valve",
                "category": DEVICE_TYPE_VALVE,
                "features": ["online", "open_state", "open_set"],
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _light_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для лампы (light).

        Обязательные функции: online, on_off.
        Опциональные (задаются пользователем при добавлении):
          light_brightness, light_colour, light_colour_temp, light_mode.
        """
        attrs = device.get("attributes", {})
        features = ["online", "on_off"]

        # Добавляем опциональные фичи, выбранные пользователем
        for feat in ("light_brightness", "light_colour", "light_colour_temp", "light_mode"):
            if attrs.get(feat):
                features.append(feat)

        model: dict = {
            "id": "ID_light",
            "manufacturer": MANUFACTURER,
            "model": "Model_light",
            "category": DEVICE_TYPE_LIGHT,
            "features": features,
        }

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": model,
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _cover_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для рулонных штор / жалюзи (window_blind).

        Обязательные функции: online, open_state, open_set, open_percentage.
        Опциональная: battery_percentage (если задан датчик).
        """
        attrs = device.get("attributes", {})
        features = ["online", "open_state", "open_set", "open_percentage"]
        if attrs.get("battery_entity"):
            features.append("battery_percentage")

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_window_blind",
                "manufacturer": MANUFACTURER,
                "model": "Model_window_blind",
                "category": "window_blind",
                "features": features,
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _water_leak_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для датчика протечки (sensor_water_leak).

        Обязательные функции: online, water_leak_state.
        Опциональная: battery_percentage (если задан датчик).
        """
        attrs    = device.get("attributes", {})
        features = ["online", "water_leak_state"]
        if attrs.get("battery_entity"):
            features.append("battery_percentage")

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_water_leak",
                "manufacturer": MANUFACTURER,
                "model": "Model_water_leak",
                "category": "sensor_water_leak",
                "features": features,
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _smoke_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для датчика дыма (sensor_smoke).

        Обязательные функции: online, smoke_state.
        Опциональные: battery_percentage, alarm_mute.
        """
        attrs    = device.get("attributes", {})
        features = ["online", "smoke_state"]
        if attrs.get("battery_entity"):
            features.append("battery_percentage")
        if attrs.get("alarm_mute_entity"):
            features.append("alarm_mute")

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_smoke",
                "manufacturer": MANUFACTURER,
                "model": "Model_smoke",
                "category": "sensor_smoke",
                "features": features,
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _kettle_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для чайника (kettle).

        Источник: сущность домена water_heater.
        Обязательные функции: online, on_off.
        Опциональные:
          kitchen_water_temperature     — current_temperature из атрибутов water_heater
          kitchen_water_temperature_set — temperature (целевая) из атрибутов water_heater

        allowed_values для kitchen_water_temperature_set формируется из
        min_temp/max_temp сохранённых при добавлении устройства.
        """
        attrs    = device.get("attributes", {})
        features = ["online", "on_off",
                    "kitchen_water_temperature",
                    "kitchen_water_temperature_set"]
        if attrs.get("water_entity"):
            features.append("kitchen_water_level")
        if attrs.get("water_low_entity"):
            features.append("kitchen_water_low_level")

        model: dict = {
            "id":           "ID_kettle",
            "manufacturer": MANUFACTURER,
            "model":        "Model_kettle",
            "category":     "kettle",
            "features":     features,
        }

        # allowed_values для целевой температуры — из min_temp/max_temp water_heater
        min_t = attrs.get("min_temp")
        max_t = attrs.get("max_temp")
        if min_t is not None and max_t is not None:
            try:
                model["allowed_values"] = {
                    "kitchen_water_temperature_set": {
                        "type": "INTEGER",
                        "integer_values": {
                            "min":  str(round(float(min_t))),
                            "max":  str(round(float(max_t))),
                            "step": "1",
                        },
                    }
                }
            except (ValueError, TypeError):
                pass

        entry = {
            "id":         device_id,
            "name":       device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model":      model,
            "model_id":   "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _sensor_door_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для датчика открытия двери/окна (sensor_door).

        Обязательные функции: online, doorcontact_state.
        Опциональные: battery_percentage (если задан датчик), tamper_alarm (если задан датчик вскрытия).
        """
        attrs    = device.get("attributes", {})
        features = ["online", "doorcontact_state"]
        if attrs.get("battery_entity"):
            features.append("battery_percentage")
        if attrs.get("tamper_entity"):
            features.append("tamper_alarm")

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_sensor_door",
                "manufacturer": MANUFACTURER,
                "model": "Model_sensor_door",
                "category": "sensor_door",
                "features": features,
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _sensor_pir_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для датчика движения (sensor_pir)."""
        attrs    = device.get("attributes", {})
        features = ["online", "pir_state"]
        if attrs.get("battery_entity"):
            features.append("battery_percentage")

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_sensor_pir",
                "manufacturer": MANUFACTURER,
                "model": "Model_sensor_pir",
                "category": "sensor_pir",
                "features": features,
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _event_button_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для кнопки событий — как сценарная кнопка в Сбере."""
        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_event_button",
                "manufacturer": MANUFACTURER,
                "model": "Model_event_button",
                "category": "scenario_button",
                "features": ["online", "button_event"],
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _sensor_air_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для датчика качества воздуха (sensor_air).

        Обязательные функции: online + минимум один из: temperature, humidity, co2, pm2_5, tvoc_float.
        Опциональные: battery_percentage, signal_strength.
        """
        attrs    = device.get("attributes", {})
        features = ["online"]
        if attrs.get("temperature_entity"):
            features.append("temperature")
        if attrs.get("humidity_entity"):
            features.append("humidity")
        if attrs.get("co2_entity"):
            features.append("co2")
        if attrs.get("pm25_entity"):
            features.append("pm2_5")
        if attrs.get("tvoc_entity"):
            features.append("tvoc_float")
        if attrs.get("battery_entity"):
            features.append("battery_percentage")
        if attrs.get("signal_entity"):
            features.append("signal_strength")

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_sensor_air",
                "manufacturer": MANUFACTURER,
                "model": "Model_sensor_air",
                "category": "sensor_air",
                "features": features,
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _hvac_radiator_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для термоголовки радиатора (hvac_radiator).

        Поддерживаемые функции: online, on_off, hvac_temp_set, temperature.
        hvac_temp_set и temperature — опциональны (включаются если заданы).
        allowed_values для hvac_temp_set — из min_temp/max_temp/step климат-сущности HA.
        """
        attrs    = device.get("attributes", {})
        features = ["online", "on_off"]
        if attrs.get("temperature_entity"):
            features.append("temperature")
        if attrs.get("hvac_temp_set"):
            features.append("hvac_temp_set")

        model: dict = {
            "id": "ID_hvac_radiator",
            "manufacturer": MANUFACTURER,
            "model": "Model_hvac_radiator",
            "category": "hvac_radiator",
            "features": features,
        }

        min_t = attrs.get("min_temp")
        max_t = attrs.get("max_temp")
        step  = attrs.get("target_temp_step")
        if min_t is not None and max_t is not None and step is not None:
            try:
                model["allowed_values"] = {
                    "hvac_temp_set": {
                        "type": "INTEGER",
                        "integer_values": {
                            "min":  str(round(float(min_t))),
                            "max":  str(round(float(max_t))),
                            "step": str(round(float(step))),
                        },
                    }
                }
            except (ValueError, TypeError):
                pass

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": model,
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _hvac_fan_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для вентилятора / бризера (hvac_fan).

        Поддерживаемые функции: online, on_off, hvac_air_flow_power.
        """
        attrs    = device.get("attributes", {})
        features = ["online", "on_off"]
        if attrs.get("supports_speed"):
            features.append("hvac_air_flow_power")

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_hvac_fan",
                "manufacturer": MANUFACTURER,
                "model": "Model_hvac_fan",
                "category": "hvac_fan",
                "features": features,
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _tv_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для телевизора (tv).

        Источник: сущность домена media_player.
        Обязательные функции: online, on_off.
        Опциональные (по возможностям сущности, флаги сохранены при добавлении):
          mute       — бесшумный режим          (is_volume_muted / volume_mute)
          volume_int — уровень громкости 0–100  (volume_level / volume_set)
          volume     — громче / тише            (volume_up / volume_down)
        """
        attrs = device.get("attributes", {})
        features = ["online", "on_off"]
        if attrs.get("supports_mute", True):
            features.append("mute")
        if attrs.get("supports_volume_set", True):
            features.append("volume_int")
        if attrs.get("supports_volume_set", True) or attrs.get("supports_volume_step", True):
            features.append("volume")

        model: dict = {
            "id":           "ID_tv",
            "manufacturer": MANUFACTURER,
            "model":        "Model_tv",
            "category":     DEVICE_TYPE_TV,
            "features":     features,
        }
        if "volume_int" in features:
            model["allowed_values"] = {
                "volume_int": {
                    "type": "INTEGER",
                    "integer_values": {"min": "0", "max": "100", "step": "1"},
                }
            }

        entry = {
            "id":         device_id,
            "name":       device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model":      model,
            "model_id":   "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _intercom_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для домофона (intercom)."""
        attrs    = device.get("attributes", {})
        features = ["online", "unlock"]
        if attrs.get("incoming_call_entity"):
            features.append("incoming_call")

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_intercom",
                "manufacturer": MANUFACTURER,
                "model": "Model_intercom",
                "category": "intercom",
                "features": features,
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry
    def _air_purifier_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для очистителя воздуха (hvac_air_purifier).

        Обязательные функции: online, on_off.
        Остальные объявляются только если пользователь сопоставил им сущность HA:
          hvac_air_flow_power, hvac_night_mode, hvac_ionization, hvac_aromatization,
          hvac_decontaminate, hvac_replace_filter, hvac_replace_ionizator.
        Для скорости вентилятора в allowed_values передаются только те значения,
        которые сопоставлены с опциями select.
        """
        from .air_purifier import declared_features, clean_speed_map
        from .const import AIR_PURIFIER_SPEED_VALUES

        attrs    = device.get("attributes", {})
        features = declared_features(attrs)

        model: dict = {
            "id":           "ID_air_purifier",
            "manufacturer": MANUFACTURER,
            "model":        "Model_air_purifier",
            "category":     "hvac_air_purifier",
            "features":     features,
        }
        if "hvac_air_flow_power" in features:
            smap = clean_speed_map(attrs)
            values = [v for v in AIR_PURIFIER_SPEED_VALUES if v in smap]
            model["allowed_values"] = {
                "hvac_air_flow_power": {
                    "type": "ENUM",
                    "enum_values": {"values": values},
                }
            }

        entry = {
            "id":         device_id,
            "name":       device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model":      model,
            "model_id":   "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _humidifier_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для увлажнителя воздуха (hvac_humidifier).

        Обязательные функции: online, on_off.
        Остальные: humidity, hvac_air_flow_power, hvac_humidity_set,
                   hvac_replace_filter, hvac_water_percentage.
        """
        attrs    = device.get("attributes", {})
        features = ["online", "on_off", "humidity", "hvac_air_flow_power",
                    "hvac_humidity_set", "hvac_replace_filter", "hvac_water_percentage"]

        # Убираем опциональные фичи если сенсор не задан
        if not attrs.get("water_percentage_entity"):
            features.remove("hvac_water_percentage")
        if not attrs.get("replace_filter_entity"):
            features.remove("hvac_replace_filter")

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_humidifier",
                "manufacturer": MANUFACTURER,
                "model": "Model_humidifier",
                "category": "hvac_humidifier",
                "features": features,
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    # ── Payload состояния ──────────────────────────────────────────────────

    def build_root_state_payload(self) -> str:
        """Состояние корневого HUB-девайса — всегда онлайн."""
        payload = {
            "devices": {
                "root": {
                    "states": [
                        {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
                    ]
                }
            }
        }
        return json.dumps(payload, ensure_ascii=False)

    def build_relay_state_payload(self, device_id: str, is_on: bool) -> str:
        """Состояние реле: онлайн + вкл/выкл."""
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
            {"key": "on_off", "value": {"type": "BOOL", "bool_value": is_on}},
        ]
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def _socket_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для розетки с энергомониторингом (socket).

        Обязательные функции: online, on_off.
        Обязательные для этого типа: power, current, voltage.
        """
        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_socket",
                "manufacturer": MANUFACTURER,
                "model": "Model_socket",
                "category": "socket",
                "features": ["online", "on_off", "power", "current", "voltage"],
            },
            "model_id": "",
        }
        # allowed_values не отправляем намеренно: Могут быть проблемы с принятием Сбером таких устройств
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def build_socket_state_payload(
        self,
        device_id: str,
        is_on: bool,
        power: float | None = None,
        current: float | None = None,
        voltage: float | None = None,
    ) -> str:
        """Состояние розетки: онлайн + вкл/выкл + показания энергомониторинга.

        power   — мощность, Вт   (0–50000)
        current — ток, мА        (0–30000)
        voltage — напряжение, В  (0–5000)
        """
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
            {"key": "on_off", "value": {"type": "BOOL", "bool_value": is_on}},
        ]
        if power is not None:
            try:
                states.append({"key": "power",   "value": {"type": "INTEGER", "integer_value": max(0, min(50000, round(float(power))))}})
            except (ValueError, TypeError):
                pass
        if current is not None:
            try:
                states.append({"key": "current", "value": {"type": "INTEGER", "integer_value": max(0, min(30000, round(float(current))))}})
            except (ValueError, TypeError):
                pass
        if voltage is not None:
            try:
                states.append({"key": "voltage", "value": {"type": "INTEGER", "integer_value": max(0, min(5000,  round(float(voltage))))}})
            except (ValueError, TypeError):
                pass
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_scenario_button_event_payload(self, device_id: str, event: str) -> str:
        """Событие сценарной кнопки: онлайн + тип нажатия.

        event — одно из: "click", "double_click"
        Сначала отправляем событие нажатия, затем Сбер сам обрабатывает его
        как триггер для пользовательских сценариев в Салюте.
        """
        payload = {
            "devices": {
                device_id: {
                    "states": [
                        {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
                        {"key": "button_event", "value": {"type": "ENUM", "enum_value": event}},
                    ]
                }
            }
        }
        return json.dumps(payload, ensure_ascii=False)

    def build_scenario_button_online_payload(self, device_id: str) -> str:
        """Состояние сценарной кнопки в покое — только online, без button_event.

        Используется при опросе состояний от Сбера и при инициализации.
        button_event отправляется только в момент реального нажатия кнопки в HA.
        """
        payload = {
            "devices": {
                device_id: {
                    "states": [
                        {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
                    ]
                }
            }
        }
        return json.dumps(payload, ensure_ascii=False)

    def build_intercom_state_payload(
        self,
        device_id: str,
        incoming_call: bool | None = None,
    ) -> str:
        """Состояние домофона."""
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
        ]
        if incoming_call is not None:
            states.append({
                "key": "incoming_call",
                "value": {"type": "BOOL", "bool_value": incoming_call},
            })
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_hvac_ac_state_payload(
        self,
        device_id: str,
        is_on: bool,
        target_temp: float | None,
        work_mode: str | None,
        current_temp: float | None = None,
        air_flow_power: str | None = None,
        air_flow_direction: str | None = None,
    ) -> str:
        """Состояние кондиционера.

        is_on               — включён/выключен
        target_temp         — целевая температура (hvac_temp_set), °C
        work_mode           — режим работы в терминах Сбера: cooling/heating/ventilation/…
        current_temp        — текущая температура (temperature), если доступна; × 10
        air_flow_power      — скорость вентилятора: auto/low/medium/high/turbo/quiet
        air_flow_direction  — направление потока: no/vertical/horizontal/rotation/swing/auto
        """
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
            {"key": "on_off", "value": {"type": "BOOL", "bool_value": is_on}},
        ]

        if target_temp is not None:
            try:
                states.append({
                    "key": "hvac_temp_set",
                    "value": {"type": "INTEGER", "integer_value": round(float(target_temp))},
                })
            except (ValueError, TypeError):
                pass

        if work_mode:
            states.append({
                "key": "hvac_work_mode",
                "value": {"type": "ENUM", "enum_value": work_mode},
            })

        if current_temp is not None:
            try:
                # Текущая температура передаётся × 10, как у датчика
                states.append({
                    "key": "temperature",
                    "value": {"type": "INTEGER", "integer_value": round(float(current_temp) * 10)},
                })
            except (ValueError, TypeError):
                pass

        if air_flow_power:
            states.append({
                "key": "hvac_air_flow_power",
                "value": {"type": "ENUM", "enum_value": air_flow_power},
            })

        if air_flow_direction:
            states.append({
                "key": "hvac_air_flow_direction",
                "value": {"type": "ENUM", "enum_value": air_flow_direction},
            })

        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_hvac_fan_state_payload(
        self,
        device_id: str,
        is_on: bool,
        air_flow_power: str | None = None,
    ) -> str:
        """Состояние вентилятора / бризера.

        is_on          — включён/выключен
        air_flow_power — скорость: auto/low/medium/high/turbo/quiet
        """
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
            {"key": "on_off", "value": {"type": "BOOL", "bool_value": is_on}},
        ]
        if air_flow_power:
            states.append({
                "key": "hvac_air_flow_power",
                "value": {"type": "ENUM", "enum_value": air_flow_power},
            })
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_hvac_radiator_state_payload(
        self,
        device_id: str,
        is_on: bool,
        target_temp: float | None = None,
        current_temp: float | None = None,
    ) -> str:
        """Состояние термоголовки радиатора.

        is_on        — включён/выключен
        target_temp  — целевая температура (hvac_temp_set), °C
        current_temp — текущая температура (temperature), если доступна; × 10
        """
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
            {"key": "on_off", "value": {"type": "BOOL", "bool_value": is_on}},
        ]
        if target_temp is not None:
            try:
                states.append({
                    "key": "hvac_temp_set",
                    "value": {"type": "INTEGER", "integer_value": round(float(target_temp))},
                })
            except (ValueError, TypeError):
                pass
        if current_temp is not None:
            try:
                states.append({
                    "key": "temperature",
                    "value": {"type": "INTEGER", "integer_value": round(float(current_temp) * 10)},
                })
            except (ValueError, TypeError):
                pass
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_vacuum_state_payload(
        self,
        device_id: str,
        status: str,
        battery: float | None = None,
    ) -> str:
        """Состояние пылесоса.

        status  — статус в терминах Сбера: cleaning / docked / pause / returning_to_dock
        battery — заряд батареи 0–100 (опционально)
        """
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
            {"key": "vacuum_cleaner_status", "value": {"type": "ENUM", "enum_value": status}},
        ]
        if battery is not None:
            try:
                states.append({
                    "key": "battery_percentage",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(battery))))},
                })
            except (ValueError, TypeError):
                pass
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_valve_state_payload(
        self,
        device_id: str,
        open_set: str,
        open_state: str,
    ) -> str:
        """Состояние крана.

        open_set   — текущее положение: open / close
        open_state — статус открытия: open / close / opening / closing / stopped
        """
        states: list[dict] = [
            {"key": "online",     "value": {"type": "BOOL", "bool_value": True}},
            {"key": "open_set",   "value": {"type": "ENUM", "enum_value": open_set}},
            {"key": "open_state", "value": {"type": "ENUM", "enum_value": open_state}},
        ]
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_light_state_payload(
        self,
        device_id: str,
        is_on: bool,
        features: list[str],
        brightness_pct: float | None = None,
        hs_color: tuple | None = None,
        color_temp_mireds: float | None = None,
        min_mireds: float | None = None,
        max_mireds: float | None = None,
        color_mode: str | None = None,
    ) -> str:
        """Состояние лампы.

        brightness_pct    — яркость 0.0–1.0 (из HA brightness / 255)
        hs_color          — (hue 0–360, sat 0–100) из HA
        color_temp_mireds — цветовая температура в мирадах
        min_mireds        — минимальные мирады лампы (самый холодный)
        max_mireds        — максимальные мирады лампы (самый тёплый)
        color_mode        — текущий color_mode из HA
        """
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
            {"key": "on_off", "value": {"type": "BOOL", "bool_value": is_on}},
        ]

        if not is_on:
            return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

        # Яркость: HA 0–255 → Сбер 50–1000
        if "light_brightness" in features and brightness_pct is not None:
            try:
                sber_brightness = round(
                    LIGHT_BRIGHTNESS_MIN
                    + float(brightness_pct) * (LIGHT_BRIGHTNESS_MAX - LIGHT_BRIGHTNESS_MIN)
                )
                sber_brightness = max(LIGHT_BRIGHTNESS_MIN, min(LIGHT_BRIGHTNESS_MAX, sber_brightness))
                states.append({
                    "key": "light_brightness",
                    "value": {"type": "INTEGER", "integer_value": sber_brightness},
                })
            except (ValueError, TypeError):
                pass

        # Цвет и температура — взаимоисключающие. Выбор по color_mode из HA.
        # color_mode in ('color_temp', 'white') → отправляем температуру
        # color_mode in ('hs', 'rgb', 'xy', …)  → отправляем цвет
        is_colour_mode = color_mode not in (None, "color_temp", "white", "onoff", "brightness")

        if not is_colour_mode:
            # Режим белого/температурного света → light_colour_temp
            if "light_colour_temp" in features and color_temp_mireds is not None:
                try:
                    mn = float(min_mireds or 153)
                    mx = float(max_mireds or 500)
                    ct = float(color_temp_mireds)
                    if mx > mn:
                        # Сбер: 0 = тёплый (max_mireds), 1000 = холодный (min_mireds)
                        sber_ct = round((1.0 - (ct - mn) / (mx - mn)) * LIGHT_COLOUR_TEMP_MAX)
                        sber_ct = max(LIGHT_COLOUR_TEMP_MIN, min(LIGHT_COLOUR_TEMP_MAX, sber_ct))
                    else:
                        sber_ct = 500
                    states.append({
                        "key": "light_colour_temp",
                        "value": {"type": "INTEGER", "integer_value": sber_ct},
                    })
                except (ValueError, TypeError):
                    pass
        else:
            # Режим цвета → light_colour (и light_mode если фича включена)
            if "light_colour" in features and hs_color is not None:
                try:
                    h = float(hs_color[0])
                    s = round(float(hs_color[1]) * 10)  # 0–100 → 0–1000
                    if brightness_pct is not None:
                        v = round(100 + float(brightness_pct) * 900)  # 100–1000
                        v = max(100, min(1000, v))
                    else:
                        v = 1000
                    states.append({
                        "key": "light_colour",
                        "value": {"type": "COLOUR", "colour_value": {"h": round(h), "s": s, "v": v}},
                    })
                except (ValueError, TypeError):
                    pass

        # Режим: colour / white — отправляем только если фича активна
        if "light_mode" in features and color_mode is not None:
            sber_mode = HA_COLOR_MODE_TO_SBER_LIGHT_MODE.get(color_mode, "white")
            states.append({
                "key": "light_mode",
                "value": {"type": "ENUM", "enum_value": sber_mode},
            })

        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_cover_state_payload(
        self,
        device_id: str,
        open_set: str,
        open_state: str,
        open_percentage: int,
        battery: float | None = None,
    ) -> str:
        """Состояние рулонных штор / жалюзи.

        open_set        — open / close
        open_state      — open / close / opening / closing
        open_percentage — 0–100 (текущая позиция из HA current_position)
        battery         — заряд батареи 0–100 (опционально)

        Правило консистентности open_set / open_percentage:
          open_percentage > 0  → open_set = open
          open_percentage == 0 → open_set = close
        """
        # Гарантируем консистентность open_set ↔ open_percentage
        if open_percentage > 0 and open_set == "close":
            open_set = "open"
        elif open_percentage == 0 and open_set == "open":
            open_set = "close"

        states: list[dict] = [
            {"key": "online",           "value": {"type": "BOOL", "bool_value": True}},
            {"key": "open_set",         "value": {"type": "ENUM", "enum_value": open_set}},
            {"key": "open_state",       "value": {"type": "ENUM", "enum_value": open_state}},
            {"key": "open_percentage",  "value": {"type": "INTEGER", "integer_value": open_percentage}},
        ]
        if battery is not None:
            try:
                states.append({
                    "key": "battery_percentage",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(battery))))},
                })
            except (ValueError, TypeError):
                pass
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_water_leak_state_payload(
        self,
        device_id: str,
        leak_detected: bool,
        battery: float | None = None,
    ) -> str:
        """Состояние датчика протечки.

        leak_detected — True если вода обнаружена (HA state == 'on')
        battery       — заряд батареи 0–100 (опционально)
        """
        states: list[dict] = [
            {"key": "online",           "value": {"type": "BOOL", "bool_value": True}},
            {"key": "water_leak_state", "value": {"type": "BOOL", "bool_value": leak_detected}},
        ]
        if battery is not None:
            try:
                states.append({
                    "key": "battery_percentage",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(battery))))},
                })
            except (ValueError, TypeError):
                pass
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_sensor_door_state_payload(
        self,
        device_id: str,
        is_open: bool,
        battery: float | None = None,
        tamper: bool | None = None,
    ) -> str:
        """Состояние датчика открытия двери/окна.

        is_open — True если дверь открыта (HA binary_sensor state == 'on')
        battery — заряд батареи 0–100 (опционально)
        tamper  — сигнализация о вскрытии (опционально)
        """
        doorcontact = "open" if is_open else "close"
        states: list[dict] = [
            {"key": "online",            "value": {"type": "BOOL", "bool_value": True}},
            {"key": "doorcontact_state", "value": {"type": "BOOL", "bool_value": is_open}},
        ]
        if battery is not None:
            try:
                states.append({
                    "key": "battery_percentage",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(battery))))},
                })
            except (ValueError, TypeError):
                pass
        if tamper is not None:
            states.append({
                "key": "tamper_alarm",
                "value": {"type": "BOOL", "bool_value": tamper},
            })
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_sensor_pir_state_payload(
        self,
        device_id: str,
        motion: bool,
        battery: float | None = None,
    ) -> str:
        """Состояние датчика движения."""
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
            {"key": "pir_state", "value": {"type": "BOOL", "bool_value": motion}},
        ]
        if battery is not None:
            try:
                states.append({
                    "key": "battery_percentage",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(battery))))},
                })
            except (ValueError, TypeError):
                pass
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_sensor_air_state_payload(
        self,
        device_id: str,
        temperature: float | None = None,
        humidity: float | None = None,
        co2: float | None = None,
        pm25: float | None = None,
        tvoc: float | None = None,
        battery: float | None = None,
        signal_strength: float | None = None,
    ) -> str:
        """Состояние датчика качества воздуха.

        temperature    — температура, °C (передаётся × 10)
        humidity       — влажность, % (0–100)
        co2            — концентрация CO₂, ppm
        pm25           — концентрация PM2.5, мкг/м³
        tvoc           — концентрация TVOC, ppb
        battery        — заряд батареи 0–100
        signal_strength — сила сигнала: low/medium/high
        """
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
        ]

        if temperature is not None:
            try:
                states.append({
                    "key": "temperature",
                    "value": {"type": "INTEGER", "integer_value": round(float(temperature) * 10)},
                })
            except (ValueError, TypeError):
                pass

        if humidity is not None:
            try:
                states.append({
                    "key": "humidity",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(humidity))))},
                })
            except (ValueError, TypeError):
                pass

        if co2 is not None:
            try:
                states.append({
                    "key": "co2",
                    "value": {"type": "INTEGER", "integer_value": round(float(co2))},
                })
            except (ValueError, TypeError):
                pass

        if pm25 is not None:
            try:
                states.append({
                    "key": "pm2_5",
                    "value": {"type": "INTEGER", "integer_value": round(float(pm25))},
                })
            except (ValueError, TypeError):
                pass

        if tvoc is not None:
            try:
                states.append({
                    "key": "tvoc_float",
                    "value": {"type": "FLOAT", "float_value": round(float(tvoc), 1)},
                })
            except (ValueError, TypeError):
                pass

        if battery is not None:
            try:
                states.append({
                    "key": "battery_percentage",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(battery))))},
                })
            except (ValueError, TypeError):
                pass

        if signal_strength is not None:
            states.append({
                "key": "signal_strength",
                "value": {"type": "ENUM", "enum_value": self._signal_to_enum(signal_strength)},
            })

        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_smoke_state_payload(
        self,
        device_id: str,
        smoke_detected: bool,
        battery: float | None = None,
        alarm_mute: bool | None = None,
    ) -> str:
        """Состояние датчика дыма.

        smoke_detected — True если дым обнаружен (HA binary_sensor state == 'on')
        battery        — заряд батареи 0–100, из sensor с device_class battery
        alarm_mute     — звуковое оповещение выключено (switch/input_boolean в состоянии on)
        """
        states: list[dict] = [
            {"key": "online",      "value": {"type": "BOOL", "bool_value": True}},
            {"key": "smoke_state", "value": {"type": "BOOL", "bool_value": smoke_detected}},
        ]
        if battery is not None:
            try:
                states.append({
                    "key": "battery_percentage",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(battery))))},
                })
            except (ValueError, TypeError):
                pass
        if alarm_mute is not None:
            states.append({
                "key": "alarm_mute",
                "value": {"type": "BOOL", "bool_value": alarm_mute},
            })
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_kettle_state_payload(
        self,
        device_id: str,
        is_on: bool,
        current_temp: float | None = None,
        target_temp: float | None = None,
        water_level: float | None = None,
        water_low: bool | None = None,
    ) -> str:
        """Состояние чайника.

        is_on        — включён/выключен (on_off)
        current_temp — текущая температура воды 0–100 °C (kitchen_water_temperature)
        target_temp  — целевая температура 0–100 °C (kitchen_water_temperature_set)
        water_level  — уровень воды в литрах (kitchen_water_level)
        water_low    — вода закончилась (kitchen_water_low_level)
        """
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
            {"key": "on_off", "value": {"type": "BOOL", "bool_value": is_on}},
        ]
        if current_temp is not None:
            try:
                states.append({
                    "key": "kitchen_water_temperature",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(current_temp))))},
                })
            except (ValueError, TypeError):
                pass
        if target_temp is not None:
            try:
                states.append({
                    "key": "kitchen_water_temperature_set",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(target_temp))))},
                })
            except (ValueError, TypeError):
                pass
        if water_level is not None:
            try:
                states.append({
                    "key": "kitchen_water_level",
                    "value": {"type": "FLOAT", "float_value": round(float(water_level), 2)},
                })
            except (ValueError, TypeError):
                pass
        if water_low is not None:
            states.append({
                "key": "kitchen_water_low_level",
                "value": {"type": "BOOL", "bool_value": water_low},
            })
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_tv_state_payload(
        self,
        device_id: str,
        is_on: bool,
        volume: int | None = None,
        muted: bool | None = None,
    ) -> str:
        """Состояние телевизора.

        is_on  — включён/выключен (on_off)
        volume — громкость 0–100 (volume_int); None — не передавать
        muted  — бесшумный режим (mute); None — не передавать
        """
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
            {"key": "on_off", "value": {"type": "BOOL", "bool_value": is_on}},
        ]
        if muted is not None:
            states.append({"key": "mute", "value": {"type": "BOOL", "bool_value": bool(muted)}})
        if volume is not None:
            try:
                states.append({
                    "key": "volume_int",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, int(volume)))},
                })
            except (ValueError, TypeError):
                pass
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_air_purifier_state_payload(
        self,
        device_id: str,
        is_on: bool,
        online: bool = True,
        air_flow_power: str | None = None,
        bool_states: dict[str, bool] | None = None,
    ) -> str:
        """Состояние очистителя воздуха.

        is_on          — включён/выключен (on_off)
        online         — доступность (online)
        air_flow_power — скорость в терминах Сбера (hvac_air_flow_power); None — не передавать
        bool_states    — {ключ функции Сбера: bool}: hvac_night_mode, hvac_ionization,
                         hvac_aromatization, hvac_decontaminate, hvac_replace_filter,
                         hvac_replace_ionizator (только те, по которым есть данные)
        """
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": bool(online)}},
            {"key": "on_off", "value": {"type": "BOOL", "bool_value": is_on}},
        ]
        if air_flow_power:
            states.append({
                "key": "hvac_air_flow_power",
                "value": {"type": "ENUM", "enum_value": air_flow_power},
            })
        for key, value in (bool_states or {}).items():
            states.append({"key": key, "value": {"type": "BOOL", "bool_value": bool(value)}})
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_humidifier_state_payload(
        self,
        device_id: str,
        is_on: bool,
        current_humidity: float | None = None,
        target_humidity: float | None = None,
        air_flow_power: str | None = None,
        replace_filter: bool | None = None,
        water_percentage: float | None = None,
    ) -> str:
        """Состояние увлажнителя воздуха.

        is_on            — включён/выключён
        current_humidity — текущая влажность 0–100 (humidity)
        target_humidity  — целевая влажность 0–100 (hvac_humidity_set)
        air_flow_power   — скорость вентилятора в терминах Сбера (hvac_air_flow_power)
        replace_filter   — нужно ли менять фильтр, bool (hvac_replace_filter)
        water_percentage — уровень воды в баке 0–100 (hvac_water_percentage)
        """
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
            {"key": "on_off", "value": {"type": "BOOL", "bool_value": is_on}},
        ]
        if current_humidity is not None:
            try:
                states.append({
                    "key": "humidity",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(current_humidity))))},
                })
            except (ValueError, TypeError):
                pass
        if target_humidity is not None:
            try:
                states.append({
                    "key": "hvac_humidity_set",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(target_humidity))))},
                })
            except (ValueError, TypeError):
                pass
        if air_flow_power:
            states.append({
                "key": "hvac_air_flow_power",
                "value": {"type": "ENUM", "enum_value": air_flow_power},
            })
        if replace_filter is not None:
            states.append({
                "key": "hvac_replace_filter",
                "value": {"type": "BOOL", "bool_value": replace_filter},
            })
        if water_percentage is not None:
            try:
                states.append({
                    "key": "hvac_water_percentage",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(water_percentage))))},
                })
            except (ValueError, TypeError):
                pass
        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    def build_sensor_temp_state_payload(
        self,
        device_id: str,
        temperature: float | None,
        humidity: float | None,
        battery: float | None,
    ) -> str:
        """Состояние датчика температуры/влажности.

        Параметры которые равны None не включаются в payload.
        Температура передаётся умноженной на 10 (21.5°C → 215).
        """
        states: list[dict] = [
            {"key": "online", "value": {"type": "BOOL", "bool_value": True}}
        ]

        if temperature is not None:
            try:
                # Сбер хранит температуру как целое число × 10
                states.append({
                    "key": "temperature",
                    "value": {"type": "INTEGER", "integer_value": round(float(temperature) * 10)},
                })
            except (ValueError, TypeError):
                pass

        if humidity is not None:
            try:
                # Влажность в процентах, зажатая в диапазон 0–100
                states.append({
                    "key": "humidity",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(humidity))))},
                })
            except (ValueError, TypeError):
                pass

        if battery is not None:
            try:
                # Заряд батареи в процентах 0–100
                states.append({
                    "key": "battery_percentage",
                    "value": {"type": "INTEGER", "integer_value": max(0, min(100, round(float(battery))))},
                })
            except (ValueError, TypeError):
                pass

        return json.dumps({"devices": {device_id: {"states": states}}}, ensure_ascii=False)

    @staticmethod
    def _signal_to_enum(val: Any) -> str:
        """Переводит числовой уровень сигнала в строковый enum Сбера.

        < 30  → "low"
        30–70 → "medium"
        > 70  → "high"
        """
        try:
            v = float(val)
        except (ValueError, TypeError):
            return "low"
        if v < SIGNAL_STRENGTH_LOW_THRESHOLD:
            return "low"
        if v > SIGNAL_STRENGTH_HIGH_THRESHOLD:
            return "high"
        return "medium"
