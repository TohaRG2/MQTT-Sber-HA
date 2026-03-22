"""Entity selector views — списки HA-сущностей для wizard добавления устройств."""
from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .ha_helpers import get_entities_for_relay, get_sensor_entities, get_ha_entities

_LOGGER = logging.getLogger(__name__)

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
        classes_param = request.query.get("classes", "temperature,humidity,battery,signal_strength,power,current,voltage")
        device_classes = [c.strip() for c in classes_param.split(",") if c.strip()]
        entities = get_sensor_entities(hass, device_classes)
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/climate ───────────────────────────────

class SberHAEntitiesClimateView(HomeAssistantView):
    """Список climate-сущностей HA для привязки к кондиционеру."""

    url  = "/api/sber_mqtt/ha_entities/climate"
    name = "api:sber_mqtt:ha_entities_climate"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_ha_entities(hass, "climate", extra_fields={
            "fan_modes":    lambda s, e: s.attributes.get("fan_modes",    []) if s else [],
            "preset_modes": lambda s, e: s.attributes.get("preset_modes", []) if s else [],
        })
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/vacuum ─────────────────────────────────

class SberHAEntitiesVacuumView(HomeAssistantView):
    """Список vacuum-сущностей HA для привязки к пылесосу."""

    url  = "/api/sber_mqtt/ha_entities/vacuum"
    name = "api:sber_mqtt:ha_entities_vacuum"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        def _battery(s, e):
            if not s: return None
            bl = s.attributes.get("battery_level")
            if bl is None: return None
            try: return int(float(bl))
            except (ValueError, TypeError): return None
        entities = get_ha_entities(hass, "vacuum", extra_fields={"battery_level": _battery})
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/valve ──────────────────────────────────

class SberHAEntitiesValveView(HomeAssistantView):
    """Список valve и switch сущностей HA для привязки к крану."""

    url  = "/api/sber_mqtt/ha_entities/valve"
    name = "api:sber_mqtt:ha_entities_valve"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_ha_entities(hass, ["valve", "switch"])
        entities.sort(key=lambda x: (x["domain"], x["area"], x["friendly_name"]))
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/light ──────────────────────────────────

class SberHAEntitiesLightView(HomeAssistantView):
    """Список light-сущностей HA для привязки к лампе.

    Возвращает поддерживаемые фичи лампы на основе её атрибутов.
    """

    url  = "/api/sber_mqtt/ha_entities/light"
    name = "api:sber_mqtt:ha_entities_light"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        def _features(s, e):
            if not s: return []
            scm = set(s.attributes.get("supported_color_modes") or [])
            f = []
            if scm - {"onoff"}:                                               f.append("light_brightness")
            if "color_temp" in scm:                                           f.append("light_colour_temp")
            if scm & {"hs", "rgb", "rgbw", "rgbww", "xy"}:                   f.append("light_colour")
            if (scm & {"hs", "rgb", "rgbw", "rgbww", "xy"}) and ("color_temp" in scm or "white" in scm): f.append("light_mode")
            return f
        entities = get_ha_entities(hass, "light", extra_fields={"supported_features": _features})
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/cover ─────────────────────────────────

class SberHAEntitiesCoverView(HomeAssistantView):
    """Список cover-сущностей HA для привязки к шторам/жалюзи."""

    url  = "/api/sber_mqtt/ha_entities/cover"
    name = "api:sber_mqtt:ha_entities_cover"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        def _pos(s, e):
            if not s: return None
            pos = s.attributes.get("current_position")
            if pos is None: return None
            try: return int(float(pos))
            except (ValueError, TypeError): return None
        entities = get_ha_entities(hass, "cover", extra_fields={"current_position": _pos})
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/water_leak ─────────────────────────────

class SberHAEntitiesWaterLeakView(HomeAssistantView):
    """Список binary_sensor с device_class=moisture для датчика протечки."""

    url  = "/api/sber_mqtt/ha_entities/water_leak"
    name = "api:sber_mqtt:ha_entities_water_leak"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_ha_entities(hass, "binary_sensor", device_class="moisture")
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/smoke ──────────────────────────────────

class SberHAEntitiesSmokeView(HomeAssistantView):
    """Список binary_sensor с device_class=smoke для датчика дыма."""

    url  = "/api/sber_mqtt/ha_entities/smoke"
    name = "api:sber_mqtt:ha_entities_smoke"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_ha_entities(hass, "binary_sensor", device_class="smoke")
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/number ─────────────────────────────────

class SberHAEntitiesNumberView(HomeAssistantView):
    """Список number/input_number сущностей — для целевой температуры чайника и т.п."""

    url  = "/api/sber_mqtt/ha_entities/number"
    name = "api:sber_mqtt:ha_entities_number"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_ha_entities(hass, ["number", "input_number"], extra_fields={
            "min":  lambda s, e: s.attributes.get("min")  if s else None,
            "max":  lambda s, e: s.attributes.get("max")  if s else None,
            "step": lambda s, e: s.attributes.get("step") if s else None,
        })
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/water_heater ───────────────────────────

class SberHAEntitiesWaterHeaterView(HomeAssistantView):
    """Список water_heater сущностей HA для чайника."""

    url  = "/api/sber_mqtt/ha_entities/water_heater"
    name = "api:sber_mqtt:ha_entities_water_heater"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_ha_entities(hass, "water_heater")
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/humidifier ─────────────────────────────

class SberHAEntitiesHumidifierView(HomeAssistantView):
    """Список humidifier-сущностей HA для увлажнителя воздуха."""

    url  = "/api/sber_mqtt/ha_entities/humidifier"
    name = "api:sber_mqtt:ha_entities_humidifier"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_ha_entities(hass, "humidifier", extra_fields={
            "available_modes": lambda s, e: (s.attributes.get("available_modes") or []) if s else [],
        })
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/socket ────────────────────────────────────

class SberHAEntitiesSocketView(HomeAssistantView):
    """Список switch/input_boolean-сущностей HA для розетки с энергомониторингом."""

    url  = "/api/sber_mqtt/ha_entities/socket"
    name = "api:sber_mqtt:ha_entities_socket"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_ha_entities(hass, ["switch", "input_boolean"])
        return web.json_response({"entities": entities})
