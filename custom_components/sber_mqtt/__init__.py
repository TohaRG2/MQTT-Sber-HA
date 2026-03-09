"""Sber MQTT Bridge — кастомная интеграция Home Assistant.

Связывает устройства HA с экосистемой Сбер Умный дом через MQTT брокер.

Жизненный цикл интеграции:
  1. async_setup_entry()  — загрузка устройств, подключение к MQTT,
                            регистрация панели и HTTP API
  2. async_unload_entry() — отключение от MQTT, очистка ресурсов
  3. async_update_entry() — применение новых учётных данных без перезапуска HA

Все рабочие объекты хранятся в hass.data[DOMAIN][entry.entry_id]:
  mqtt_client     — MQTT клиент (SberMQTTClient)
  device_registry — хранилище устройств (SberDeviceRegistry)
  serializer      — формирует MQTT payload (SberSerializer)
  state_tracker   — отслеживает изменения состояний HA (StateTracker)
  command_handler — выполняет команды от Сбера (HACommandHandler)
  config          — словарь настроек из config entry

Глобальные флаги (_HTTP_VIEWS_REGISTERED, _PANEL_REGISTERED):
  HTTP API и боковая панель регистрируются ОДИН РАЗ за жизнь процесса HA.
  При reload интеграции повторная регистрация не происходит — это сделано
  намеренно, т.к. повторный вызов вызывал бы ошибку «route already exists».

Architecture:
  - Config Flow handles initial MQTT credentials setup
  - SberDeviceRegistry persists user-defined devices across restarts
  - SberMQTTClient maintains connection to Sber broker
  - StateTracker subscribes to HA state changes and pushes to Sber
  - HACommandHandler translates Sber commands into HA service calls
  - REST API views serve the management SPA panel
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, RELAY_BUTTON_DOMAINS, SCENARIO_BUTTON_PUSH_DOMAINS, SCENARIO_BUTTON_STATEFUL_DOMAINS, SCENARIO_BUTTON_CLICK, SCENARIO_BUTTON_DOUBLE_CLICK
from .device_registry import SberDeviceRegistry
from .mqtt_client import SberMQTTClient
from .sber_serializer import SberSerializer
from .state_tracker import StateTracker
from .ha_command_handler import HACommandHandler

_LOGGER = logging.getLogger(__name__)

# Guards: HTTP views and panel must only be registered once per HA process lifetime.
# They survive config entry reloads — re-registering would raise an error.
# Флаги регистрации — HTTP API регистрируется только один раз
# за жизнь процесса HA. При reload интеграции повторная регистрация
# не нужна и вызвала бы ошибку «route already exists».
# Панель перерегистрируется при каждом setup (с актуальным токеном в URL).
_HTTP_VIEWS_REGISTERED = False


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Инициализация интеграции при загрузке HA или после добавления через UI."""
    global _HTTP_VIEWS_REGISTERED

    hass.data.setdefault(DOMAIN, {})

    # Объединяем data и options — options перезаписывают data при обновлении учётных данных
    config: dict[str, Any] = {**entry.data, **entry.options}

    # 1. Persistent device storage
    device_registry = SberDeviceRegistry(hass)
    await device_registry.async_load()

    # 2. Stateless serializer
    serializer = SberSerializer()

    # 3. HA command handler
    command_handler = HACommandHandler(hass)

    # 4. MQTT client — all callbacks are closures over hass/registry/serializer
    #    No circular references, no access to private attributes
    mqtt_client = SberMQTTClient(
        hass=hass,
        config=config,
        on_command=_make_on_command(device_registry, command_handler),
        on_status_request=_make_on_status_request(hass, device_registry, serializer),
        on_config_request=_make_on_config_request(device_registry, serializer),
    )

    connected = await hass.async_add_executor_job(mqtt_client.connect)
    if not connected:
        _LOGGER.error(
            "Could not connect to Sber MQTT broker. "
            "Check credentials via integration options."
        )

    # 5. State tracker
    state_tracker = StateTracker(
        hass=hass,
        serializer=serializer,
        publish_status_fn=mqtt_client.publish_status,
        get_devices_fn=lambda: device_registry.devices,
        update_last_state_fn=device_registry.async_update_last_state,
    )
    state_tracker.start()

    # 6. Store in hass.data
    hass.data[DOMAIN][entry.entry_id] = {
        "device_registry": device_registry,
        "mqtt_client": mqtt_client,
        "serializer": serializer,
        "state_tracker": state_tracker,
        "command_handler": command_handler,
        "config": config,
    }

    # 7. HTTP views — register once per HA process lifetime
    if not _HTTP_VIEWS_REGISTERED:
        _register_http_views(hass)
        _HTTP_VIEWS_REGISTERED = True

    # 8. Sidebar panel — перерегистрируем при каждом setup
    await _async_register_panel(hass)

    # 9. Publish initial config to Sber
    if connected:
        if device_registry.devices:
            payload = serializer.build_config_payload(device_registry.devices)
            _LOGGER.info(
                "Sber MQTT startup: publishing config for %d devices: %s",
                len(device_registry.devices),
                list(device_registry.devices.keys()),
            )
            _LOGGER.info("Sber MQTT config payload: %s", payload)
            mqtt_client.publish_config(payload)
        else:
            _LOGGER.info("Sber MQTT startup: no devices configured yet, skipping config publish")
    else:
        _LOGGER.warning("Sber MQTT startup: not connected, config publish skipped")

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Выгрузка интеграции: остановка отслеживания и отключение от MQTT."""
    data = hass.data[DOMAIN].pop(entry.entry_id, {})
    if tracker := data.get("state_tracker"):
        tracker.stop()
    if client := data.get("mqtt_client"):
        await hass.async_add_executor_job(client.disconnect)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Перезагружает интеграцию после изменения учётных данных в OptionsFlow."""
    _LOGGER.info("Учётные данные Sber MQTT обновлены — перезагружаем интеграцию")
    await hass.config_entries.async_reload(entry.entry_id)


