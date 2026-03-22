"""Точка входа для API — реэкспортирует все view-классы для __init__.py.

Разбивка по файлам:
  api_common.py    — _get_entry_data, _slugify
  api_devices.py   — CRUD устройств, publish, панель
  api_entities.py  — SberHAEntities*View (списки HA-сущностей для wizard)
  api_devtools.py  — Dev Tools: SSE, просмотр состояний, статус MQTT
"""
from .api_devices import (
    SberDevicesView,
    SberDeviceView,
    SberPublishConfigView,
    SberPublishStatusView,
    SberDeviceTypesView,
    SberPanelView,
)
from .api_entities import (
    SberHAEntitiesRelayView,
    SberHASensorsView,
    SberHAEntitiesClimateView,
    SberHAEntitiesVacuumView,
    SberHAEntitiesValveView,
    SberHAEntitiesLightView,
    SberHAEntitiesCoverView,
    SberHAEntitiesWaterLeakView,
    SberHAEntitiesSmokeView,
    SberHAEntitiesNumberView,
    SberHAEntitiesWaterHeaterView,
    SberHAEntitiesHumidifierView,
    SberHAEntitiesSocketView,
)
from .api_devtools import (
    devtools_on_command,
    SberDevConfigRawView,
    SberDevStateView,
    SberDevStateRawView,
    SberDevCommandsHistoryView,
    SberDevCommandsStreamView,
    SberDevPanelView,
    SberDevToolsExistsView,
    SberConnectionStatusView,
)

__all__ = [
    "SberDevicesView", "SberDeviceView", "SberPublishConfigView",
    "SberPublishStatusView", "SberDeviceTypesView", "SberPanelView",
    "SberHAEntitiesRelayView", "SberHASensorsView",
    "SberHAEntitiesClimateView", "SberHAEntitiesVacuumView",
    "SberHAEntitiesValveView", "SberHAEntitiesLightView",
    "SberHAEntitiesCoverView", "SberHAEntitiesWaterLeakView",
    "SberHAEntitiesSmokeView", "SberHAEntitiesNumberView",
    "SberHAEntitiesWaterHeaterView", "SberHAEntitiesHumidifierView",
    "SberHAEntitiesSocketView",
    "devtools_on_command",
    "SberDevConfigRawView", "SberDevStateView", "SberDevStateRawView",
    "SberDevCommandsHistoryView", "SberDevCommandsStreamView",
    "SberDevPanelView", "SberDevToolsExistsView", "SberConnectionStatusView",
]
