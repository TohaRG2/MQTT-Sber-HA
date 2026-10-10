"""Entity selector views — списки HA-сущностей для wizard добавления устройств."""
from __future__ import annotations

import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .ha_helpers import (
    get_entities_for_relay,
    get_sensor_entities,
    get_ha_entities,
    tv_features_from_supported,
)

_LOGGER = logging.getLogger(__name__)


def _safe_pct(s):
    if not s: return None
    pct = s.attributes.get("percentage")
    if pct is not None:
        try: return int(float(pct))
        except (ValueError, TypeError): return None
    return None


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
        classes_param = request.query.get("classes", "temperature,humidity,battery,signal_strength,power,current,voltage,carbon_dioxide,pm25,volatile_organic_compounds")
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
            "hvac_modes":     lambda s, e: s.attributes.get("hvac_modes",     []) if s else [],
            "fan_modes":      lambda s, e: s.attributes.get("fan_modes",      []) if s else [],
            "preset_modes":   lambda s, e: s.attributes.get("preset_modes",   []) if s else [],
            "swing_modes":    lambda s, e: s.attributes.get("swing_modes",    []) if s else [],
            "min_temp":       lambda s, e: s.attributes.get("min_temp")         if s else None,
            "max_temp":       lambda s, e: s.attributes.get("max_temp")         if s else None,
            "target_temp_step": lambda s, e: s.attributes.get("target_temp_step") if s else None,
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
    """Список water_heater сущностей HA для чайника.

    Возвращает также operation_list каждой сущности — у разных чайников
    (SkyKettle, Redmond, Xiaomi и т.д.) набор режимов и их названия
    отличаются (например: off/heat/boil/boil_heat/lamp/light или
    "off"/Boiling/Warming/Heating/"IQ Boiling"). Список нужен панели,
    чтобы пользователь сам сопоставил три команды Сбера
    (вскипятить/нагреть/выключить) с реальными режимами устройства.
    """

    url  = "/api/sber_mqtt/ha_entities/water_heater"
    name = "api:sber_mqtt:ha_entities_water_heater"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]

        def _operation_list(s, e):
            if not s:
                return []
            return list(s.attributes.get("operation_list", []) or [])

        entities = get_ha_entities(
            hass, "water_heater", extra_fields={"operation_list": _operation_list}
        )
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


# ── GET /api/sber_mqtt/ha_entities/sensor_door ────────────────────────────

class SberHAEntitiesDoorView(HomeAssistantView):
    """Список binary_sensor с device_class door/window/opening/garage_door для датчика открытия."""

    url  = "/api/sber_mqtt/ha_entities/sensor_door"
    name = "api:sber_mqtt:ha_entities_sensor_door"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        from .const import SENSOR_DOOR_DEVICE_CLASSES
        hass: HomeAssistant = request.app["hass"]
        entities = get_ha_entities(hass, "binary_sensor", extra_fields={
            "device_class": lambda s, e: s.attributes.get("device_class") if s else None,
        })
        # Фильтруем по device_class
        entities = [e for e in entities if e.get("device_class") in SENSOR_DOOR_DEVICE_CLASSES]
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/sensor_air ─────────────────────────────

class SberHAEntitiesAirView(HomeAssistantView):
    """Список сенсоров HA для датчика качества воздуха.

    Возвращает сенсоры с device_class: temperature, humidity, carbon_dioxide,
    pm25, volatile_organic_compounds, battery, signal_strength.
    """

    url  = "/api/sber_mqtt/ha_entities/sensor_air"
    name = "api:sber_mqtt:ha_entities_sensor_air"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        classes = ["temperature", "humidity", "carbon_dioxide", "pm25",
                    "volatile_organic_compounds", "battery", "signal_strength"]
        entities = get_sensor_entities(hass, classes)
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/hvac_radiator ──────────────────────────

class SberHAEntitiesRadiatorView(HomeAssistantView):
    """Список climate-сущностей HA для термоголовки радиатора."""

    url  = "/api/sber_mqtt/ha_entities/hvac_radiator"
    name = "api:sber_mqtt:ha_entities_hvac_radiator"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_ha_entities(hass, "climate", extra_fields={
            "hvac_modes":          lambda s, e: s.attributes.get("hvac_modes", []) if s else [],
            "min_temp":            lambda s, e: s.attributes.get("min_temp") if s else None,
            "max_temp":            lambda s, e: s.attributes.get("max_temp") if s else None,
            "target_temp_step":    lambda s, e: s.attributes.get("target_temp_step") if s else None,
            "current_temperature": lambda s, e: s.attributes.get("current_temperature") if s else None,
        })
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/hvac_fan ───────────────────────────────

class SberHAEntitiesFanView(HomeAssistantView):
    """Список fan, climate и switch сущностей HA для бризера/вентилятора."""

    url  = "/api/sber_mqtt/ha_entities/hvac_fan"
    name = "api:sber_mqtt:ha_entities_hvac_fan"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        # fan entities
        entities = get_ha_entities(hass, "fan", extra_fields={
            "percentage": lambda s, e: _safe_pct(s),
            "preset_modes": lambda s, e: s.attributes.get("preset_modes", []) if s else [],
        })
        # climate entities (бризеры часто climate)
        climate_entities = get_ha_entities(hass, "climate", extra_fields={
            "percentage": lambda s, e: _safe_pct(s),
            "preset_modes": lambda s, e: s.attributes.get("preset_modes", []) if s else [],
        })
        entities.extend(climate_entities)
        # switch fallback
        switch_entities = get_ha_entities(hass, ["switch", "input_boolean"])
        entities.extend(switch_entities)
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/tv ────────────────────────────────────────

