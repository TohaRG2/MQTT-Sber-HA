"""Dev Tools: SSE-стрим команд, просмотр состояний, статус MQTT, отслеживание устройств."""
from __future__ import annotations

import asyncio
import logging
import time as _time
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .api_common import _get_entry_data
from .state_builder import build_current_state_payload

_LOGGER = logging.getLogger(__name__)

# ── GET /api/sber_mqtt/status ─────────────────────────────────────────────

# Глобальный буфер входящих команд от Сбера (до 200 записей, живёт в памяти)
_DEV_COMMANDS_BUFFER: list[dict] = []
_DEV_COMMANDS_MAX    = 200
_DEV_COMMANDS_QUEUES: list[asyncio.Queue] = []  # живые SSE-подписчики

# ── Device tracking ────────────────────────────────────────────────────────
# Буфер для отслеживания конкретного устройства
_DEV_TRACKING_BUFFER: list[dict] = []
_DEV_TRACKING_MAX = 500
_DEV_TRACKING_DEVICE_ID: str | None = None  # Какое устройство отслеживаем
_DEV_TRACKING_ACTIVE = False  # Включено ли отслеживание


def devtools_on_command(topic: str, payload_raw: str) -> None:
    """Вызвать из mqtt_client при получении любого входящего MQTT сообщения (Сбер → HA).

    Добавляет запись в буфер и рассылает подписчикам SSE стрима.
    """
    _devtools_push(topic, payload_raw, direction="in")


def devtools_on_publish(topic: str, payload_raw: str) -> None:
    """Вызвать из mqtt_client при отправке любого исходящего MQTT сообщения (HA → Сбер).

    Добавляет запись в буфер и рассылает подписчикам SSE стрима.
    """
    _devtools_push(topic, payload_raw, direction="out")


def _devtools_push(topic: str, payload_raw: str, direction: str = "in") -> None:
    """Внутренняя функция: добавляет запись в буфер и рассылает по SSE очередям."""
    try:
        import json as _json
        payload_obj = _json.loads(payload_raw)
    except Exception:
        payload_obj = {"raw": payload_raw}

    entry = {
        "ts":        _time.time(),
        "topic":     topic,
        "payload":   payload_obj,
        "direction": direction,   # "in" = Сбер→HA, "out" = HA→Сбер
    }

    _DEV_COMMANDS_BUFFER.append(entry)
    if len(_DEV_COMMANDS_BUFFER) > _DEV_COMMANDS_MAX:
        del _DEV_COMMANDS_BUFFER[:-_DEV_COMMANDS_MAX]

    for q in list(_DEV_COMMANDS_QUEUES):
        try:
            q.put_nowait(entry)
        except asyncio.QueueFull:
            pass

    # Device tracking: если отслеживание активно и устройство совпадает — добавляем в буфер
    _devtools_track_entry(entry)


# ── Device tracking helpers ────────────────────────────────────────────────

def devtools_start_tracking(device_id: str) -> dict:
    """Начать отслеживание конкретного устройства."""
    global _DEV_TRACKING_ACTIVE, _DEV_TRACKING_DEVICE_ID, _DEV_TRACKING_BUFFER
    _DEV_TRACKING_DEVICE_ID = device_id
    _DEV_TRACKING_ACTIVE = True
    _DEV_TRACKING_BUFFER.clear()
    return {"ok": True, "device_id": device_id}


def devtools_stop_tracking() -> dict:
    """Остановить отслеживание устройства."""
    global _DEV_TRACKING_ACTIVE, _DEV_TRACKING_DEVICE_ID
    _DEV_TRACKING_ACTIVE = False
    _DEV_TRACKING_DEVICE_ID = None
    return {"ok": True}


def devtools_get_tracking_info() -> dict:
    """Получить текущий статус отслеживания и буфер."""
    return {
        "active": _DEV_TRACKING_ACTIVE,
        "device_id": _DEV_TRACKING_DEVICE_ID,
        "buffer": list(_DEV_TRACKING_BUFFER),
        "count": len(_DEV_TRACKING_BUFFER),
    }