# ── HTTP views (REST API) ─────────────────────────────────────────────────

def _register_http_views(hass: HomeAssistant) -> None:
    """Регистрирует REST API views. Вызывается один раз за жизнь процесса HA."""
    from .api_views import (
        SberDevicesView,
        SberDeviceView,
        SberHAEntitiesRelayView,
        SberHASensorsView,
        SberPublishConfigView,
        SberPublishStatusView,
        SberPanelView,
        SberDeviceTypesView,
        SberConnectionStatusView,
    )
    hass.http.register_view(SberDevicesView(hass))
    hass.http.register_view(SberDeviceView(hass))
    hass.http.register_view(SberHAEntitiesRelayView(hass))
    hass.http.register_view(SberHASensorsView(hass))
    hass.http.register_view(SberPublishConfigView(hass))
    hass.http.register_view(SberPublishStatusView(hass))
    hass.http.register_view(SberPanelView(hass))
    hass.http.register_view(SberDeviceTypesView(hass))
    hass.http.register_view(SberConnectionStatusView(hass))


# ------------------------------------------------------------------ #
# Panel
# ------------------------------------------------------------------ #

async def _async_register_panel(hass: HomeAssistant) -> None:
    """Регистрирует панель в боковом меню HA.

    Панель открывается через динамический эндпоинт /api/sber_mqtt/panel.
    Авторизация API запросов из панели происходит через cookie сессии HA
    (credentials: include) — никакой токен не нужен.
    """
    from homeassistant.components import frontend

    # Удаляем старую панель если уже зарегистрирована
    try:
        frontend.async_remove_panel(hass, "sber_mqtt_panel")
    except Exception:
        pass

    frontend.async_register_built_in_panel(
        hass,
        component_name="iframe",
        sidebar_title="Sber MQTT",
        sidebar_icon="mdi:connection",
        frontend_url_path="sber_mqtt_panel",
        config={"url": "/api/sber_mqtt/panel"},
        require_admin=True,
    )
    _LOGGER.info("Панель Sber MQTT зарегистрирована")


# ── Фабрики колбэков (замыкания) ──────────────────────────────────────────
# Используем замыкания чтобы не передавать hass и другие объекты
# напрямую в MQTT клиент — это предотвращает циклические ссылки.

