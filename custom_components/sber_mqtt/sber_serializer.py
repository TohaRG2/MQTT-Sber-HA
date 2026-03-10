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
    HA_HVAC_MODE_TO_SBER,
    SIGNAL_STRENGTH_LOW_THRESHOLD,
    SIGNAL_STRENGTH_HIGH_THRESHOLD,
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
        _LOGGER.warning("Неизвестный тип устройства: %s", device_type)
        return None

    def _relay_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для реле (switch, light, button и т.д.)."""
        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_relay",
                "manufacturer": MANUFACTURER,
                "model": "Model_relay",
                "category": DEVICE_TYPE_RELAY,
                "features": ["online", "on_off"],
            },
            "model_id": "",
        }
        # Комната опциональна — добавляем только если задана
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
        if attrs.get("signal_entity"):
            features.append("signal_strength")

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
                "allowed_values": {
                    "button_event": {
                        "type": "ENUM",
                        "enum_values": {
                            "values": ["click", "double_click"],
                        },
                    }
                },
            },
            "model_id": "",
        }
        if device.get("room"):
            entry["room"] = device["room"]
        return entry

    def _hvac_ac_config(self, device_id: str, device: dict) -> dict:
        """Конфиг для кондиционера (hvac_ac).

        Обязательные функции: online, on_off, hvac_temp_set.
        Опциональные: hvac_work_mode, temperature (если задан датчик текущей температуры).
        """
        attrs = device.get("attributes", {})
        features = ["online", "on_off", "hvac_temp_set", "hvac_work_mode"]
        if attrs.get("temperature_entity"):
            features.append("temperature")

        entry = {
            "id": device_id,
            "name": device.get("name", device_id),
            "hw_version": HW_VERSION,
            "sw_version": SW_VERSION,
            "model": {
                "id": "ID_hvac_ac",
                "manufacturer": MANUFACTURER,
                "model": "Model_hvac_ac",
                "category": DEVICE_TYPE_HVAC_AC,
                "features": features,
            },
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
        payload = {
            "devices": {
                device_id: {
                    "states": [
                        {"key": "online", "value": {"type": "BOOL", "bool_value": True}},
                        {"key": "on_off", "value": {"type": "BOOL", "bool_value": is_on}},
                    ]
                }
            }
        }
        return json.dumps(payload, ensure_ascii=False)

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

    def build_hvac_ac_state_payload(
        self,
        device_id: str,
        is_on: bool,
        target_temp: float | None,
        work_mode: str | None,
        current_temp: float | None = None,
    ) -> str:
        """Состояние кондиционера.

        is_on         — включён/выключён
        target_temp   — целевая температура (hvac_temp_set), градусы °C
        work_mode     — режим работы в терминах Сбера: cooling/heating/ventilation/…
        current_temp  — текущая температура (temperature), если задан датчик; × 10
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

    def build_sensor_temp_state_payload(
        self,
        device_id: str,
        temperature: float | None,
        humidity: float | None,
        battery: float | None,
        signal: float | None,
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

        if signal is not None:
            # Уровень сигнала — enum: low / medium / high
            states.append({
                "key": "signal_strength",
                "value": {"type": "ENUM", "enum_value": self._signal_to_enum(signal)},
            })

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