def _devtools_track_entry(entry: dict) -> None:
    """Добавить запись в буфер отслеживания если устройство совпадает."""
    global _DEV_TRACKING_BUFFER
    if not _DEV_TRACKING_ACTIVE or not _DEV_TRACKING_DEVICE_ID:
        return

    topic = entry.get("topic", "")
    payload = entry.get("payload", {})
    device_id = _DEV_TRACKING_DEVICE_ID

    # Проверяем, относится ли сообщение к отслеживаемому устройству
    matched = False

    # 1. Проверяем topic на наличие device_id
    if device_id in topic:
        matched = True

    # 2. Проверяем payload.devices на наличие device_id
    if not matched and isinstance(payload, dict):
        devices = payload.get("devices", {})
        if isinstance(devices, dict) and device_id in devices:
            matched = True
        elif isinstance(devices, list) and device_id in devices:
            matched = True

    # 3. Проверяем payload.device_id
    if not matched and isinstance(payload, dict):
        if payload.get("device_id") == device_id:
            matched = True

    if matched:
        # Определяем тип события
        event_type = _classify_tracking_event(topic, payload, device_id)
        tracking_entry = {**entry, "event_type": event_type}
        _DEV_TRACKING_BUFFER.append(tracking_entry)
        if len(_DEV_TRACKING_BUFFER) > _DEV_TRACKING_MAX:
            del _DEV_TRACKING_BUFFER[:-_DEV_TRACKING_MAX]


def _classify_tracking_event(topic: str, payload: dict, device_id: str) -> str:
    """Классифицирует тип события для отслеживаемого устройства."""
    # Входящие команды от Сбера
    if "down/commands" in topic:
        return "sber_command"
    if "down/status_request" in topic:
        return "sber_status_request"
    if "down/config_request" in topic:
        return "sber_config_request"
    if "down/errors" in topic:
        return "sber_error"
    if "down/change_group" in topic:
        return "sber_change_group"

    # Исходящие состояния в Сбер
    if "up/status" in topic:
        return "ha_status_update"
    if "up/config" in topic:
        return "ha_config_update"

    # HA state change (отслеживается через state_tracker)
    if topic.startswith("ha_state_change"):
        return "ha_state_change"

    # Команда, отправленная в HA (из ha_command_handler)
    if topic.startswith("ha_command/"):
        return "ha_command"

    return "other"


def devtools_track_ha_command(device_id: str, sber_command: dict, ha_service_call: dict) -> None:
    """Записать в буфер отслеживания команду, отправленную в HA.
    
    Вызывается из HACommandHandler после обработки команды от Сбера.
    
    Args:
        device_id: ID отслеживаемого устройства
        sber_command: Исходная команда от Сбера (states из MQTT)
        ha_service_call: Информация о вызове сервиса HA {domain, service, data}
    """
    global _DEV_TRACKING_BUFFER
    if not _DEV_TRACKING_ACTIVE or not _DEV_TRACKING_DEVICE_ID:
        return
    
    if device_id != _DEV_TRACKING_DEVICE_ID:
        return
    
    entry = {
        "ts": _time.time(),
        "topic": f"ha_command/{device_id}",
        "payload": {
            "device_id": device_id,
            "sber_command": sber_command,
            "ha_service_call": ha_service_call,
        },
        "direction": "out",
        "event_type": "ha_command",
    }
    _DEV_TRACKING_BUFFER.append(entry)
    if len(_DEV_TRACKING_BUFFER) > _DEV_TRACKING_MAX:
        del _DEV_TRACKING_BUFFER[:-_DEV_TRACKING_MAX]
    
    # Push to SSE queues for real-time streaming in DevTools
    for q in list(_DEV_COMMANDS_QUEUES):
        try:
            q.put_nowait(entry)
        except asyncio.QueueFull:
            pass


# ── GET/POST /api/sber_mqtt/dev/config_raw ────────────────────────────────

