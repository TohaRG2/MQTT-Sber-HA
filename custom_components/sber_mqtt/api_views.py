"""HTTP REST API для панели управления Sber MQTT Bridge.

Все view-классы регистрируются один раз при первом запуске HA
(флаг _HTTP_VIEWS_REGISTERED в __init__.py) и работают на протяжении
всей жизни HA — включая перезагрузки интеграции.

При каждом запросе активная запись интеграции ищется через
_get_entry_data(hass) — это позволяет не хранить ссылки на объекты
между перезагрузками.

Эндпоинты:
  GET  /api/sber_mqtt/devices                    — список устройств
  POST /api/sber_mqtt/devices                    — добавить устройство
  DEL  /api/sber_mqtt/devices/{id}               — удалить устройство
  GET  /api/sber_mqtt/ha_entities/relay          — сущности HA для реле
  GET  /api/sber_mqtt/ha_entities/sensors        — сенсоры HA для датчиков
  POST /api/sber_mqtt/publish_config             — вручную переотправить конфиг
  GET  /api/sber_mqtt/device_types               — типы устройств
  GET  /api/sber_mqtt/status                     — статус MQTT соединения
"""
from __future__ import annotations

import logging
import re
import unicodedata

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    DEVICE_TYPE_RELAY,
    DEVICE_TYPE_SENSOR_TEMP,
    SUPPORTED_DEVICE_TYPES,
)
from .ha_helpers import get_entities_for_relay, get_sensor_entities

_LOGGER = logging.getLogger(__name__)


def _get_entry_data(hass: HomeAssistant) -> dict | None:
    """Находит данные активной записи интеграции в hass.data.

    Возвращает словарь с ключами: mqtt_client, device_registry,
    serializer, state_tracker, config — или None если интеграция не загружена.
    """
    for val in hass.data.get(DOMAIN, {}).values():
        if isinstance(val, dict) and "mqtt_client" in val:
            return val
    return None


def _slugify(text: str) -> str:
    """Преобразует произвольный текст в допустимый ASCII идентификатор.

    Пример: "Свет в гостиной" → "svet_v_gostinoi"
    """
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text or "device"


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


# ── GET /api/sber_mqtt/ha_entities/relay ──────────────────────────────────

class SberHAEntitiesRelayView(HomeAssistantView):
    """Список сущностей HA подходящих для привязки как реле.

    Возвращает switch, input_boolean, script, button, input_button, light.
    """

    url  = "/api/sber_mqtt/ha_entities/relay"
    name = "api:sber_mqtt:ha_entities_relay"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_entities_for_relay(hass)
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/sensors ────────────────────────────────

class SberHASensorsView(HomeAssistantView):
    """Список сенсоров HA отфильтрованных по device_class.

    Параметр: ?classes=temperature,humidity,battery,signal_strength
    """

    url  = "/api/sber_mqtt/ha_entities/sensors"
    name = "api:sber_mqtt:ha_sensors"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        classes_param = request.query.get("classes", "temperature,humidity,battery,signal_strength")
        device_classes = [c.strip() for c in classes_param.split(",") if c.strip()]
        entities = get_sensor_entities(hass, device_classes)
        return web.json_response({"entities": entities})


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

        from .__init__ import _build_current_state_payload

        updated_states = {}  # device_id → last_state для возврата в панель

        for device_id, device in registry.devices.items():
            payload = _build_current_state_payload(hass, device_id, device, serializer)
            if not payload:
                continue
            mqtt_client.publish_status(payload)
            # Сохраняем last_state и собираем для ответа
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
        hass: HomeAssistant = request.app["hass"]

        token = ""
        data = _get_entry_data(hass)
        if data:
            token = data["config"].get("ha_token", "")

        html_path = Path(__file__).parent / "www" / "index.html"
        html = html_path.read_text(encoding="utf-8")

        # Вшиваем токен в страницу — JS читает window.HA_ACCESS_TOKEN при загрузке
        inject = f'<script>\nwindow.HA_ACCESS_TOKEN = {repr(token)};\n</script>\n'
        html = html.replace("</head>", inject + "</head>", 1)

        return web.Response(text=html, content_type="text/html")


# ── GET /api/sber_mqtt/status ─────────────────────────────────────────────

class SberConnectionStatusView(HomeAssistantView):
    """Текущий статус MQTT соединения.

    Используется панелью для отображения индикатора подключения.
    """

    url  = "/api/sber_mqtt/status"
    name = "api:sber_mqtt:status"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.json_response({"connected": False, "devices_count": 0})

        mqtt_client = data["mqtt_client"]
        registry    = data["device_registry"]
        config      = data["config"]

        return web.json_response({
            "connected":     mqtt_client.is_connected,
            "broker":        config.get("mqtt_broker", ""),
            "login":         config.get("mqtt_login", ""),
            "devices_count": len(registry.devices),
        })
