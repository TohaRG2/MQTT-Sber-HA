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

from .ha_helpers import _parse_bool, _parse_integer

_LOGGER = logging.getLogger(__name__)


class HACommandHandler:
    """Выполняет команды Сбера через сервисы HA."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._user_id: str | None = None

    def set_user_id(self, user_id: str | None) -> None:
        """Устанавливает пользователя HA, от имени которого выполняются команды."""
        self._user_id = user_id or None

    def _context(self) -> Any:
        """Возвращает Context с user_id, если задан."""
        from homeassistant.core import Context
        if self._user_id:
            return Context(user_id=self._user_id)
        return Context()

    async def _async_call(self, domain: str, service: str, service_data: dict, blocking: bool = False) -> None:
        """Вызывает сервис HA с контекстом пользователя Сбера."""
        await self._hass.services.async_call(
            domain, service, service_data,
            context=self._context(),
            blocking=blocking,
        )

    async def async_handle_command(self, device: dict, states: list) -> None:
        """Обрабатывает список команд для устройства.

        states — список объектов вида:
        [{"key": "on_off", "value": {"type": "BOOL", "bool_value": true}}]
        """
        device_type = device.get("device_type")
        device_id = device.get("id")

        _LOGGER.debug("CMD %s (%s): %s", device_id, device_type, states)

        # ── Управляемые устройства ───────────────────────────────────────
        if device_type == "relay":
            await self._handle_relay_command(device, states)
        elif device_type == "socket":
            await self._handle_relay_command(device, states)  # on_off — та же логика что у реле
        elif device_type == "light":
            await self._handle_light_command(device, states)
        elif device_type == "hvac_ac":
            await self._handle_hvac_ac_command(device, states)
        elif device_type == "humidifier":
            await self._handle_humidifier_command(device, states)
        elif device_type == "kettle":
            await self._handle_kettle_command(device, states)
        elif device_type == "tv":
            await self._handle_tv_command(device, states)
        elif device_type == "air_purifier":
            await self._handle_air_purifier_command(device, states)
        elif device_type == "vacuum_cleaner":
            await self._handle_vacuum_command(device, states)
        elif device_type == "valve":
            await self._handle_valve_command(device, states)
        elif device_type == "cover":
            await self._handle_cover_command(device, states)
        elif device_type == "hvac_radiator":
            await self._handle_hvac_radiator_command(device, states)
        elif device_type == "hvac_fan":
            await self._handle_hvac_fan_command(device, states)
        elif device_type == "intercom":
            await self._handle_intercom_command(device, states)

        # ── Датчики — команды не принимают ───────────────────────────────
        elif device_type in ("sensor_temp", "water_leak", "smoke", "sensor_door", "sensor_air", "sensor_pir"):
            _LOGGER.debug("Команда для датчика %s проигнорирована", device.get("id"))

        # ── Сценарные кнопки — только отправляют события в Сбер ─────────
        elif device_type == "scenario_button" or device_type == "event_button":
            _LOGGER.debug("Команда для сценарной кнопки %s проигнорирована", device.get("id"))

        else:
            _LOGGER.warning(
                "Команда для устройства неизвестного типа '%s': %s",
                device_type, device.get("id"),
            )

    def _track_ha_command(self, device: dict, states: list, domain: str, service: str, data: dict) -> None:
        """Записать команду HA в буфер отслеживания DevTools."""
        try:
            from .api_devtools import devtools_track_ha_command
            device_id = device.get("id")
            sber_cmd = {"device_id": device_id, "device_type": device.get("device_type"), "states": states}
            ha_call = {"domain": domain, "service": service, "data": data}
            devtools_track_ha_command(device_id, sber_cmd, ha_call)
        except Exception:
            pass

    async def _handle_relay_command(self, device: dict, states: list) -> None:
        """Обрабатывает команду включения/выключения реле."""
        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")

        if not entity_id:
            _LOGGER.error("Реле %s: не задан entity_id", device.get("id"))
            return

        domain = entity_id.split(".")[0]

        on_off_value = None
        for state in states:
            if state.get("key") == "on_off":
                val_obj = state.get("value", {})
                on_off_value = _parse_bool(val_obj)
                _LOGGER.debug(
                    "Реле %s: on_off=%r, domain=%s, entity_id=%s",
                    device.get("id"), on_off_value, domain, entity_id,
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

        is_on = on_off_value

        if domain == "script":
            # Сценарий запускается независимо от значения on_off
            script_name = entity_id.split(".", 1)[1]  # "script.my_scene" → "my_scene"
            self._track_ha_command(device, states, "script", script_name, {})
            await self._async_call(
                "script", script_name, {}, blocking=False
            )

        elif domain == "automation":
            if is_on:
                data = {"entity_id": entity_id}
                trigger_id = attrs.get("trigger_id")
                if trigger_id:
                    data["variables"] = {"manual_trigger_id": trigger_id}
                self._track_ha_command(device, states, "automation", "trigger", data)
                await self._async_call(
                    "automation", "trigger", data, blocking=False
                )
            # else: на выключение ничего не делаем

        elif domain in ("button", "input_button"):
            # Кнопки нажимаются независимо от значения on_off
            self._track_ha_command(device, states, domain, "press", {"entity_id": entity_id})
            await self._async_call(
                domain, "press", {"entity_id": entity_id}, blocking=False
            )

        elif domain in ("switch", "input_boolean", "light"):
            # Переключаемые сущности: turn_on или turn_off
            service = "turn_on" if on_off_value else "turn_off"
            self._track_ha_command(device, states, "homeassistant", service, {"entity_id": entity_id})
            await self._async_call(
                "homeassistant", service, {"entity_id": entity_id}, blocking=False
            )

        elif domain == "media_player":
            # Медиаплеер: turn_on / turn_off через домен media_player
            service = "turn_on" if on_off_value else "turn_off"
            self._track_ha_command(device, states, "media_player", service, {"entity_id": entity_id})
            await self._async_call(
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
          on_off              — включить/выключить (climate.turn_on / climate.turn_off)
          hvac_temp_set       — установить целевую температуру (climate.set_temperature)
          hvac_work_mode      — установить режим работы (climate.set_hvac_mode)
          hvac_air_flow_power — установить скорость вентилятора:
                                  auto/low/medium/high → climate.set_fan_mode
                                  turbo → climate.set_preset_mode(boost)
                                  quiet → climate.set_preset_mode(sleep)
        """
        from .const import SBER_HVAC_MODE_TO_HA, SBER_AIR_FLOW_TO_HA_AC

        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")

        if not entity_id:
            _LOGGER.error("Кондиционер %s: не задан entity_id", device.get("id"))
            return

        for state in states:
            key     = state.get("key")
            val_obj = state.get("value", {})

            if key == "on_off":
                is_on = _parse_bool(val_obj)
                service = "turn_on" if is_on else "turn_off"
                _LOGGER.info("HVAC %s: on_off=%s → climate.%s", device.get("id"), is_on, service)
                self._track_ha_command(device, states, "climate", service, {"entity_id": entity_id})
                await self._async_call(
                    "climate", service, {"entity_id": entity_id}, blocking=False
                )

            elif key == "hvac_temp_set":
                temp = _parse_integer(val_obj)
                try:
                    temp_f = float(temp)
                    _LOGGER.info("HVAC %s: set_temperature=%.1f", device.get("id"), temp_f)
                    self._track_ha_command(device, states, "climate", "set_temperature",
                                           {"entity_id": entity_id, "temperature": temp_f})
                    await self._async_call(
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
                    self._track_ha_command(device, states, "climate", "set_hvac_mode",
                                           {"entity_id": entity_id, "hvac_mode": ha_mode})
                    await self._async_call(
                        "climate", "set_hvac_mode",
                        {"entity_id": entity_id, "hvac_mode": ha_mode},
                        blocking=False,
                    )
                else:
                    _LOGGER.warning(
                        "HVAC %s: неизвестный hvac_work_mode '%s'", device.get("id"), sber_mode
                    )

            elif key == "hvac_air_flow_power":
                sber_flow = val_obj.get("enum_value", "")
                mapping   = SBER_AIR_FLOW_TO_HA_AC.get(sber_flow)
                if not mapping:
                    _LOGGER.warning(
                        "HVAC %s: неизвестный hvac_air_flow_power '%s'", device.get("id"), sber_flow
                    )
                    continue
                fan_mode, preset_mode = mapping
                if preset_mode and preset_mode != "none":
                    # turbo/quiet — через preset_mode
                    _LOGGER.info(
                        "HVAC %s: hvac_air_flow_power=%s → set_preset_mode(%s)",
                        device.get("id"), sber_flow, preset_mode,
                    )
                    self._track_ha_command(device, states, "climate", "set_preset_mode",
                                           {"entity_id": entity_id, "preset_mode": preset_mode})
                    await self._async_call(
                        "climate", "set_preset_mode",
                        {"entity_id": entity_id, "preset_mode": preset_mode},
                        blocking=False,
                    )
                elif fan_mode:
                    # auto/low/medium/high — через fan_mode, сбрасываем preset на none
                    _LOGGER.info(
                        "HVAC %s: hvac_air_flow_power=%s → set_fan_mode(%s)",
                        device.get("id"), sber_flow, fan_mode,
                    )
                    self._track_ha_command(device, states, "climate", "set_fan_mode",
                                           {"entity_id": entity_id, "fan_mode": fan_mode})
                    await self._async_call(
                        "climate", "set_fan_mode",
                        {"entity_id": entity_id, "fan_mode": fan_mode},
                        blocking=False,
                    )
                    # Сбрасываем preset в none чтобы не осталось boost/sleep
                    self._track_ha_command(device, states, "climate", "set_preset_mode",
                                           {"entity_id": entity_id, "preset_mode": "none"})
                    await self._async_call(
                        "climate", "set_preset_mode",
                        {"entity_id": entity_id, "preset_mode": "none"},
                        blocking=False,
                    )

            elif key == "hvac_air_flow_direction":
                from .const import SBER_AIR_FLOW_DIR_TO_HA
                sber_dir = val_obj.get("enum_value", "")
                ha_swing = SBER_AIR_FLOW_DIR_TO_HA.get(sber_dir)
                if ha_swing:
                    _LOGGER.info(
                        "HVAC %s: hvac_air_flow_direction=%s → set_swing_mode(%s)",
                        device.get("id"), sber_dir, ha_swing,
                    )
                    self._track_ha_command(device, states, "climate", "set_swing_mode",
                                           {"entity_id": entity_id, "swing_mode": ha_swing})
                    await self._async_call(
                        "climate", "set_swing_mode",
                        {"entity_id": entity_id, "swing_mode": ha_swing},
                        blocking=False,
                    )
                else:
                    _LOGGER.warning(
                        "HVAC %s: неизвестный hvac_air_flow_direction '%s'", device.get("id"), sber_dir
                    )

    async def _handle_hvac_radiator_command(self, device: dict, states: list) -> None:
        """Обрабатывает команды управления термоголовкой радиатора от Сбера.

        Поддерживаемые команды:
          on_off        → climate.turn_on / climate.turn_off
          hvac_temp_set → climate.set_temperature
        """
        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")

        for state in states:
            key      = state.get("key", "")
            val_obj = state.get("value", {})

            if key == "on_off":
                is_on = _parse_bool(val_obj)
                service = "turn_on" if is_on else "turn_off"
                _LOGGER.info("Radiator %s: on_off=%s → climate.%s", device.get("id"), is_on, service)
                self._track_ha_command(device, states, "climate", service, {"entity_id": entity_id})
                await self._async_call(
                    "climate", service, {"entity_id": entity_id}, blocking=False
                )

            elif key == "hvac_temp_set":
                temp = _parse_integer(val_obj)
                try:
                    temp_f = float(temp)
                    _LOGGER.info("Radiator %s: set_temperature=%.1f", device.get("id"), temp_f)
                    self._track_ha_command(device, states, "climate", "set_temperature",
                                           {"entity_id": entity_id, "temperature": temp_f})
                    await self._async_call(
                        "climate", "set_temperature",
                        {"entity_id": entity_id, "temperature": temp_f},
                        blocking=False,
                    )
                except (ValueError, TypeError):
                    _LOGGER.warning("Radiator %s: невалидная температура: %s", device.get("id"), temp)

    async def _handle_hvac_fan_command(self, device: dict, states: list) -> None:
        """Обрабатывает команды управления вентилятором / бризером от Сбера.

        Поддерживаемые команды:
          on_off              → fan.turn_on / fan.turn_off (или homeassistant.* для switch)
          hvac_air_flow_power → fan.set_percentage
        """
        from .const import SBER_AIR_FLOW_TO_FAN_PCT

        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")
        domain    = entity_id.split(".")[0] if entity_id else "fan"

        for state in states:
            key     = state.get("key", "")
            val_obj = state.get("value", {})

            if key == "on_off":
                is_on = _parse_bool(val_obj)
                if domain in ("switch", "input_boolean"):
                    svc_domain, service = "homeassistant", ("turn_on" if is_on else "turn_off")
                elif domain == "climate":
                    svc_domain, service = "climate", ("turn_on" if is_on else "turn_off")
                else:
                    svc_domain, service = "fan", ("turn_on" if is_on else "turn_off")
                _LOGGER.info("Fan %s: on_off=%s → %s.%s", device.get("id"), is_on, svc_domain, service)
                self._track_ha_command(device, states, svc_domain, service, {"entity_id": entity_id})
                await self._async_call(
                    svc_domain, service, {"entity_id": entity_id}, blocking=False
                )

            elif key == "hvac_air_flow_power":
                sber_flow = val_obj.get("enum_value", "")
                if domain == "climate":
                    # Для climate-бризера — set_fan_mode
                    fan_mode = sber_flow
                    _LOGGER.info("Fan %s(climate): hvac_air_flow_power=%s → set_fan_mode", device.get("id"), sber_flow)
                    self._track_ha_command(device, states, "climate", "set_fan_mode",
                                           {"entity_id": entity_id, "fan_mode": fan_mode})
                    await self._async_call(
                        "climate", "set_fan_mode",
                        {"entity_id": entity_id, "fan_mode": fan_mode},
                        blocking=False,
                    )
                elif domain == "fan":
                    pct = SBER_AIR_FLOW_TO_FAN_PCT.get(sber_flow)
                    if pct is not None:
                        _LOGGER.info("Fan %s: hvac_air_flow_power=%s → set_percentage=%d", device.get("id"), sber_flow, pct)
                        self._track_ha_command(device, states, "fan", "set_percentage",
                                               {"entity_id": entity_id, "percentage": pct})
                        await self._async_call(
                            "fan", "set_percentage",
                            {"entity_id": entity_id, "percentage": pct},
                            blocking=False,
                        )
                else:
                    _LOGGER.warning("Fan %s: неизвестная скорость '%s' или домен %s", device.get("id"), sber_flow, domain)

    async def _handle_intercom_command(self, device: dict, states: list) -> None:
        """Обрабатывает команды домофона: unlock → открыть дверь."""
        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")
        domain    = entity_id.split(".")[0] if entity_id else ""

        for state in states:
            key = state.get("key", "")
            if key == "unlock":
                val_obj = state.get("value", {})
                is_unlock = val_obj.get("bool_value", True) if val_obj.get("type") == "BOOL" else True
                if is_unlock:
                    if domain == "lock":
                        svc = "open"
                        self._track_ha_command(device, states, "lock", svc, {"entity_id": entity_id})
                        await self._async_call("lock", svc, {"entity_id": entity_id}, blocking=False)
                    else:
                        svc = "turn_on"
                        self._track_ha_command(device, states, "homeassistant", svc, {"entity_id": entity_id})
                        await self._async_call("homeassistant", svc, {"entity_id": entity_id}, blocking=False)

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
                self._track_ha_command(device, states, domain, service, {"entity_id": entity_id})
                await self._async_call(
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
                self._track_ha_command(device, states, d, service, {"entity_id": entity_id})
                await self._async_call(
                    d, service, {"entity_id": entity_id}, blocking=False
                )
            else:
                _LOGGER.warning(
                    "Кран %s: команда '%s' не поддерживается для домена '%s'",
                    device.get("id"), sber_cmd, domain,
                )

    async def _handle_light_command(self, device: dict, states: list) -> None:
        """Обрабатывает команды управления лампой от Сбера.

        on_off          → light.turn_on / light.turn_off
        light_brightness → light.turn_on(brightness=...)
        light_colour     → light.turn_on(hs_color=...)
        light_colour_temp → light.turn_on(color_temp=...)
        light_mode       → light.turn_on(color_mode=...)
        """
        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")
        if not entity_id:
            _LOGGER.error("Лампа %s: не задан entity_id", device.get("id"))
            return

        service_data: dict = {"entity_id": entity_id}
        service = "turn_on"
        requested_light_mode: str | None = None

        for state in states:
            key = state.get("key")
            val = state.get("value", {})

            if key == "on_off":
                # Сбер может прислать {"type": "BOOL"} без bool_value — это выключение
                raw = val.get("bool_value")
                if raw is None:
                    is_on = False
                elif isinstance(raw, bool):
                    is_on = raw
                elif isinstance(raw, str):
                    is_on = raw.lower() in ("true", "1", "on")
                else:
                    is_on = bool(raw)
                service = "turn_on" if is_on else "turn_off"

            elif key == "light_brightness":
                # Сбер 50–1000 → HA 0–255
                try:
                    from .const import LIGHT_BRIGHTNESS_MIN, LIGHT_BRIGHTNESS_MAX
                    sber_b = _parse_integer(val, LIGHT_BRIGHTNESS_MIN)
                    ha_brightness = round(
                        (sber_b - LIGHT_BRIGHTNESS_MIN)
                        / (LIGHT_BRIGHTNESS_MAX - LIGHT_BRIGHTNESS_MIN)
                        * 255
                    )
                    service_data["brightness"] = max(0, min(255, ha_brightness))
                except (ValueError, TypeError):
                    pass

            elif key == "light_colour":
                # Сбер HSV (h 0–360, s 0–1000, v 100–1000) → HA hs_color (h 0–360, s 0–100)
                # Цвет и температура взаимоисключающие — убираем температуру если была
                try:
                    cv = val.get("colour_value", {})
                    h  = float(cv.get("h", 0))
                    s  = float(cv.get("s", 1000)) / 10.0  # 0–1000 → 0–100
                    service_data.pop("color_temp_kelvin", None)
                    service_data.pop("color_temp", None)
                    service_data["hs_color"] = (h, s)
                    # v: 100–1000 → HA brightness 0–255
                    v = cv.get("v")
                    if v is not None:
                        v_norm = (float(v) - 100) / 900.0   # 100–1000 → 0.0–1.0
                        service_data["brightness"] = round(max(0.0, min(1.0, v_norm)) * 255)
                except (ValueError, TypeError):
                    pass

            elif key == "light_colour_temp":
                # Сбер 0–1000: 0 = тёплый (max_mireds), 1000 = холодный (min_mireds) — инвертировано.
                # Цвет и температура взаимоисключающие — убираем цвет если был.
                # Используем color_temp_kelvin если лампа его поддерживает, иначе color_temp (мирады).
                #
                # ВАЖНО: интерполяция всегда ведётся в мирадах, потому что HA→Sber
                # тоже интерполирует в мирадах (sber_serializer.py:908).
                # Если интерполировать в Кельвинах, обратное преобразование «прыгает».
                try:
                    sber_ct = _parse_integer(val, 0)
                    hass_state = self._hass.states.get(entity_id)
                    a = hass_state.attributes if hass_state else {}

                    service_data.pop("hs_color", None)
                    service_data.pop("rgb_color", None)
                    service_data.pop("xy_color", None)

                    min_k = a.get("min_color_temp_kelvin")
                    max_k = a.get("max_color_temp_kelvin")

                    if min_k is not None and max_k is not None:
                        # Переводим границы Кельвинов в мирады
                        mn = 1_000_000 / float(max_k)  # холодный → меньше мирад
                        mx = 1_000_000 / float(min_k)  # тёплый → больше мирад
                        # Линейная интерполяция в мирадах: 0→mx (тёплый), 1000→mn (холодный)
                        mireds = round(mx - (sber_ct / 1000.0) * (mx - mn))
                        mireds = max(int(mn), min(int(mx), mireds))
                        # Обратное преобразование в Кельвины для HA
                        kelvin = round(1_000_000 / mireds) if mireds > 0 else int(min_k)
                        kelvin = max(int(min_k), min(int(max_k), kelvin))
                        _LOGGER.info(
                            "Лампа %s: light.turn_on color_temp_kelvin=%d (sber=%d, mireds=%d)",
                            device.get("id"), kelvin, sber_ct, mireds,
                        )
                        service_data["color_temp_kelvin"] = kelvin
                    else:
                        mn = float(a.get("min_mireds", 153))
                        mx = float(a.get("max_mireds", 500))
                        mireds = round(mx - (sber_ct / 1000.0) * (mx - mn))
                        mireds = max(int(mn), min(int(mx), mireds))
                        _LOGGER.info(
                            "Лампа %s: light.turn_on color_temp=%d mireds (sber=%d)",
                            device.get("id"), mireds, sber_ct,
                        )
                        service_data["color_temp"] = mireds
                except (ValueError, TypeError):
                    pass

            elif key == "light_mode":
                # light_mode только переключает режим если нет явного цвета/температуры в команде.
                # Сохраняем запрошенный режим — применим после цикла если нужно.
                requested_light_mode = val.get("enum_value", "white")

        # Если пришёл только light_mode без явного цвета/температуры —
        # переключаем лампу в нужный режим минимальной командой
        colour_keys  = {"hs_color", "rgb_color", "xy_color"}
        temp_keys    = {"color_temp_kelvin", "color_temp"}
        has_colour   = bool(colour_keys & service_data.keys())
        has_temp     = bool(temp_keys   & service_data.keys())
        if requested_light_mode and not has_colour and not has_temp:
            if requested_light_mode == "colour":
                # Переключаем в цветовой режим — отправляем текущий hs_color лампы
                hass_state = self._hass.states.get(entity_id)
                if hass_state:
                    hs = hass_state.attributes.get("hs_color")
                    if hs:
                        service_data["hs_color"] = (float(hs[0]), float(hs[1]))
            else:
                # Переключаем в белый/температурный режим
                hass_state = self._hass.states.get(entity_id)
                if hass_state:
                    a = hass_state.attributes
                    min_k = a.get("min_color_temp_kelvin")
                    max_k = a.get("max_color_temp_kelvin")
                    if min_k and max_k:
                        # Берём текущую температуру или нейтральную
                        k = a.get("color_temp_kelvin") or round((float(min_k) + float(max_k)) / 2)
                        service_data["color_temp_kelvin"] = int(k)
                    else:
                        mn = float(a.get("min_mireds", 153))
                        mx = float(a.get("max_mireds", 500))
                        ct = a.get("color_temp") or round((mn + mx) / 2)
                        service_data["color_temp"] = int(ct)

        _LOGGER.info(
            "Лампа %s: %s.%s %s",
            device.get("id"), "light", service, service_data,
        )
        self._track_ha_command(device, states, "light", service, service_data)
        await self._async_call(
            "light", service, service_data, blocking=False
        )

    async def _handle_cover_command(self, device: dict, states: list) -> None:
        """Обрабатывает команды управления шторами/жалюзи от Сбера.

        open_set:
          open  → cover.open_cover
          close → cover.close_cover
          stop  → cover.stop_cover

        open_percentage:
          0–100 → cover.set_cover_position(position=...)
        """
        from .const import SBER_COVER_COMMAND_TO_HA

        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")
        if not entity_id:
            _LOGGER.error("Шторы %s: не задан entity_id", device.get("id"))
            return

        for state in states:
            key = state.get("key")
            val = state.get("value", {})

            if key == "open_set":
                sber_cmd = val.get("enum_value", "")
                ha_call  = SBER_COVER_COMMAND_TO_HA.get(sber_cmd)
                if ha_call:
                    domain, service = ha_call
                    _LOGGER.info(
                        "Шторы %s: команда '%s' → %s.%s",
                        device.get("id"), sber_cmd, domain, service,
                    )
                    self._track_ha_command(device, states, domain, service, {"entity_id": entity_id})
                    await self._async_call(
                        domain, service, {"entity_id": entity_id}, blocking=False
                    )
                else:
                    _LOGGER.warning("Шторы %s: неизвестная команда '%s'", device.get("id"), sber_cmd)

            elif key == "open_percentage":
                try:
                    pct = _parse_integer(val, 0)
                    pct = max(0, min(100, pct))
                    _LOGGER.info(
                        "Шторы %s: open_percentage=%s → cover.set_cover_position",
                        device.get("id"), pct,
                    )
                    self._track_ha_command(device, states, "cover", "set_cover_position",
                                           {"entity_id": entity_id, "position": pct})
                    await self._async_call(
                        "cover", "set_cover_position",
                        {"entity_id": entity_id, "position": pct},
                        blocking=False,
                    )
                except (ValueError, TypeError):
                    pass

    async def _handle_tv_command(self, device: dict, states: list) -> None:
        """Обрабатывает команды управления телевизором от Сбера.

        Источник: сущность домена media_player.

        Поддерживаемые команды:
          on_off     — включить/выключить (media_player.turn_on / turn_off)
          mute       — бесшумный режим (media_player.volume_mute)
          volume_int — громкость 0–100 → media_player.volume_set (0.0–1.0)
          volume     — «громче»/«тише» ("+"/"-") → media_player.volume_up / volume_down;
                       если сущность не умеет шаг громкости, но умеет volume_set —
                       считаем новую громкость сами (±5%)
        """
        from .const import (
            SBER_TV_VOLUME_UP,
            SBER_TV_VOLUME_DOWN,
            TV_FEATURE_VOLUME_SET,
            TV_FEATURE_VOLUME_STEP,
            TV_VOLUME_FALLBACK_STEP,
        )

        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")
        dev_id    = device.get("id")

        if not entity_id:
            _LOGGER.error("ТВ %s: не задан entity_id", dev_id)
            return

        for state in states:
            key     = state.get("key")
            val_obj = state.get("value", {}) or {}

            if key == "on_off":
                is_on   = _parse_bool(val_obj)
                service = "turn_on" if is_on else "turn_off"
                _LOGGER.info("ТВ %s: on_off=%s → media_player.%s", dev_id, is_on, service)
                data = {"entity_id": entity_id}
                self._track_ha_command(device, states, "media_player", service, data)
                await self._async_call(
                    "media_player", service, data, blocking=False
                )

            elif key == "mute":
                # Протокол Сбера: отсутствие bool_value трактуется как false (звук включить)
                muted = _parse_bool(val_obj)
                _LOGGER.info("ТВ %s: mute=%s → media_player.volume_mute", dev_id, muted)
                data = {"entity_id": entity_id, "is_volume_muted": muted}
                self._track_ha_command(device, states, "media_player", "volume_mute", data)
                await self._async_call(
                    "media_player", "volume_mute", data, blocking=False
                )

            elif key == "volume_int":
                pct   = max(0, min(100, _parse_integer(val_obj, 0)))
                level = round(pct / 100, 2)
                _LOGGER.info("ТВ %s: volume_int=%d → media_player.volume_set(%.2f)", dev_id, pct, level)
                data = {"entity_id": entity_id, "volume_level": level}
                self._track_ha_command(device, states, "media_player", "volume_set", data)
                await self._async_call(
                    "media_player", "volume_set", data, blocking=False
                )

            elif key == "volume":
                direction = str(val_obj.get("enum_value", "")).strip().lower()
                if direction in SBER_TV_VOLUME_UP:
                    step_up = True
                elif direction in SBER_TV_VOLUME_DOWN:
                    step_up = False
                else:
                    _LOGGER.warning("ТВ %s: неизвестная команда volume '%s'", dev_id, direction)
                    continue

                # Возможности берём из живого состояния сущности
                ha_state = self._hass.states.get(entity_id)
                try:
                    sf = int(ha_state.attributes.get("supported_features") or 0) if ha_state else 0
                except (ValueError, TypeError):
                    sf = 0

                if sf & TV_FEATURE_VOLUME_STEP or not (sf & TV_FEATURE_VOLUME_SET):
                    # Штатный шаг громкости (также запасной вариант, если флаги
                    # неизвестны — пусть HA сам вернёт ошибку, если не поддерживается)
                    service = "volume_up" if step_up else "volume_down"
                    _LOGGER.info("ТВ %s: volume '%s' → media_player.%s", dev_id, direction, service)
                    data = {"entity_id": entity_id}
                    self._track_ha_command(device, states, "media_player", service, data)
                    await self._async_call(
                        "media_player", service, data, blocking=False
                    )
                else:
                    # Нет volume_up/down, но есть volume_set — считаем сами
                    current = ha_state.attributes.get("volume_level") if ha_state else None
                    try:
                        current = float(current)
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            "ТВ %s: volume '%s' — текущая громкость неизвестна, команда пропущена",
                            dev_id, direction,
                        )
                        continue
                    delta = TV_VOLUME_FALLBACK_STEP if step_up else -TV_VOLUME_FALLBACK_STEP
                    level = round(max(0.0, min(1.0, current + delta)), 2)
                    _LOGGER.info(
                        "ТВ %s: volume '%s' → media_player.volume_set(%.2f)", dev_id, direction, level
                    )
                    data = {"entity_id": entity_id, "volume_level": level}
                    self._track_ha_command(device, states, "media_player", "volume_set", data)
                    await self._async_call(
                        "media_player", "volume_set", data, blocking=False
                    )

            else:
                _LOGGER.debug("ТВ %s: команда '%s' не поддерживается, пропущена", dev_id, key)

    async def _handle_air_purifier_command(self, device: dict, states: list) -> None:
        """Обрабатывает команды управления очистителем воздуха от Сбера.

        Очиститель в HA — набор отдельных сущностей, поэтому каждая функция
        Сбера управляет «своей» сущностью, выбранной пользователем в мастере.

        Поддерживаемые команды:
          on_off              — <domain>.turn_on / turn_off для сущности питания
          hvac_air_flow_power — скорость → select.select_option (по speed_map)
          hvac_night_mode, hvac_ionization, hvac_aromatization, hvac_decontaminate
                              — switch/input_boolean: turn_on/turn_off;
                                select/input_select: выбор опции «вкл» / «выкл»
        hvac_replace_filter и hvac_replace_ionizator — только состояние, команды игнорируются.
        """
        from .air_purifier import clean_speed_map, domain_of
        from .const import AIR_PURIFIER_BOOL_FEATURES, AIR_PURIFIER_SELECT_DOMAINS

        attrs  = device.get("attributes", {})
        dev_id = device.get("id")
        sber_to_name = {v: k for k, v in AIR_PURIFIER_BOOL_FEATURES.items()}

        async def _call(domain: str, service: str, data: dict) -> None:
            self._track_ha_command(device, states, domain, service, data)
            await self._async_call(domain, service, data, blocking=False)

        for state in states:
            key     = state.get("key")
            val_obj = state.get("value", {}) or {}

            if key == "on_off":
                entity_id = attrs.get("entity_id", "")
                if not entity_id:
                    _LOGGER.error("Очиститель %s: не задан entity_id питания", dev_id)
                    continue
                is_on   = _parse_bool(val_obj)
                service = "turn_on" if is_on else "turn_off"
                domain  = domain_of(entity_id)
                _LOGGER.info("Очиститель %s: on_off=%s → %s.%s", dev_id, is_on, domain, service)
                await _call(domain, service, {"entity_id": entity_id})

            elif key == "hvac_air_flow_power":
                entity_id = attrs.get("speed_entity", "")
                sber_val  = str(val_obj.get("enum_value", "")).strip().lower()
                option    = clean_speed_map(attrs).get(sber_val)
                if not entity_id or not option:
                    _LOGGER.warning(
                        "Очиститель %s: скорость '%s' не сопоставлена с опцией select",
                        dev_id, sber_val,
                    )
                    continue
                domain = domain_of(entity_id)
                _LOGGER.info("Очиститель %s: скорость %s → %s.select_option(%s)", dev_id, sber_val, domain, option)
                await _call(domain, "select_option", {"entity_id": entity_id, "option": option})

            elif key in sber_to_name:
                name      = sber_to_name[key]
                entity_id = attrs.get(f"{name}_entity", "")
                if not entity_id:
                    _LOGGER.warning("Очиститель %s: для %s не выбрана сущность", dev_id, key)
                    continue
                is_on  = _parse_bool(val_obj)
                domain = domain_of(entity_id)
                if domain in AIR_PURIFIER_SELECT_DOMAINS:
                    option = attrs.get(f"{name}_on_option" if is_on else f"{name}_off_option")
                    if not option:
                        _LOGGER.warning(
                            "Очиститель %s: %s=%s — не задана опция select для этого значения",
                            dev_id, key, is_on,
                        )
                        continue
                    _LOGGER.info("Очиститель %s: %s=%s → %s.select_option(%s)", dev_id, key, is_on, domain, option)
                    await _call(domain, "select_option", {"entity_id": entity_id, "option": option})
                else:
                    service = "turn_on" if is_on else "turn_off"
                    _LOGGER.info("Очиститель %s: %s=%s → %s.%s", dev_id, key, is_on, domain, service)
                    await _call(domain, service, {"entity_id": entity_id})

            else:
                _LOGGER.debug("Очиститель %s: команда '%s' не поддерживается, пропущена", dev_id, key)

    async def _handle_humidifier_command(self, device: dict, states: list) -> None:
        """Обрабатывает команды управления увлажнителем от Сбера.

        Поддерживаемые команды:
          on_off              — включить/выключить (humidifier.turn_on / turn_off)
          hvac_humidity_set   — установить целевую влажность (humidifier.set_humidity)
          hvac_air_flow_power — установить режим/скорость (humidifier.set_mode)
        """
        from .const import SBER_AIR_FLOW_TO_HA_MODE

        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")

        if not entity_id:
            _LOGGER.error("Увлажнитель %s: не задан entity_id", device.get("id"))
            return

        for state in states:
            key     = state.get("key")
            val_obj = state.get("value", {})

            if key == "on_off":
                is_on = _parse_bool(val_obj)
                service = "turn_on" if is_on else "turn_off"
                _LOGGER.info("Humidifier %s: on_off=%s → humidifier.%s", device.get("id"), is_on, service)
                self._track_ha_command(device, states, "humidifier", service, {"entity_id": entity_id})
                await self._async_call(
                    "humidifier", service, {"entity_id": entity_id}, blocking=False
                )

            elif key == "hvac_humidity_set":
                humidity = _parse_integer(val_obj)
                try:
                    h = max(0, min(100, int(float(humidity))))
                    _LOGGER.info("Humidifier %s: set_humidity=%d", device.get("id"), h)
                    self._track_ha_command(device, states, "humidifier", "set_humidity",
                                           {"entity_id": entity_id, "humidity": h})
                    await self._async_call(
                        "humidifier", "set_humidity",
                        {"entity_id": entity_id, "humidity": h},
                        blocking=False,
                    )
                except (ValueError, TypeError):
                    _LOGGER.warning("Humidifier %s: невалидная влажность: %s", device.get("id"), humidity)

            elif key == "hvac_air_flow_power":
                sber_mode = val_obj.get("enum_value", "")
                ha_mode   = SBER_AIR_FLOW_TO_HA_MODE.get(sber_mode)
                if ha_mode:
                    _LOGGER.info("Humidifier %s: set_mode=%s (sber=%s)", device.get("id"), ha_mode, sber_mode)
                    self._track_ha_command(device, states, "humidifier", "set_mode",
                                           {"entity_id": entity_id, "mode": ha_mode})
                    await self._async_call(
                        "humidifier", "set_mode",
                        {"entity_id": entity_id, "mode": ha_mode},
                        blocking=False,
                    )
                else:
                    _LOGGER.warning(
                        "Humidifier %s: неизвестный режим Сбера '%s'", device.get("id"), sber_mode
                    )
    async def _handle_kettle_command(self, device: dict, states: list) -> None:
        """Обрабатывает команды управления чайником от Сбера.

        Источник: сущность домена water_heater (SkyKettle и аналоги).

        Сбер не присылает явных команд вида "выключить"/"вскипятить"/
        "нагреть" — он шлёт только состояния on_off (BOOL) и, опционально,
        kitchen_water_temperature_set (INTEGER). Намерение вычисляется из
        их комбинации (см. логику ниже), и получаются ровно три сценария.

        У каждой модели чайника свой operation_list со своими названиями
        режимов (например off/heat/boil/boil_heat/lamp/light, или
        "off"/Boiling/Warming/Heating/"IQ Boiling"), поэтому при добавлении
        чайника в панели пользователь сопоставляет эти три сценария с
        реальными значениями operation_list устройства — они сохраняются
        в attributes (off_mode / boil_mode / heat_mode) и используются
        здесь вместо захардкоженных строк "off"/"boil"/"heat".

        Логика:
          on_off отсутствует/false            → выключить (set_operation_mode = off_mode)
          on_off = true, temp задана          → set_temperature(temperature=temp, operation_mode)
                                                 (100 или temp не задана → boil_mode, иначе heat_mode)
          on_off = true, temp не задана       → вскипятить (set_operation_mode = boil_mode)

        Для обратной совместимости с устройствами, добавленными до этого
        сопоставления (в attributes нет off_mode/boil_mode/heat_mode),
        используются старые значения "off"/"boil"/"heat".
        """
        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")

        if not entity_id:
            _LOGGER.error("Чайник %s: не задан entity_id", device.get("id"))
            return

        # Режимы устройства, выбранные пользователем при добавлении.
        # Фолбэк на старые захардкоженные значения — для чайников,
        # добавленных до появления этой настройки.
        off_mode  = attrs.get("off_mode")  or "off"
        boil_mode = attrs.get("boil_mode") or "boil"
        # Если отдельного режима нагрева нет — используем режим кипячения.
        heat_mode = attrs.get("heat_mode") or boil_mode

        if not attrs.get("off_mode") or not attrs.get("boil_mode"):
            _LOGGER.warning(
                "Kettle %s: не заданы off_mode/boil_mode в attributes — "
                "используются значения по умолчанию ('off'/'boil'). "
                "Пересохраните устройство в панели, указав реальные "
                "значения operation_list.",
                device.get("id"),
            )

        # Извлекаем on_off и целевую температуру из states
        on_off      = None
        target_temp = None
        for state in states:
            key = state.get("key")
            if key == "on_off":
                on_off = _parse_bool(state.get("value", {}))
            elif key == "kitchen_water_temperature_set":
                target_temp = _parse_integer(state.get("value", {}))

        # ── Выключение ────────────────────────────────────────────────────
        if on_off is False:
            _LOGGER.info(
                "Kettle %s: on_off=False → water_heater.set_operation_mode(%s)",
                device.get("id"), off_mode,
            )
            self._track_ha_command(device, states, "water_heater", "set_operation_mode",
                                   {"entity_id": entity_id, "operation_mode": off_mode})
            await self._async_call(
                "water_heater", "set_operation_mode",
                {"entity_id": entity_id, "operation_mode": off_mode},
                blocking=False,
            )
            return

        # ── Включение / вскипятить / нагрев ─────────────────────────────────
        temp_f = None
        if target_temp is not None:
            try:
                temp_f = float(target_temp)
            except (ValueError, TypeError):
                _LOGGER.warning(
                    "Kettle %s: невалидная температура: %s", device.get("id"), target_temp
                )

        # 100°C → кипячение, ниже → нагрев до температуры, без температуры → кипячение
        is_heat = temp_f is not None and temp_f < 100
        operation_mode = heat_mode if is_heat else boil_mode

        # Сервис water_heater.set_temperature принимает не только
        # temperature, но и operation_mode — можно выставить и температуру,
        # и режим одной командой, без двух последовательных вызовов.
        if temp_f is not None:
            _LOGGER.info(
                "Kettle %s: water_heater.set_temperature(temperature=%.0f, operation_mode=%s)",
                device.get("id"), temp_f, operation_mode,
            )
            self._track_ha_command(device, states, "water_heater", "set_temperature",
                                   {"entity_id": entity_id, "temperature": temp_f,
                                    "operation_mode": operation_mode})
            await self._async_call(
                "water_heater", "set_temperature",
                {"entity_id": entity_id, "temperature": temp_f,
                 "operation_mode": operation_mode},
                blocking=False,
            )
            return

        # Температура не задана (просто on_off=true без temperature) —
        # ставим только режим кипячения.
        _LOGGER.info(
            "Kettle %s: on_off=%s, temp не задана → water_heater.set_operation_mode(%s)",
            device.get("id"), on_off, operation_mode,
        )
        self._track_ha_command(device, states, "water_heater", "set_operation_mode",
                               {"entity_id": entity_id, "operation_mode": operation_mode})
        await self._async_call(
            "water_heater", "set_operation_mode",
            {"entity_id": entity_id, "operation_mode": operation_mode},
            blocking=False,
        )
