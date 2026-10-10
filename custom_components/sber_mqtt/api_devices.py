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
    DEVICE_TYPE_TV,
    DEVICE_TYPE_AIR_PURIFIER,
    SUPPORTED_DEVICE_TYPES,
)
from .api_common import _get_entry_data, _slugify
from .state_builder import build_current_state_payload
from .ha_helpers import tv_features_from_supported

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
            # Upsert: обновить существующее устройство
            existing = registry.get_device(device_id)
            existing["name"] = name
            if "room" in body:
                existing["room"] = body["room"]
            if attrs:
                existing["attributes"] = {**existing.get("attributes", {}), **attrs}
            await registry.async_save()
            state_tracker.refresh()
            config_payload = serializer.build_config_payload(registry.devices)
            mqtt_client.publish_config(config_payload)
            return web.json_response({"ok": True, "device": existing})

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

            # Сбер не присылает команды с явными именами вроде "boil" или
            # "heat" — он шлёт только два поля состояния: on_off (BOOL) и
            # kitchen_water_temperature_set (INTEGER, опционально).
            # Из их комбинации ha_command_handler вычисляет намерение:
            #   on_off отсутствует/false          → выключить
            #   on_off=true, temp=100 или не задан → вскипятить
            #   on_off=true, temp<100              → нагреть до temp
            # Получаются ровно три сценария, и для каждого нужно знать,
            # какому значению operation_list конкретного чайника он
            # соответствует (у разных моделей разные названия режимов).
            # Поэтому пользователь обязан сопоставить их при добавлении
            # устройства. off_mode и boil_mode обязательны, heat_mode
            # опционален — если у чайника нет отдельного режима нагрева
            # до заданной температуры, используется boil_mode.
            off_mode  = (attrs.get("off_mode")  or "").strip()
            boil_mode = (attrs.get("boil_mode") or "").strip()
            heat_mode = (attrs.get("heat_mode") or "").strip()

            if not off_mode:
                return web.json_response(
                    {"error": "attributes.off_mode is required for kettle "
                              "(выберите команду «Выключить» из operation_list устройства)"},
                    status=400,
                )
            if not boil_mode:
                return web.json_response(
                    {"error": "attributes.boil_mode is required for kettle "
                              "(выберите команду «Вскипятить» из operation_list устройства)"},
                    status=400,
                )

            attrs["off_mode"]  = off_mode
            attrs["boil_mode"] = boil_mode
            if heat_mode:
                attrs["heat_mode"] = heat_mode
            else:
                attrs.pop("heat_mode", None)

            # Подтягиваем min_temp/max_temp/operation_list из water_heater
            ks = hass.states.get(attrs["entity_id"])
            if ks:
                op_list = list(ks.attributes.get("operation_list", []) or [])
                # Если у сущности известен operation_list — проверяем,
                # что выбранные режимы действительно в нём есть.
                if op_list:
                    for field_name, value in (
                        ("off_mode", off_mode),
                        ("boil_mode", boil_mode),
                        ("heat_mode", heat_mode) if heat_mode else (None, None),
                    ):
                        if field_name and value not in op_list:
                            return web.json_response(
                                {"error": f"attributes.{field_name} = '{value}' "
                                          f"не найден в operation_list устройства {attrs['entity_id']}: {op_list}"},
                                status=400,
                            )
                if "min_temp" not in attrs and ks.attributes.get("min_temp") is not None:
                    attrs["min_temp"] = ks.attributes["min_temp"]
                if "max_temp" not in attrs and ks.attributes.get("max_temp") is not None:
                    attrs["max_temp"] = ks.attributes["max_temp"]
        elif device_type == DEVICE_TYPE_TV:
            entity_id = attrs.get("entity_id", "")
            if not entity_id:
                return web.json_response(
                    {"error": "attributes.entity_id is required for tv"}, status=400
                )
            if not entity_id.startswith("media_player."):
                return web.json_response(
                    {"error": "tv requires a media_player entity"}, status=400
                )

            # Набор функций ТВ в Сбере (mute / volume_int / volume) определяется
            # тем, что умеет сущность. Фиксируем флаги при добавлении, чтобы
            # конфиг не менялся от того, включён ли телевизор в данный момент.
            # Если состояния нет (интеграция ТВ ещё не загрузилась) — считаем,
            # что поддерживается всё.
            ts = hass.states.get(entity_id)
            if ts:
                flags = tv_features_from_supported(ts.attributes.get("supported_features"))
            else:
                flags = {
                    "supports_volume_set":  True,
                    "supports_mute":        True,
                    "supports_volume_step": True,
                }
            for flag_name, flag_val in flags.items():
                attrs.setdefault(flag_name, flag_val)
        elif device_type == DEVICE_TYPE_AIR_PURIFIER:
            error = _validate_air_purifier_attrs(attrs)
            if error:
                return web.json_response({"error": error}, status=400)

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

    async def put(self, request: web.Request, device_id: str) -> web.Response:
        """Обновляет устройство: имя, комната, атрибуты."""
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.json_response({"error": "Integration not loaded"}, status=503)

        body = await request.json()
        registry      = data["device_registry"]
        serializer    = data["serializer"]
        mqtt_client   = data["mqtt_client"]
        state_tracker = data["state_tracker"]

        existing = registry.get_device(device_id)
        if not existing:
            return web.json_response({"error": "Device not found"}, status=404)

        # Обновляем поля
        if "name" in body:
            existing["name"] = body["name"]
        if "room" in body:
            existing["room"] = body["room"]
        if "attributes" in body:
            existing["attributes"] = {**existing.get("attributes", {}), **body["attributes"]}

        await registry.async_save()
        state_tracker.refresh()
        config_payload = serializer.build_config_payload(registry.devices)
        mqtt_client.publish_config(config_payload)

        return web.json_response({"ok": True, "device": existing})

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


