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

from .ha_helpers import _parse_bool

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
        elif device_type == "vacuum_cleaner":
            await self._handle_vacuum_command(device, states)
        elif device_type == "valve":
            await self._handle_valve_command(device, states)
        elif device_type == "cover":
            await self._handle_cover_command(device, states)

        # ── Датчики — команды не принимают ───────────────────────────────
        elif device_type in ("sensor_temp", "water_leak", "smoke"):
            _LOGGER.debug("Команда для датчика %s проигнорирована", device.get("id"))

        # ── Сценарные кнопки — только отправляют события в Сбер ─────────
        elif device_type == "scenario_button":
            _LOGGER.debug("Команда для сценарной кнопки %s проигнорирована", device.get("id"))

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
                on_off_value = _parse_bool(val_obj)
                _LOGGER.info(
                    "Реле %s: on_off=%s (raw bool_value=%r)",
                    device.get("id"), on_off_value, val_obj.get("bool_value"),
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
                    await self._hass.services.async_call(
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
                    await self._hass.services.async_call(
                        "climate", "set_fan_mode",
                        {"entity_id": entity_id, "fan_mode": fan_mode},
                        blocking=False,
                    )
                    # Сбрасываем preset в none чтобы не осталось boost/sleep
                    await self._hass.services.async_call(
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
                    await self._hass.services.async_call(
                        "climate", "set_swing_mode",
                        {"entity_id": entity_id, "swing_mode": ha_swing},
                        blocking=False,
                    )
                else:
                    _LOGGER.warning(
                        "HVAC %s: неизвестный hvac_air_flow_direction '%s'", device.get("id"), sber_dir
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
                    sber_b = int(val.get("integer_value", 500))
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
                try:
                    sber_ct = int(val.get("integer_value", 500))
                    hass_state = self._hass.states.get(entity_id)
                    a = hass_state.attributes if hass_state else {}

                    service_data.pop("hs_color", None)
                    service_data.pop("rgb_color", None)
                    service_data.pop("xy_color", None)

                    min_k = a.get("min_color_temp_kelvin")
                    max_k = a.get("max_color_temp_kelvin")

                    if min_k is not None and max_k is not None:
                        mn_k = float(min_k)  # тёплый
                        mx_k = float(max_k)  # холодный
                        kelvin = round(mn_k + (sber_ct / 1000.0) * (mx_k - mn_k))
                        kelvin = max(int(mn_k), min(int(mx_k), kelvin))
                        _LOGGER.info(
                            "Лампа %s: light.turn_on color_temp_kelvin=%d (sber=%d)",
                            device.get("id"), kelvin, sber_ct,
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
        await self._hass.services.async_call(
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
                    await self._hass.services.async_call(
                        domain, service, {"entity_id": entity_id}, blocking=False
                    )
                else:
                    _LOGGER.warning("Шторы %s: неизвестная команда '%s'", device.get("id"), sber_cmd)

            elif key == "open_percentage":
                try:
                    pct = int(val.get("integer_value", 0))
                    pct = max(0, min(100, pct))
                    _LOGGER.info(
                        "Шторы %s: open_percentage=%s → cover.set_cover_position",
                        device.get("id"), pct,
                    )
                    await self._hass.services.async_call(
                        "cover", "set_cover_position",
                        {"entity_id": entity_id, "position": pct},
                        blocking=False,
                    )
                except (ValueError, TypeError):
                    pass

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
                await self._hass.services.async_call(
                    "humidifier", service, {"entity_id": entity_id}, blocking=False
                )

            elif key == "hvac_humidity_set":
                humidity = val_obj.get("integer_value")
                if humidity is not None:
                    try:
                        h = max(0, min(100, int(float(humidity))))
                        _LOGGER.info("Humidifier %s: set_humidity=%d", device.get("id"), h)
                        await self._hass.services.async_call(
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
                    await self._hass.services.async_call(
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

        Источник: сущность домена water_heater.
        Поддерживаемые команды:
          on_off                        — включить (water_heater.turn_on) /
                                          выключить (water_heater.set_operation_mode, mode=off)
          kitchen_water_temperature_set — установить целевую температуру
                                          (water_heater.set_temperature)
        """
        attrs     = device.get("attributes", {})
        entity_id = attrs.get("entity_id", "")

        if not entity_id:
            _LOGGER.error("Чайник %s: не задан entity_id", device.get("id"))
            return

        for state in states:
            key     = state.get("key")
            val_obj = state.get("value", {})

            if key == "on_off":
                is_on = _parse_bool(val_obj)
                if is_on:
                    _LOGGER.info("Kettle %s: on_off=True → water_heater.turn_on", device.get("id"))
                    await self._hass.services.async_call(
                        "water_heater", "turn_on", {"entity_id": entity_id}, blocking=False
                    )
                else:
                    _LOGGER.info("Kettle %s: on_off=False → water_heater.set_operation_mode(off)", device.get("id"))
                    await self._hass.services.async_call(
                        "water_heater", "set_operation_mode",
                        {"entity_id": entity_id, "operation_mode": "off"},
                        blocking=False,
                    )

            elif key == "kitchen_water_temperature_set":
                temp = val_obj.get("integer_value")
                if temp is not None:
                    try:
                        temp_f = float(temp)
                        _LOGGER.info(
                            "Kettle %s: set_temperature=%.0f → water_heater.set_temperature",
                            device.get("id"), temp_f
                        )
                        await self._hass.services.async_call(
                            "water_heater", "set_temperature",
                            {"entity_id": entity_id, "temperature": temp_f},
                            blocking=False,
                        )
                    except (ValueError, TypeError):
                        _LOGGER.warning(
                            "Kettle %s: невалидная температура: %s", device.get("id"), temp
                        )
