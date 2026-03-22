"""CRUD устройств, публикация конфига/статуса, панель управления."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
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
    DEVICE_TYPE_SMOKE,
    DEVICE_TYPE_KETTLE,
    SUPPORTED_DEVICE_TYPES,
)
from .api_common import _get_entry_data, _slugify
from .state_builder import build_current_state_payload

_LOGGER = logging.getLogger(__name__)

# ── GET/POST /api/sber_mqtt/devices ───────────────────────────────────────

class SberDevicesView(HomeAssistantView):
    """Список устройств (GET) и добавление нового устройства (POST)."""

    url  = "/api/sber_mqtt/devices"
    name = "api:sber_mqtt:devices"
    requires_auth = True  # Требует авторизацию через Bearer токен HA

    def __init__(self, hass: HomeAssistant) -> None:
        pass  # hass доступен через request.app["hass"]

    async def get(self, request: web.Request) -> web.Response:
        """Возвращает список всех зарегистрированных устройств."""
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.json_response({"error": "Integration not loaded"}, status=503)
        devices = data["device_registry"].get_all_as_list()
        return web.json_response({"devices": devices})

    async def post(self, request: web.Request) -> web.Response:
        """Добавляет новое устройство.

        Тело запроса (JSON):
        {
          "id":          "relay_kitchen",       # уникальный slug
          "name":        "Свет на кухне",
          "room":        "Кухня",               # опционально
          "device_type": "relay",
          "attributes":  {
            "entity_id": "switch.kitchen_light" # для relay
          }
        }
        После добавления — переотправляет конфиг в Сбер и обновляет подписки.
        """
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.json_response({"error": "Integration not loaded"}, status=503)

        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)

        registry     = data["device_registry"]
        serializer   = data["serializer"]
        mqtt_client  = data["mqtt_client"]
        state_tracker = data["state_tracker"]

        # Валидация общих полей
        device_id:   str  = body.get("id", "").strip()
        name:        str  = body.get("name", "").strip()
        device_type: str  = body.get("device_type", "")
        attrs:       dict = body.get("attributes", {})

        if not device_id:
            return web.json_response({"error": "id is required"}, status=400)
        if not re.match(r"^[a-z0-9_]+$", device_id):
            return web.json_response(
                {"error": "id must contain only lowercase letters, digits and _"}, status=400
            )
        if not name:
            return web.json_response({"error": "name is required"}, status=400)
        if device_type not in SUPPORTED_DEVICE_TYPES:
            return web.json_response(
                {"error": f"Unsupported device_type: {device_type}"}, status=400
            )
        if registry.device_exists(device_id):
            return web.json_response(
                {"error": f"Device ID '{device_id}' already exists"}, status=409
            )

        # Валидация специфичная для типа устройства
        if device_type == DEVICE_TYPE_RELAY:
            if not attrs.get("entity_id"):
                return web.json_response(
                    {"error": "attributes.entity_id is required for relay"}, status=400
                )
        elif device_type == DEVICE_TYPE_SENSOR_TEMP:
            if not attrs.get("temperature_entity") and not attrs.get("humidity_entity"):
                return web.json_response(
                    {"error": "At least one of temperature_entity or humidity_entity must be specified"},
                    status=400,
                )
        elif device_type == DEVICE_TYPE_SCENARIO_BUTTON:
            if not attrs.get("entity_id"):
                return web.json_response(
                    {"error": "attributes.entity_id is required for scenario_button"}, status=400
                )
        elif device_type == DEVICE_TYPE_HVAC_AC:
            if not attrs.get("entity_id"):
                return web.json_response(
                    {"error": "attributes.entity_id is required for hvac_ac"}, status=400
                )
            # Подтягиваем из live-state HA всё что нужно сериализатору для allowed_values
            climate_state = hass.states.get(attrs["entity_id"])
            if climate_state:
                ca = climate_state.attributes
                if "fan_modes" not in attrs:
                    fm = ca.get("fan_modes", [])
                    if fm:
                        attrs["fan_modes"] = fm
                if "preset_modes" not in attrs:
                    pm = ca.get("preset_modes", [])
                    if pm:
                        attrs["preset_modes"] = pm
                if "swing_modes" not in attrs:
                    sm = ca.get("swing_modes", [])
                    if sm:
                        attrs["swing_modes"] = sm
                if "hvac_modes" not in attrs:
                    hm = ca.get("hvac_modes", [])
                    if hm:
                        attrs["hvac_modes"] = hm
                if "min_temp" not in attrs and ca.get("min_temp") is not None:
                    attrs["min_temp"] = ca["min_temp"]
                if "max_temp" not in attrs and ca.get("max_temp") is not None:
                    attrs["max_temp"] = ca["max_temp"]
                if "target_temp_step" not in attrs and ca.get("target_temp_step") is not None:
                    attrs["target_temp_step"] = ca["target_temp_step"]
        elif device_type == DEVICE_TYPE_VACUUM:
            if not attrs.get("entity_id"):
                return web.json_response(
                    {"error": "attributes.entity_id is required for vacuum_cleaner"}, status=400
                )
        elif device_type == DEVICE_TYPE_VALVE:
            if not attrs.get("entity_id"):
                return web.json_response(
                    {"error": "attributes.entity_id is required for valve"}, status=400
                )
        elif device_type == DEVICE_TYPE_LIGHT:
            if not attrs.get("entity_id"):
                return web.json_response(
                    {"error": "attributes.entity_id is required for light"}, status=400
                )
        elif device_type == DEVICE_TYPE_COVER:
            if not attrs.get("entity_id"):
                return web.json_response(
                    {"error": "attributes.entity_id is required for cover"}, status=400
                )
        elif device_type == DEVICE_TYPE_WATER_LEAK:
            if not attrs.get("entity_id"):
                return web.json_response(
                    {"error": "attributes.entity_id is required for water_leak"}, status=400
                )
        elif device_type == DEVICE_TYPE_HUMIDIFIER:
            if not attrs.get("entity_id"):
                return web.json_response(
                    {"error": "attributes.entity_id is required for humidifier"}, status=400
                )
        elif device_type == DEVICE_TYPE_SMOKE:
            if not attrs.get("entity_id"):
                return web.json_response(
                    {"error": "attributes.entity_id is required for smoke"}, status=400
                )
        elif device_type == DEVICE_TYPE_KETTLE:
            if not attrs.get("entity_id"):
                return web.json_response(
                    {"error": "attributes.entity_id is required for kettle"}, status=400
                )
            # Подтягиваем min_temp/max_temp из water_heater для allowed_values
            if "min_temp" not in attrs:
                ks = hass.states.get(attrs["entity_id"])
                if ks:
                    if ks.attributes.get("min_temp") is not None:
                        attrs["min_temp"] = ks.attributes["min_temp"]
                    if ks.attributes.get("max_temp") is not None:
                        attrs["max_temp"] = ks.attributes["max_temp"]

        # Формируем запись устройства
        device_entry = {
            "id":          device_id,
            "name":        name,
            "room":        body.get("room", ""),
            "device_type": device_type,
            "attributes":  attrs,
            "last_state":  {},
        }

        # Сохраняем, обновляем подписки, публикуем конфиг
        await registry.async_add_device(device_entry)
        state_tracker.refresh()

        config_payload = serializer.build_config_payload(registry.devices)
        _LOGGER.info(
            "Устройство добавлено %s (%s) — публикуем конфиг для %d устройств",
            device_id, device_type, len(registry.devices),
        )
        _LOGGER.info("Config payload after add: %s", config_payload)
        mqtt_client.publish_config(config_payload)

        # Публикуем начальное состояние нового устройства и сохраняем в last_state
        from .state_builder import build_current_state_payload
        import json as _json
        status_payload = build_current_state_payload(hass, device_id, device_entry, serializer)
        if status_payload:
            mqtt_client.publish_status(status_payload)
            last = _json.loads(status_payload)["devices"][device_id]
            await registry.async_update_last_state(device_id, last)
            device_entry["last_state"] = last
            _LOGGER.info("Initial status published for %s: %s", device_id, status_payload)

        return web.json_response({"ok": True, "device": device_entry}, status=201)


# ── DELETE /api/sber_mqtt/devices/{device_id} ─────────────────────────────

class SberDeviceView(HomeAssistantView):
    """Удаление одного устройства по ID."""

    url  = "/api/sber_mqtt/devices/{device_id}"
    name = "api:sber_mqtt:device"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def delete(self, request: web.Request, device_id: str) -> web.Response:
        """Удаляет устройство, обновляет подписки и переотправляет конфиг."""
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.json_response({"error": "Integration not loaded"}, status=503)

        registry      = data["device_registry"]
        serializer    = data["serializer"]
        mqtt_client   = data["mqtt_client"]
        state_tracker = data["state_tracker"]

        removed = await registry.async_remove_device(device_id)
        if not removed:
            return web.json_response({"error": "Device not found"}, status=404)

        # Пересобираем подписки и публикуем обновлённый конфиг
        state_tracker.refresh()
        config_payload = serializer.build_config_payload(registry.devices)
        mqtt_client.publish_config(config_payload)

        return web.json_response({"ok": True})

# ── POST /api/sber_mqtt/publish_config ────────────────────────────────────

class SberPublishConfigView(HomeAssistantView):
    """Ручная переотправка полного конфига устройств в Сбер.

    Кнопка «Обновить в Сбере» в панели управления вызывает этот эндпоинт.
    """

    url  = "/api/sber_mqtt/publish_config"
    name = "api:sber_mqtt:publish_config"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.json_response({"error": "Integration not loaded"}, status=503)

        registry    = data["device_registry"]
        serializer  = data["serializer"]
        mqtt_client = data["mqtt_client"]

        payload = serializer.build_config_payload(registry.devices)
        _LOGGER.info(
            "Ручная публикация конфига: %d устройств | payload: %s",
            len(registry.devices), payload,
        )
        mqtt_client.publish_config(payload)
        return web.json_response({"ok": True, "devices_count": len(registry.devices)})



# ── POST /api/sber_mqtt/publish_status ───────────────────────────────────────

class SberPublishStatusView(HomeAssistantView):
    """Ручная отправка текущих состояний всех устройств в Сбер.

    Читает актуальные состояния из HA, отправляет в Сбер и возвращает
    словарь {device_id: last_state} для обновления таблицы в панели.
    """

    url  = "/api/sber_mqtt/publish_status"
    name = "api:sber_mqtt:publish_status"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def post(self, request: web.Request) -> web.Response:
        import json as _json
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.json_response({"error": "Integration not loaded"}, status=503)

        registry    = data["device_registry"]
        serializer  = data["serializer"]
        mqtt_client = data["mqtt_client"]

        from .state_builder import build_current_state_payload

        # Опциональный фильтр по одному устройству: {"device_id": "my_device"}
        try:
            body = await request.json()
            filter_id = body.get("device_id") if isinstance(body, dict) else None
        except Exception:
            filter_id = None

        devices_to_publish = (
            {filter_id: registry.get_device(filter_id)}
            if filter_id and registry.get_device(filter_id)
            else registry.devices
        )

        updated_states = {}  # device_id → last_state для возврата в панель

        for device_id, device in devices_to_publish.items():
            payload = build_current_state_payload(hass, device_id, device, serializer)
            if not payload:
                continue
            mqtt_client.publish_status(payload)
            last = _json.loads(payload)["devices"][device_id]
            await registry.async_update_last_state(device_id, last)
            updated_states[device_id] = last

        _LOGGER.info("Ручная публикация статусов: %d устройств", len(updated_states))
        return web.json_response({"ok": True, "states": updated_states})


# ── GET /api/sber_mqtt/device_types ───────────────────────────────────────

class SberDeviceTypesView(HomeAssistantView):
    """Список поддерживаемых типов устройств (для UI панели)."""

    url  = "/api/sber_mqtt/device_types"
    name = "api:sber_mqtt:device_types"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        types = [{"id": k, "name": v} for k, v in SUPPORTED_DEVICE_TYPES.items()]
        return web.json_response({"device_types": types})


# ── GET /api/sber_mqtt/panel ──────────────────────────────────────────────────

class SberPanelView(HomeAssistantView):
    """Отдаёт index.html с токеном вшитым прямо в HTML.

    requires_auth=False потому что iframe не передаёт cookie сессии.
    Токен из config entry вшивается в страницу как JS переменная —
    панель использует его для Bearer авторизации API запросов.
    """

    url  = "/api/sber_mqtt/panel"
    name = "api:sber_mqtt:panel"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        from pathlib import Path
        import functools
        hass: HomeAssistant = request.app["hass"]

        token = ""
        data = _get_entry_data(hass)
        if data:
            token = data["config"].get("ha_token", "")

        www = Path(__file__).parent / "www"

        def _read_files():
            html = (www / "index.html").read_text(encoding="utf-8")
            css  = (www / "panel.css").read_text(encoding="utf-8")
            js   = (www / "panel.js").read_text(encoding="utf-8")
            return html, css, js

        html, css, js = await hass.async_add_executor_job(_read_files)

        # Заменяем ссылки на внешние файлы инлайн-содержимым
        html = html.replace(
            '<link rel="stylesheet" href="/local/sber_mqtt/panel.css">',
            f'<style>\n{css}\n</style>'
        )
        html = html.replace(
            '<script src="/local/sber_mqtt/panel.js"></script>',
            f'<script>\n{js}\n</script>'
        )

        # Вшиваем токен перед </head>
        inject = f'<script>\nwindow.HA_ACCESS_TOKEN = {repr(token)};\n</script>\n'
        html = html.replace("</head>", inject + "</head>", 1)

        return web.Response(text=html, content_type="text/html")