def _make_on_command(
    device_registry: SberDeviceRegistry,
    command_handler: HACommandHandler,
):
    """Создаёт колбэк для обработки команд от Сбера."""
    async def _on_command(device_id: str, states: list) -> None:
        """Находит устройство по ID и передаёт команду в HACommandHandler."""
        device = device_registry.get_device(device_id)
        if not device:
            _LOGGER.warning("Команда от Сбера для неизвестного устройства: %s", device_id)
            return
        await command_handler.async_handle_command(device, states)
    return _on_command


def _make_on_status_request(
    hass: HomeAssistant,
    device_registry: SberDeviceRegistry,
    serializer: SberSerializer,
):
    async def _on_status_request(device_ids: list) -> None:
        """Отвечает на запрос Сбера о текущих состояниях устройств."""
        entry_data = _get_active_entry_data(hass)
        if not entry_data:
            return
        mqtt_client: SberMQTTClient = entry_data["mqtt_client"]

        # Always respond to root HUB status request
        if not device_ids or "root" in device_ids:
            root_payload = serializer.build_root_state_payload()
            mqtt_client.publish_status(root_payload)
            _LOGGER.info("Sber status: published root HUB state")

        # Respond for registered devices
        devices = device_registry.devices
        targets = (
            {k: v for k, v in devices.items() if k in device_ids}
            if device_ids else devices
        )
        _LOGGER.info("Sber status_request: publishing state for %d devices", len(targets))
        for device_id, device in targets.items():
            payload = _build_current_state_payload(hass, device_id, device, serializer)
            if payload:
                _LOGGER.info("Sber status payload for %s: %s", device_id, payload)
                mqtt_client.publish_status(payload)
            else:
                _LOGGER.warning("Sber status: could not build payload for device %s", device_id)
    return _on_status_request


def _make_on_config_request(
    device_registry: SberDeviceRegistry,
    serializer: SberSerializer,
):
    async def _on_config_request() -> None:
        """Отвечает на запрос Сбера о конфигурации устройств.

        mqtt_client получается в момент вызова (не хранится в замыкании)
        чтобы избежать циклических ссылок при reload интеграции.
        """
        pass
    return _on_config_request


def _get_active_entry_data(hass: HomeAssistant) -> dict | None:
    """Находит данные активной записи интеграции в hass.data."""
    for val in hass.data.get(DOMAIN, {}).values():
        if isinstance(val, dict) and "mqtt_client" in val:
            return val
    return None


def _build_current_state_payload(
    hass: HomeAssistant,
    device_id: str,
    device: dict,
    serializer: SberSerializer,
) -> str | None:
    """Читает текущее состояние из HA и формирует MQTT payload для Сбера."""
    device_type = device.get("device_type")
    attrs = device.get("attributes", {})

    if device_type == "relay":
        entity_id = attrs.get("entity_id", "")
        domain = entity_id.split(".")[0] if entity_id else ""
        if domain in RELAY_BUTTON_DOMAINS:
            is_on = False
        else:
            state = hass.states.get(entity_id)
            if state:
                # media_player: всё кроме "off" считается включённым
                is_on = (state.state != "off") if domain == "media_player" else (state.state == "on")
            else:
                is_on = False
        return serializer.build_relay_state_payload(device_id, is_on)

    if device_type == "sensor_temp":
        def _val(eid: str | None) -> float | None:
            if not eid:
                return None
            s = hass.states.get(eid)
            if not s or s.state in ("unavailable", "unknown", ""):
                return None
            try:
                return float(s.state)
            except (ValueError, TypeError):
                return None
        return serializer.build_sensor_temp_state_payload(
            device_id,
            _val(attrs.get("temperature_entity")),
            _val(attrs.get("humidity_entity")),
            _val(attrs.get("battery_entity")),
            _val(attrs.get("signal_entity")),
        )

    if device_type == "scenario_button":
        entity_id = attrs.get("entity_id", "")
        domain = entity_id.split(".")[0] if entity_id else ""
        if domain in SCENARIO_BUTTON_PUSH_DOMAINS:
            # Кнопки/сценарии не имеют постоянного состояния — отправляем online
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

    return None