class SberDevConfigRawView(HomeAssistantView):
    """Сырой JSON конфига как он уйдёт в Сбер (GET), или отправка произвольного (POST)."""

    url  = "/api/sber_mqtt/dev/config_raw"
    name = "api:sber_mqtt:dev:config_raw"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        import json as _json
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.json_response({"error": "Integration not loaded"}, status=503)
        payload_str = data["serializer"].build_config_payload(data["device_registry"].devices)
        return web.json_response({
            "payload":       _json.loads(payload_str),
            "payload_str":   payload_str,
            "devices_count": len(data["device_registry"].devices),
        })

    async def post(self, request: web.Request) -> web.Response:
        import json as _json
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.json_response({"error": "Integration not loaded"}, status=503)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)
        payload_str = _json.dumps(body, ensure_ascii=False)
        try:
            data["mqtt_client"].publish_config(payload_str)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
        _LOGGER.warning("DevTools: ручная отправка сырого конфига (%d bytes)", len(payload_str))
        return web.json_response({"ok": True, "bytes_sent": len(payload_str)})


# ── GET /api/sber_mqtt/dev/state/{device_id} ──────────────────────────────

class SberDevStateView(HomeAssistantView):
    """Текущее состояние одного устройства как оно было бы сформировано для Сбера."""

    url  = "/api/sber_mqtt/dev/state/{device_id}"
    name = "api:sber_mqtt:dev:state"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request, device_id: str) -> web.Response:
        import json as _json
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.json_response({"error": "Integration not loaded"}, status=503)
        device = data["device_registry"].get_device(device_id)
        if not device:
            return web.json_response({"error": "Device not found"}, status=404)
        from .state_builder import build_current_state_payload
        payload_str = build_current_state_payload(hass, device_id, device, data["serializer"])
        if not payload_str:
            return web.json_response({"device_id": device_id, "payload": None, "last_state": device.get("last_state", {})})
        return web.json_response({
            "device_id":   device_id,
            "payload":     _json.loads(payload_str),
            "payload_str": payload_str,
            "last_state":  device.get("last_state", {}),
        })


# ── POST /api/sber_mqtt/dev/state_raw ─────────────────────────────────────

class SberDevStateRawView(HomeAssistantView):
    """Отправить произвольный JSON состояния в Сбер (минуя логику интеграции)."""

    url  = "/api/sber_mqtt/dev/state_raw"
    name = "api:sber_mqtt:dev:state_raw"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def post(self, request: web.Request) -> web.Response:
        import json as _json
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.json_response({"error": "Integration not loaded"}, status=503)
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)
        # _device_id — служебное поле для обновления last_state, убираем из payload
        device_id = body.pop("_device_id", None)
        payload_str = _json.dumps(body, ensure_ascii=False)
        try:
            data["mqtt_client"].publish_status(payload_str)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
        if device_id and data["device_registry"].get_device(device_id):
            device_states = body.get("devices", {}).get(device_id)
            if device_states:
                await data["device_registry"].async_update_last_state(device_id, device_states)
        _LOGGER.warning("DevTools: ручная отправка сырого состояния (%d bytes)", len(payload_str))
        return web.json_response({"ok": True, "bytes_sent": len(payload_str)})


# ── GET/DELETE /api/sber_mqtt/dev/commands/history ────────────────────────

class SberDevCommandsHistoryView(HomeAssistantView):
    """Буфер последних входящих команд от Сбера."""

    url  = "/api/sber_mqtt/dev/commands/history"
    name = "api:sber_mqtt:dev:commands_history"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        limit = max(1, min(int(request.query.get("limit", 100)), _DEV_COMMANDS_MAX))
        since = float(request.query.get("since", 0))
        result = [c for c in _DEV_COMMANDS_BUFFER if c["ts"] > since][-limit:]
        return web.json_response({"commands": result, "total_buffered": len(_DEV_COMMANDS_BUFFER)})

    async def delete(self, request: web.Request) -> web.Response:
        _DEV_COMMANDS_BUFFER.clear()
        return web.json_response({"ok": True})


# ── GET /api/sber_mqtt/dev/commands/stream ────────────────────────────────

