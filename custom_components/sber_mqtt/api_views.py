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
    SberSettingsView,
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
    SberHAEntitiesDoorView,
    SberHAEntitiesAirView,
    SberHAEntitiesRadiatorView,
    SberHAEntitiesFanView,
    SberHAEntitiesTVView,
    SberHAEntitiesWaterSensorView,
    SberHAEntitiesIntercomView,
    SberHAEntitiesSensorPirView,
    SberHAAutomationTriggersView,
    SberHAEventButtonsView,
    SberHAEntitiesAirPurifierView,
)
from .api_devtools import (
    devtools_on_command,
    devtools_on_publish,
    SberDevConfigRawView,
    SberDevStateView,
    SberDevStateRawView,
    SberDevCommandsHistoryView,
    SberDevCommandsStreamView,
    SberDevPanelView,
    SberDevToolsExistsView,
    SberConnectionStatusView,
    SberDevReconnectView,
)

__all__ = [
    "SberDevicesView", "SberDeviceView", "SberPublishConfigView",
    "SberPublishStatusView", "SberDeviceTypesView", "SberPanelView",
    "SberSettingsView",
    "SberHAEntitiesRelayView", "SberHASensorsView",
    "SberHAEntitiesClimateView", "SberHAEntitiesVacuumView",
    "SberHAEntitiesValveView", "SberHAEntitiesLightView",
    "SberHAEntitiesCoverView", "SberHAEntitiesWaterLeakView",
    "SberHAEntitiesSmokeView", "SberHAEntitiesNumberView",
    "SberHAEntitiesWaterHeaterView", "SberHAEntitiesHumidifierView",
    "SberHAEntitiesSocketView",
    "SberHAEntitiesDoorView",
    "SberHAEntitiesAirView",
    "SberHAEntitiesRadiatorView",
    "SberHAEntitiesFanView",
    "SberHAEntitiesTVView",
    "SberHAEntitiesWaterSensorView",
    "SberHAEntitiesIntercomView",
    "SberHAEntitiesSensorPirView",
    "SberHAAutomationTriggersView",
    "SberHAEventButtonsView",
    "SberHAEntitiesAirPurifierView",
    "devtools_on_command", "devtools_on_publish",
    "SberDevConfigRawView", "SberDevStateView", "SberDevStateRawView",
    "SberDevCommandsHistoryView", "SberDevCommandsStreamView",
    "SberDevPanelView", "SberDevToolsExistsView", "SberConnectionStatusView",
    "SberDevReconnectView",
]
