"""Обработчик команд от Сбера → вызов сервисов Home Assistant.

Когда пользователь нажимает кнопку в приложении Сбера, брокер присылает
команду вида: {"key": "on_off", "value": {"type": "BOOL", "bool_value": true}}

Этот модуль переводит команду в вызов соответствующего сервиса HA
в зависимости от типа устройства и домена сущности.

Маппинг доменов → сервисы:
  switch, input_boolean, light  → homeassistant.turn_on / turn_off
  script                        → script.<name> (запуск сценария)
  button, input_button          → button.press / input_button.press
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class HACommandHandler:
    """Выполняет команды Сбера через сервисы HA."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def async_handle_command(self, device: dict, states: list) -> None:
        """Обрабатывает список команд для устройства.

        states — список объектов вида:
        [{"key": "on_off", "value": {"type": "BOOL", "bool_value": true}}]
        """
        device_type = device.get("device_type")

        if device_type == "relay":
            await self._handle_relay_command(device, states)
        elif device_type == "sensor_temp":
            # Датчики не управляются командами — игнорируем
            _LOGGER.debug("Команда для датчика %s проигнорирована", device.get("id"))
        else:
            _LOGGER.warning(
                "Команда для устройства неизвестного типа '%s': %s",
                device_type, device.get("id"),
            )

    async def _handle_relay_command(self, device: dict, states: list) -> None:
        """Обрабатывает команду включения/выключения реле."""
        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")

        if not entity_id:
            _LOGGER.error("Реле %s: не задан entity_id", device.get("id"))
            return

        domain = entity_id.split(".")[0]

        # Ищем команду on_off в списке состояний.
        # Протокол Сбера: bool_value=true → включить, отсутствие bool_value → выключить
        on_off_value = None
        for state in states:
            if state.get("key") == "on_off":
                val_obj = state.get("value", {})
                raw = val_obj.get("bool_value")
                if isinstance(raw, bool):
                    on_off_value = raw
                elif isinstance(raw, str):
                    on_off_value = raw.lower() in ("true", "1", "on")
                elif isinstance(raw, int):
                    on_off_value = bool(raw)
                else:
                    # bool_value отсутствует — Сбер сигнализирует о выключении
                    on_off_value = False
                _LOGGER.info(
                    "Реле %s: on_off raw=%r → интерпретируем как %s",
                    device.get("id"), raw, on_off_value,
                )
                break

        if on_off_value is None:
            _LOGGER.warning(
                "Реле %s: команда on_off не найдена в states: %s",
                device.get("id"), states,
            )
            return

        _LOGGER.info(
            "Выполняем команду для %s (%s): on_off=%s",
            entity_id, domain, on_off_value,
        )

        if domain == "script":
            # Сценарий запускается независимо от значения on_off
            script_name = entity_id.split(".", 1)[1]  # "script.my_scene" → "my_scene"
            await self._hass.services.async_call(
                "script", script_name, {}, blocking=False
            )

        elif domain in ("button", "input_button"):
            # Кнопки нажимаются независимо от значения on_off
            await self._hass.services.async_call(
                domain, "press", {"entity_id": entity_id}, blocking=False
            )

        elif domain in ("switch", "input_boolean", "light"):
            # Переключаемые сущности: turn_on или turn_off
            service = "turn_on" if on_off_value else "turn_off"
            await self._hass.services.async_call(
                "homeassistant", service, {"entity_id": entity_id}, blocking=False
            )

        elif domain == "media_player":
            # Медиаплеер: turn_on / turn_off через домен media_player
            service = "turn_on" if on_off_value else "turn_off"
            await self._hass.services.async_call(
                "media_player", service, {"entity_id": entity_id}, blocking=False
            )

        else:
            _LOGGER.warning(
                "Реле %s: домен '%s' не поддерживается для управления",
                device.get("id"), domain,
            )