# ── GET/POST /api/sber_mqtt/settings ────────────────────────────────────

class SberSettingsView(HomeAssistantView):
    """Настройки интеграции: выбор пользователя HA для действий из Сбера."""

    url  = "/api/sber_mqtt/settings"
    name = "api:sber_mqtt:settings"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        user_id = (data or {}).get("config", {}).get("user_id", "")
        users = []
        # Имена из person registry (friendly_name) для лучшего отображения
        person_names: dict[str, str] = {}
        try:
            from homeassistant.helpers import entity_registry as er
            ent_reg = er.async_get(hass)
            for entry in ent_reg.entities.values():
                if entry.domain == "person" and entry.unique_id:
                    person_names[entry.unique_id] = entry.name or entry.original_name or ""
        except Exception:
            pass
        for u in await hass.auth.async_get_users():
            users.append({
                "id": u.id,
                "name": person_names.get(u.id) or u.name or u.id,
                "is_active": u.is_active,
            })
        return web.json_response({"users": users, "user_id": user_id})

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        data = _get_entry_data(hass)
        if not data:
            return web.json_response({"error": "Integration not loaded"}, status=503)
        body = await request.json()
        user_id = body.get("user_id", "")
        data["config"]["user_id"] = user_id
        if handler := data.get("command_handler"):
            handler.set_user_id(user_id)
        return web.json_response({"ok": True, "user_id": user_id})
def _validate_air_purifier_attrs(attrs: dict) -> str | None:
    """Проверяет и нормализует (на месте) настройки очистителя воздуха.

    Возвращает текст ошибки или None. Пустые значения удаляются, чтобы
    незаполненный слот не считался заданным.
    """
    from .const import (
        AIR_PURIFIER_BOOL_FEATURES,
        AIR_PURIFIER_POWER_DOMAINS,
        AIR_PURIFIER_REPLACE_FEATURES,
        AIR_PURIFIER_SELECT_DOMAINS,
        AIR_PURIFIER_SPEED_VALUES,
    )

    def _domain(eid: str) -> str:
        return eid.split(".", 1)[0] if eid else ""

    power = attrs.get("entity_id", "")
    if not power:
        return "attributes.entity_id is required for air_purifier"
    if _domain(power) not in AIR_PURIFIER_POWER_DOMAINS:
        return "air_purifier power entity must be switch, input_boolean or fan"

    # Скорость вентилятора: select + сопоставление значений Сбера опциям select
    if attrs.get("speed_entity"):
        if _domain(attrs["speed_entity"]) not in AIR_PURIFIER_SELECT_DOMAINS:
            return "speed_entity must be select or input_select"
        raw = attrs.get("speed_map")
        raw = raw if isinstance(raw, dict) else {}
        smap = {
            k: str(v) for k, v in raw.items()
            if k in AIR_PURIFIER_SPEED_VALUES and v not in (None, "")
        }
        if not smap:
            return "speed_map must map at least one Sber speed to a select option"
        attrs["speed_map"] = smap
    else:
        attrs.pop("speed_entity", None)
        attrs.pop("speed_map", None)

    # Булевые режимы: switch/input_boolean либо select с опциями «вкл» / «выкл»
    for name in AIR_PURIFIER_BOOL_FEATURES:
        eid = attrs.get(f"{name}_entity")
        if not eid:
            for suffix in ("entity", "on_option", "off_option"):
                attrs.pop(f"{name}_{suffix}", None)
            continue
        if _domain(eid) in AIR_PURIFIER_SELECT_DOMAINS:
            if not attrs.get(f"{name}_on_option") or not attrs.get(f"{name}_off_option"):
                return f"{name}: on_option and off_option are required for select entity"
        else:
            attrs.pop(f"{name}_on_option", None)
            attrs.pop(f"{name}_off_option", None)

    # «Нужно менять»: binary_sensor либо числовой sensor с порогом
    for name in AIR_PURIFIER_REPLACE_FEATURES:
        eid = attrs.get(f"{name}_entity")
        if not eid:
            for suffix in ("entity", "threshold", "cmp"):
                attrs.pop(f"{name}_{suffix}", None)
            continue
        if _domain(eid) == "sensor":
            try:
                attrs[f"{name}_threshold"] = float(attrs.get(f"{name}_threshold"))
            except (ValueError, TypeError):
                return f"{name}: numeric threshold is required for sensor entity"
            attrs[f"{name}_cmp"] = "ge" if attrs.get(f"{name}_cmp") == "ge" else "le"
        else:
            attrs.pop(f"{name}_threshold", None)
            attrs.pop(f"{name}_cmp", None)

    if not attrs.get("online_entity"):
        attrs.pop("online_entity", None)
    return None