class SberHAEntitiesTVView(HomeAssistantView):
    """Список media_player-сущностей HA для привязки к телевизору.

    Для каждой сущности возвращает флаги поддерживаемых функций
    (громкость, mute, шаг громкости) — по ним панель показывает, что
    будет доступно в Салюте.
    """

    url  = "/api/sber_mqtt/ha_entities/tv"
    name = "api:sber_mqtt:ha_entities_tv"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]

        def _flags(s, e):
            if not s:
                return {}
            return tv_features_from_supported(s.attributes.get("supported_features"))

        entities = get_ha_entities(hass, "media_player", extra_fields={"tv_features": _flags})
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/air_purifier ─────────────────────────────

class SberHAEntitiesAirPurifierView(HomeAssistantView):
    """Кандидаты для привязки к очистителю воздуха.

    Очиститель в HA — набор сущностей, поэтому возвращаем три списка:
      power    — switch / input_boolean / fan   (включение и выключение)
      controls — switch / input_boolean / select / input_select
                 (скорость и режимы; у select есть список options)
      sensors  — sensor / binary_sensor
                 (замена фильтра / ионизатора, доступность; с unit и device_class)
    У каждой сущности есть device_id — по нему мастер подбирает остальные
    сущности того же физического устройства.
    """

    url  = "/api/sber_mqtt/ha_entities/air_purifier"
    name = "api:sber_mqtt:ha_entities_air_purifier"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]

        def _options(s, e):
            if not s:
                return []
            opts = s.attributes.get("options")
            return list(opts) if isinstance(opts, (list, tuple)) else []

        def _unit(s, e):
            return (s.attributes.get("unit_of_measurement") or "") if s else ""

        def _state(s, e):
            return s.state if s else ""

        def _dc(s, e):
            return (
                e.original_device_class
                or e.device_class
                or (s.attributes.get("device_class", "") if s else "")
                or ""
            )

        return web.json_response({
            "power": get_ha_entities(hass, ["switch", "input_boolean", "fan"]),
            "controls": get_ha_entities(
                hass, ["switch", "input_boolean", "select", "input_select"],
                extra_fields={"options": _options},
            ),
            "sensors": get_ha_entities(
                hass, ["sensor", "binary_sensor"],
                extra_fields={"unit": _unit, "dc": _dc, "state": _state},
            ),
        })
# ── GET /api/sber_mqtt/ha_entities/intercom ───────────────────────────

class SberHAEntitiesIntercomView(HomeAssistantView):
    """Список сущностей для домофона: switch, button, lock, input_boolean."""

    url  = "/api/sber_mqtt/ha_entities/intercom"
    name = "api:sber_mqtt:ha_entities_intercom"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_ha_entities(hass, ["switch", "button", "input_button", "lock", "input_boolean", "script"])
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/sensor_pir ─────────────────────────

class SberHAEntitiesSensorPirView(HomeAssistantView):
    """Список binary_sensor с device_class motion/occupancy для датчика движения."""

    url  = "/api/sber_mqtt/ha_entities/sensor_pir"
    name = "api:sber_mqtt:ha_entities_sensor_pir"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_ha_entities(hass, "binary_sensor")
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/water_sensors ──────────────────────────

class SberHAEntitiesWaterSensorView(HomeAssistantView):
    """Все сенсоры без фильтра — для выбора уровня воды в чайнике."""

    url  = "/api/sber_mqtt/ha_entities/water_sensors"
    name = "api:sber_mqtt:ha_entities_water_sensors"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_sensor_entities(hass, [])
        return web.json_response({"entities": entities})


# ── GET /api/sber_mqtt/ha_entities/automation_triggers ─────────────────

class SberHAAutomationTriggersView(HomeAssistantView):
    """Список trigger_id автоматизации."""

    url  = "/api/sber_mqtt/ha_entities/automation_triggers"
    name = "api:sber_mqtt:ha_automation_triggers"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entity_id = request.query.get("entity_id", "")
        ids = []
        raw = []
        if entity_id:
            state = hass.states.get(entity_id)
            if state:
                # Отдаём automation id для запроса конфига через REST API
                auto_id = state.attributes.get("id", "")
                return web.json_response({"trigger_ids": [], "automation_id": auto_id})


# ── GET /api/sber_mqtt/ha_entities/event_buttons ───────────────────────

class SberHAEventButtonsView(HomeAssistantView):
    """Список sensor и binary_sensor для кнопок событий."""

    url  = "/api/sber_mqtt/ha_entities/event_buttons"
    name = "api:sber_mqtt:ha_event_buttons"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        pass

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app["hass"]
        entities = get_ha_entities(hass, ["sensor", "binary_sensor", "event"])
        return web.json_response({"entities": entities})