class SberDevCommandsStreamView(HomeAssistantView):
    """SSE стрим входящих команд от Сбера в реальном времени.

    Аутентификация через ?token= (Bearer не работает с EventSource в браузере).
    При подключении сразу отдаёт последние N записей из буфера (параметр backlog).
    Keepalive каждые 15 секунд.
    """

    url  = "/api/sber_mqtt/dev/commands/stream"
    name = "api:sber_mqtt:dev:commands_stream"
    requires_auth = False  # auth через ?token=

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.StreamResponse:
        import json as _json
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.Response(text="Integration not loaded", status=503)
        if request.query.get("token", "") != data["config"].get("ha_token", ""):
            return web.Response(text="Unauthorized", status=401)

        response = web.StreamResponse(headers={
            "Content-Type":    "text/event-stream",
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",
        })
        await response.prepare(request)

        backlog = int(request.query.get("backlog", 50))
        for cmd in _DEV_COMMANDS_BUFFER[-backlog:]:
            await response.write(f"data: {_json.dumps(cmd, ensure_ascii=False)}\n\n".encode())

        q: asyncio.Queue = asyncio.Queue(maxsize=50)
        _DEV_COMMANDS_QUEUES.append(q)
        try:
            while True:
                try:
                    cmd = await asyncio.wait_for(q.get(), timeout=15.0)
                    await response.write(f"data: {_json.dumps(cmd, ensure_ascii=False)}\n\n".encode())
                except asyncio.TimeoutError:
                    await response.write(b": ping\n\n")
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            if q in _DEV_COMMANDS_QUEUES:
                _DEV_COMMANDS_QUEUES.remove(q)
        return response


# ── GET /api/sber_mqtt/dev/panel ──────────────────────────────────────────

class SberDevPanelView(HomeAssistantView):
    """Отдаёт devtools.html с вшитым токеном.

    По умолчанию в дистрибутиве лежит заглушка devtools.html.
    Разработчики заменяют её полноценной консолью вручную.
    """

    url  = "/api/sber_mqtt/devtools"
    name = "api:sber_mqtt:devtools"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        import functools
        hass: HomeAssistant = request.app["hass"]

        token = ""
        data = _get_entry_data(hass)
        if data:
            token = data["config"].get("ha_token", "")

        html_path = Path(__file__).parent / "www" / "devtools.html"
        try:
            html = await hass.async_add_executor_job(
                functools.partial(html_path.read_text, encoding="utf-8")
            )
        except FileNotFoundError:
            return web.Response(text="devtools.html not found", status=404)

        inject = f'<script>\nwindow.HA_ACCESS_TOKEN = {repr(token)};\n</script>\n'
        html = html.replace("</head>", inject + "</head>", 1)
        return web.Response(text=html, content_type="text/html")


class SberDevToolsExistsView(HomeAssistantView):
    """Проверяет наличие devtools.html рядом с index.html.

    Используется панелью чтобы показывать кнопку Dev Tools только если
    разработчик положил полноценный devtools.html вместо заглушки.
    Не требует авторизации — вызывается до инициализации токена.
    """

    url  = "/api/sber_mqtt/devtools/exists"
    name = "api:sber_mqtt:devtools_exists"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        html_path = Path(__file__).parent / "www" / "devtools.html"
        exists = html_path.exists()
        # Заглушка не считается — проверяем что файл содержит признак полноценной консоли
        if exists:
            try:
                content = html_path.read_text(encoding="utf-8", errors="ignore")
                # Заглушка содержит этот маркер; полноценный devtools.html его не имеет
                exists = "А вы точно разработчик?" not in content
            except OSError:
                exists = False
        return web.json_response({"exists": exists})


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

        info = mqtt_client.connection_info
        info["devices_count"] = len(registry.devices)
        return web.json_response(info)


class SberDevReconnectView(HomeAssistantView):
    """Принудительное переподключение к MQTT брокеру.

    POST /api/sber_mqtt/dev/reconnect
    Отключается от брокера и подключается заново с теми же учётными данными.
    Возвращает обновлённый connection_info после попытки подключения.
    """

    url  = "/api/sber_mqtt/dev/reconnect"
    name = "api:sber_mqtt:dev:reconnect"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.json_response({"error": "Integration not loaded"}, status=503)

        mqtt_client = data["mqtt_client"]
        _LOGGER.info("DevTools: принудительное переподключение к MQTT")
        ok = await hass.async_add_executor_job(mqtt_client.reconnect)

        info = mqtt_client.connection_info
        info["reconnect_ok"] = ok
        return web.json_response(info)


# ── Device Tracking API ────────────────────────────────────────────────────

