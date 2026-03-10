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
        elif device_type == "scenario_button":
            # Сценарные кнопки только отправляют события в Сбер, команды не принимают
            _LOGGER.debug("Команда для сценарной кнопки %s проигнорирована", device.get("id"))
        elif device_type == "hvac_ac":
            await self._handle_hvac_ac_command(device, states)
        elif device_type == "vacuum_cleaner":
            await self._handle_vacuum_command(device, states)
        elif device_type == "valve":
            await self._handle_valve_command(device, states)
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

    async def _handle_hvac_ac_command(self, device: dict, states: list) -> None:
        """Обрабатывает команды управления кондиционером от Сбера.

        Поддерживаемые команды:
          on_off         — включить/выключить (climate.turn_on / climate.turn_off)
          hvac_temp_set  — установить целевую температуру (climate.set_temperature)
          hvac_work_mode — установить режим работы (climate.set_hvac_mode)
        """
        from .const import SBER_HVAC_MODE_TO_HA

        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")

        if not entity_id:
            _LOGGER.error("Кондиционер %s: не задан entity_id", device.get("id"))
            return

        for state in states:
            key     = state.get("key")
            val_obj = state.get("value", {})

            if key == "on_off":
                raw = val_obj.get("bool_value")
                if isinstance(raw, bool):
                    is_on = raw
                elif isinstance(raw, str):
                    is_on = raw.lower() in ("true", "1", "on")
                else:
                    is_on = False
                service = "turn_on" if is_on else "turn_off"
                _LOGGER.info("HVAC %s: on_off=%s → climate.%s", device.get("id"), is_on, service)
                await self._hass.services.async_call(
                    "climate", service, {"entity_id": entity_id}, blocking=False
                )

            elif key == "hvac_temp_set":
                temp = val_obj.get("integer_value")
                if temp is not None:
                    try:
                        temp_f = float(temp)
                        _LOGGER.info("HVAC %s: set_temperature=%.1f", device.get("id"), temp_f)
                        await self._hass.services.async_call(
                            "climate", "set_temperature",
                            {"entity_id": entity_id, "temperature": temp_f},
                            blocking=False,
                        )
                    except (ValueError, TypeError):
                        _LOGGER.warning("HVAC %s: невалидная температура: %s", device.get("id"), temp)

            elif key == "hvac_work_mode":
                sber_mode = val_obj.get("enum_value", "")
                ha_mode   = SBER_HVAC_MODE_TO_HA.get(sber_mode)
                if ha_mode:
                    _LOGGER.info("HVAC %s: set_hvac_mode=%s (sber=%s)", device.get("id"), ha_mode, sber_mode)
                    await self._hass.services.async_call(
                        "climate", "set_hvac_mode",
                        {"entity_id": entity_id, "hvac_mode": ha_mode},
                        blocking=False,
                    )
                else:
                    _LOGGER.warning(
                        "HVAC %s: неизвестный режим Сбера '%s'", device.get("id"), sber_mode
                    )

    async def _handle_vacuum_command(self, device: dict, states: list) -> None:
        """Обрабатывает команды управления пылесосом от Сбера.

        Поддерживаемые команды (vacuum_cleaner_command):
          start          → vacuum.start
          resume         → vacuum.start
          pause          → vacuum.pause
          return_to_dock → vacuum.return_to_base
        """
        from .const import SBER_VACUUM_COMMAND_TO_HA

        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")

        if not entity_id:
            _LOGGER.error("Пылесос %s: не задан entity_id", device.get("id"))
            return

        for state in states:
            key = state.get("key")
            if key != "vacuum_cleaner_command":
                continue

            sber_cmd = state.get("value", {}).get("enum_value", "")
            ha_call  = SBER_VACUUM_COMMAND_TO_HA.get(sber_cmd)

            if ha_call:
                domain, service = ha_call
                _LOGGER.info(
                    "Пылесос %s: команда '%s' → %s.%s",
                    device.get("id"), sber_cmd, domain, service,
                )
                await self._hass.services.async_call(
                    domain, service, {"entity_id": entity_id}, blocking=False
                )
            else:
                _LOGGER.warning(
                    "Пылесос %s: неизвестная команда '%s'",
                    device.get("id"), sber_cmd,
                )

    async def _handle_valve_command(self, device: dict, states: list) -> None:
        """Обрабатывает команды управления краном от Сбера.

        open_set:
          open  → valve.open_valve  / switch.turn_on
          close → valve.close_valve / switch.turn_off
          stop  → valve.stop_valve  (только для domain=valve)
        """
        from .const import SBER_VALVE_COMMAND_TO_HA_VALVE, SBER_VALVE_COMMAND_TO_HA_SWITCH

        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")
        if not entity_id:
            _LOGGER.error("Кран %s: не задан entity_id", device.get("id"))
            return

        domain = entity_id.split(".")[0]

        for state in states:
            if state.get("key") != "open_set":
                continue

            sber_cmd = state.get("value", {}).get("enum_value", "")

            if domain == "valve":
                ha_call = SBER_VALVE_COMMAND_TO_HA_VALVE.get(sber_cmd)
            else:
                ha_call = SBER_VALVE_COMMAND_TO_HA_SWITCH.get(sber_cmd)

            if ha_call:
                d, service = ha_call
                _LOGGER.info(
                    "Кран %s: команда '%s' → %s.%s",
                    device.get("id"), sber_cmd, d, service,
                )
                await self._hass.services.async_call(
                    d, service, {"entity_id": entity_id}, blocking=False
                )
            else:
                _LOGGER.warning(
                    "Кран %s: команда '%s' не поддерживается для домена '%s'",
                    device.get("id"), sber_cmd, domain,
                )