class SberDevTrackingStartView(HomeAssistantView):
    """Начать отслеживание конкретного устройства.

    POST /api/sber_mqtt/dev/tracking/start
    Body: {"device_id": "my_device"}
    """

    url = "/api/sber_mqtt/dev/tracking/start"
    name = "api:sber_mqtt:dev:tracking_start"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def post(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON body"}, status=400)
        device_id = body.get("device_id")
        if not device_id:
            return web.json_response({"error": "device_id is required"}, status=400)
        result = devtools_start_tracking(device_id)
        _LOGGER.info("DevTools: отслеживание устройства %s запущено", device_id)
        return web.json_response(result)


class SberDevTrackingStopView(HomeAssistantView):
    """Остановить отслеживание устройства.

    POST /api/sber_mqtt/dev/tracking/stop
    """

    url = "/api/sber_mqtt/dev/tracking/stop"
    name = "api:sber_mqtt:dev:tracking_stop"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def post(self, request: web.Request) -> web.Response:
        result = devtools_stop_tracking()
        _LOGGER.info("DevTools: отслеживание устройства остановлено")
        return web.json_response(result)


class SberDevTrackingInfoView(HomeAssistantView):
    """Получить информацию об отслеживании и буфер событий.

    GET /api/sber_mqtt/dev/tracking/info
    """

    url = "/api/sber_mqtt/dev/tracking/info"
    name = "api:sber_mqtt:dev:tracking_info"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        return web.json_response(devtools_get_tracking_info())


class SberDevTrackingClearView(HomeAssistantView):
    """Очистить буфер отслеживания.

    POST /api/sber_mqtt/dev/tracking/clear
    """

    url = "/api/sber_mqtt/dev/tracking/clear"
    name = "api:sber_mqtt:dev:tracking_clear"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def post(self, request: web.Request) -> web.Response:
        global _DEV_TRACKING_BUFFER
        _DEV_TRACKING_BUFFER.clear()
        return web.json_response({"ok": True})


class SberDevTrackingStreamView(HomeAssistantView):
    """SSE стрим событий отслеживания устройства в реальном времени.

    GET /api/sber_mqtt/dev/tracking/stream?token=...
    """

    url = "/api/sber_mqtt/dev/tracking/stream"
    name = "api:sber_mqtt:dev:tracking_stream"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.StreamResponse:
        import json as _json
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.Response(text="Integration not loaded", status=503)
        if request.query.get("token", "") != data["config"].get("ha_token", ""):
            return web.Response(text="Unauthorized", status=401)

        response = web.StreamResponse(headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        })
        await response.prepare(request)

        # Отдаём текущий буфер
        for entry in _DEV_TRACKING_BUFFER:
            await response.write(f"data: {_json.dumps(entry, ensure_ascii=False)}\n\n".encode())

        # Подписываемся на обновления
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        _DEV_COMMANDS_QUEUES.append(q)
        try:
            while True:
                try:
                    entry = await asyncio.wait_for(q.get(), timeout=15.0)
                    # Фильтруем только для отслеживаемого устройства
                    if _DEV_TRACKING_ACTIVE and _DEV_TRACKING_DEVICE_ID:
                        topic = entry.get("topic", "")
                        payload = entry.get("payload", {})
                        device_id = _DEV_TRACKING_DEVICE_ID
                        matched = False
                        if device_id in topic:
                            matched = True
                        if not matched and isinstance(payload, dict):
                            devices = payload.get("devices", {})
                            if isinstance(devices, dict) and device_id in devices:
                                matched = True
                            elif isinstance(devices, list) and device_id in devices:
                                matched = True
                        if not matched and isinstance(payload, dict):
                            if payload.get("device_id") == device_id:
                                matched = True
                        if matched:
                            event_type = _classify_tracking_event(topic, payload, device_id)
                            tracking_entry = {**entry, "event_type": event_type}
                            await response.write(f"data: {_json.dumps(tracking_entry, ensure_ascii=False)}\n\n".encode())
                    else:
                        await response.write(f"data: {_json.dumps(entry, ensure_ascii=False)}\n\n".encode())
                except asyncio.TimeoutError:
                    await response.write(b": ping\n\n")
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            if q in _DEV_COMMANDS_QUEUES:
                _DEV_COMMANDS_QUEUES.remove(q)
        return response
