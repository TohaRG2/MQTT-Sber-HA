"""Константы интеграции Sber MQTT Bridge."""

# ── Идентификатор интеграции ───────────────────────────────────────────────
# Должен совпадать с именем папки в custom_components
DOMAIN = "sber_mqtt"

# ── Ключи настроек (хранятся в config entry) ──────────────────────────────
CONF_MQTT_LOGIN    = "mqtt_login"     # Логин для подключения к брокеру Сбера
CONF_MQTT_PASSWORD = "mqtt_password"  # Пароль
CONF_HA_TOKEN      = "ha_token"       # Long-Lived Access Token для панели управления
CONF_MQTT_BROKER   = "mqtt_broker"    # Адрес брокера (можно переопределить)
CONF_MQTT_PORT     = "mqtt_port"      # Порт брокера

# ── Параметры MQTT брокера Сбера по умолчанию ─────────────────────────────
DEFAULT_MQTT_BROKER = "mqtt-partners.iot.sberdevices.ru"
DEFAULT_MQTT_PORT   = 8883  # TLS порт

# ── MQTT топики ───────────────────────────────────────────────────────────
# {login} подставляется из настроек интеграции

# Исходящие топики (мы → Сбер)
TOPIC_UP_CONFIG = "sberdevices/v1/{login}/up/config"   # Отправка конфигурации устройств
TOPIC_UP_STATUS = "sberdevices/v1/{login}/up/status"   # Отправка состояний устройств

# Входящие топики (Сбер → мы)
TOPIC_DOWN_COMMANDS       = "sberdevices/v1/{login}/down/commands"             # Команды управления
TOPIC_DOWN_STATUS_REQUEST = "sberdevices/v1/{login}/down/status_request"       # Запрос текущих состояний
TOPIC_DOWN_CONFIG_REQUEST = "sberdevices/v1/{login}/down/config_request"       # Запрос конфигурации
TOPIC_DOWN_ERRORS         = "sberdevices/v1/{login}/down/errors"               # Ошибки от брокера

# ── Типы устройств ────────────────────────────────────────────────────────
# Используются как значение поля device_type при сохранении устройства
DEVICE_TYPE_RELAY           = "relay"            # Реле: выключатели, кнопки, лампы, сценарии
DEVICE_TYPE_SENSOR_TEMP     = "sensor_temp"      # Датчик температуры/влажности
DEVICE_TYPE_SCENARIO_BUTTON = "scenario_button"  # Сценарная кнопка: прокидывает события из HA в Сбер
DEVICE_TYPE_HVAC_AC         = "hvac_ac"          # Кондиционер
DEVICE_TYPE_VACUUM          = "vacuum_cleaner"   # Пылесос
DEVICE_TYPE_VALVE           = "valve"            # Кран / вентиль
DEVICE_TYPE_LIGHT           = "light"            # Лампа / осветительный прибор
DEVICE_TYPE_COVER           = "cover"            # Рулонные шторы / жалюзи
DEVICE_TYPE_WATER_LEAK      = "water_leak"       # Датчик протечки
DEVICE_TYPE_HUMIDIFIER      = "humidifier"       # Увлажнитель воздуха
DEVICE_TYPE_SOCKET          = "socket"           # Розетка с энергомониторингом
DEVICE_TYPE_SMOKE           = "smoke"            # Датчик дыма
DEVICE_TYPE_KETTLE          = "kettle"           # Чайник
DEVICE_TYPE_SENSOR_DOOR     = "sensor_door"      # Датчик открытия двери/окна
DEVICE_TYPE_SENSOR_AIR      = "sensor_air"       # Датчик качества воздуха
DEVICE_TYPE_HVAC_RADIATOR   = "hvac_radiator"    # Термоголовка радиатора
DEVICE_TYPE_HVAC_FAN        = "hvac_fan"         # Вентилятор / бризер
DEVICE_TYPE_TV              = "tv"               # Телевизор
DEVICE_TYPE_INTERCOM         = "intercom"         # Домофон
DEVICE_TYPE_SENSOR_PIR       = "sensor_pir"       # Датчик движения
DEVICE_TYPE_EVENT_BUTTON     = "event_button"     # Кнопка событий HA → Сбер
DEVICE_TYPE_AIR_PURIFIER    = "air_purifier"     # Очиститель воздуха (набор сущностей HA)

# Маппинг скоростей вентилятора Сбер → HA (humidifier mode)
# Сбер: auto | low | medium | high | turbo | quiet
# HA humidifier.set_mode принимает произвольные строки — передаём как есть
SBER_AIR_FLOW_TO_HA_MODE: dict[str, str] = {
    "auto":   "auto",
    "low":    "low",
    "medium": "medium",
    "high":   "high",
    "turbo":  "turbo",
    "quiet":  "quiet",
}
HA_MODE_TO_SBER_AIR_FLOW: dict[str, str] = {v: k for k, v in SBER_AIR_FLOW_TO_HA_MODE.items()}

# Маппинг скоростей Сбер → процент для fan (hvac_fan)
SBER_AIR_FLOW_TO_FAN_PCT: dict[str, int] = {
    "auto":   50,
    "low":    25,
    "medium": 50,
    "high":   75,
    "turbo":  100,
    "quiet":  10,
}

# ── Маппинги вентилятора кондиционера (hvac_ac) ───────────────────────────

# fan_mode кондиционера HA → hvac_air_flow_power Сбера
# Стандартные значения; у конкретного устройства могут быть и другие fan_modes
HA_AC_FAN_MODE_TO_SBER: dict[str, str] = {
    "auto":   "auto",
    "low":    "low",
    "medium": "medium",
    "high":   "high",
}

# preset_mode кондиционера HA → hvac_air_flow_power Сбера
# preset перекрывает fan_mode: boost → turbo, sleep → quiet
HA_AC_PRESET_TO_SBER_AIR_FLOW: dict[str, str] = {
    "boost": "turbo",
    "sleep": "quiet",
}

# hvac_air_flow_power Сбера → (fan_mode, preset_mode) в HA
# turbo/quiet меняют только preset_mode; auto/low/medium/high — только fan_mode
SBER_AIR_FLOW_TO_HA_AC: dict[str, tuple] = {
    "auto":   ("auto",   "none"),
    "low":    ("low",    "none"),
    "medium": ("medium", "none"),
    "high":   ("high",   "none"),
    "turbo":  (None,     "boost"),
    "quiet":  (None,     "sleep"),
}

# ── Маппинги направления потока воздуха кондиционера (hvac_ac) ───────────

# swing_mode кондиционера HA → hvac_air_flow_direction Сбера
HA_AC_SWING_TO_SBER: dict[str, str] = {
    "off":        "no",
    "vertical":   "vertical",
    "horizontal": "horizontal",
    "both":       "rotation",
    "swing":      "swing",      # некоторые устройства используют "swing" вместо "vertical"
    "auto":       "auto",
}

# hvac_air_flow_direction Сбера → swing_mode HA
SBER_AIR_FLOW_DIR_TO_HA: dict[str, str] = {
    "no":         "off",
    "vertical":   "vertical",
    "horizontal": "horizontal",
    "rotation":   "both",
    "swing":      "swing",
    "auto":       "auto",
}

# Словарь типов для UI панели: type_id → отображаемое название
SUPPORTED_DEVICE_TYPES = {
    DEVICE_TYPE_RELAY:           "Реле",
    DEVICE_TYPE_SENSOR_TEMP:     "Датчик температуры/влажности",
    DEVICE_TYPE_SCENARIO_BUTTON: "Сценарная кнопка",
    DEVICE_TYPE_HVAC_AC:         "Кондиционер",
    DEVICE_TYPE_VACUUM:          "Пылесос",
    DEVICE_TYPE_VALVE:           "Кран",
    DEVICE_TYPE_LIGHT:           "Лампа",
    DEVICE_TYPE_COVER:           "Рулонные шторы / жалюзи",
    DEVICE_TYPE_WATER_LEAK:      "Датчик протечки",
    DEVICE_TYPE_HUMIDIFIER:      "Увлажнитель воздуха",
    DEVICE_TYPE_SOCKET:          "Розетка",
    DEVICE_TYPE_SMOKE:           "Датчик дыма",
    DEVICE_TYPE_KETTLE:          "Чайник",
    DEVICE_TYPE_SENSOR_DOOR:     "Датчик открытия",
    DEVICE_TYPE_SENSOR_AIR:      "Датчик качества воздуха",
    DEVICE_TYPE_HVAC_RADIATOR:   "Термоголовка радиатора",
    DEVICE_TYPE_HVAC_FAN:        "Бризер / вентилятор",
    DEVICE_TYPE_TV:              "Телевизор",
    DEVICE_TYPE_INTERCOM:        "Домофон",
    DEVICE_TYPE_SENSOR_PIR:      "Датчик движения",
    DEVICE_TYPE_EVENT_BUTTON:    "Кнопка событий (event → Сбер)",
    DEVICE_TYPE_AIR_PURIFIER:    "Очиститель воздуха",
}

# ── Домены HA для типа "реле" ─────────────────────────────────────────────
# Только сущности из этих доменов можно привязать как реле
RELAY_DOMAINS = {"switch", "input_boolean", "button", "input_button", "light", "media_player"}

# Домены у которых нет состояния on/off (кнопки, сценарии)
# Для них всегда отправляем on_off=false и не отслеживаем изменения состояния
RELAY_BUTTON_DOMAINS = {"script", "button", "input_button", "automation"}

# Домены у которых есть состояние on/off (отслеживаем через state_tracker)
# media_player: состояние "off" → выключен, всё остальное (on/idle/playing/paused) → включён
RELAY_STATEFUL_DOMAINS = {"switch", "input_boolean", "light", "media_player"}

# ── Домены HA для типа "сценарная кнопка" ────────────────────────────────
# Те же домены что и для реле — любая сущность с on/off или кнопка
SCENARIO_BUTTON_DOMAINS = {"switch", "input_boolean", "script", "button", "input_button", "light", "media_player"}

# Домены без состояния (button/script) — всегда шлём click при срабатывании
SCENARIO_BUTTON_PUSH_DOMAINS = {"script", "button", "input_button"}

# Домены со состоянием — включение → click, выключение → double_click
SCENARIO_BUTTON_STATEFUL_DOMAINS = {"switch", "input_boolean", "light", "media_player"}

# Значения событий сценарной кнопки (button_event) для Сбера
SCENARIO_BUTTON_CLICK        = "click"         # Однократное нажатие (включение или кнопка)
SCENARIO_BUTTON_DOUBLE_CLICK = "double_click"  # Двойное нажатие (выключение)

# ── Хранилище ─────────────────────────────────────────────────────────────
STORAGE_KEY     = "sber_mqtt_devices"  # Ключ в .storage/
STORAGE_VERSION = 1                    # Версия схемы хранилища

# ── Устаревшие константы модели (оставлены для совместимости) ─────────────
# В новом формате payload эти значения не используются напрямую —
# структура модели формируется в sber_serializer.py
SBER_MANUFACTURER = "TM Integation"
SBER_HW_VERSION   = "1.1"
SBER_SW_VERSION   = "3.1"
SBER_MODEL_RELAY      = "RELAY_TM_1"
SBER_MODEL_SENSOR_TEMP = "TEMP_HUM_SENSOR_1"

# ── Пороги уровня сигнала ─────────────────────────────────────────────────
# Числовое значение сигнала переводится в enum: low / medium / high
SIGNAL_STRENGTH_LOW_THRESHOLD  = 30   # Ниже 30 → "low"
SIGNAL_STRENGTH_HIGH_THRESHOLD = 70   # Выше 70 → "high", между → "medium"

# ── Маппинг hvac_mode HA → hvac_work_mode Сбера ──────────────────────────
# HA hvac_mode: off, cool, heat, fan_only, dry, auto, heat_cool
# Сбер hvac_work_mode: cooling, heating, ventilation, dehumidification, auto
HA_HVAC_MODE_TO_SBER = {
    "cool":      "cooling",
    "heat":      "heating",
    "fan_only":  "ventilation",
    "dry":       "dehumidification",
    "auto":      "auto",
    "heat_cool": "auto",
}

# Обратный маппинг: Сбер → HA hvac_mode
SBER_HVAC_MODE_TO_HA = {v: k for k, v in HA_HVAC_MODE_TO_SBER.items()}
# Разрешаем несколько значений вручную для конфликтов
SBER_HVAC_MODE_TO_HA["auto"] = "auto"

# ── Маппинг статусов пылесоса HA → Сбер ──────────────────────────────────
# HA vacuum states: cleaning, docked, paused, returning, idle, error
# Сбер vacuum_cleaner_status: cleaning, docked, pause, returning_to_dock
HA_VACUUM_STATUS_TO_SBER = {
    "cleaning":  "cleaning",
    "docked":    "docked",
    "idle":      "pause",
    "paused":    "pause",
    "returning": "returning_to_dock",
    "error":     "pause",
}

# Маппинг команд Сбер → сервис HA
# Сбер: start, pause, return_to_dock, resume
# HA: vacuum.start, vacuum.pause, vacuum.return_to_base
SBER_VACUUM_COMMAND_TO_HA = {
    "start":          ("vacuum", "start"),
    "resume":         ("vacuum", "start"),
    "pause":          ("vacuum", "pause"),
    "return_to_dock": ("vacuum", "return_to_base"),
}

# ── Домены HA для типа "датчик открытия" ──────────────────────────────────
# Датчик открытия двери/окна: binary_sensor с device_class door/window/opening/garage_door
SENSOR_DOOR_DEVICE_CLASSES = {"door", "window", "opening", "garage_door"}

# Маппинг HA состояния → doorcontact_state Сбера
# HA: on → дверь открыта, off → дверь закрыта
HA_DOOR_STATE_TO_SBER = {"on": "open", "off": "close"}

# ── Домены HA для типа "кран" ─────────────────────────────────────────────
VALVE_DOMAINS = {"valve", "switch"}

# Маппинг состояния HA → open_set Сбера
HA_VALVE_STATE_TO_SBER = {
    # valve domain
    "open":    "open",
    "opening": "open",
    "closed":  "close",
    "closing": "close",
    # switch domain
    "on":      "open",
    "off":     "close",
}

# Маппинг команды Сбера → (domain, service) для valve
SBER_VALVE_COMMAND_TO_HA_VALVE = {
    "open":  ("valve", "open_valve"),
    "close": ("valve", "close_valve"),
    "stop":  ("valve", "stop_valve"),
}

# Маппинг команды Сбера → (domain, service) для switch
SBER_VALVE_COMMAND_TO_HA_SWITCH = {
    "open":  ("switch", "turn_on"),
    "close": ("switch", "turn_off"),
    # stop не поддерживается для switch — игнорируем
}

# ── Константы для типа "лампа" ────────────────────────────────────────────

# Диапазоны Сбера
LIGHT_BRIGHTNESS_MIN  = 50
LIGHT_BRIGHTNESS_MAX  = 1000
LIGHT_COLOUR_TEMP_MIN = 0
LIGHT_COLOUR_TEMP_MAX = 1000

# color_mode HA → light_mode Сбера
# Режимы HA: color_temp, hs, rgb, rgbw, rgbww, xy, white, onoff, brightness, unknown
# Всё цветовое → colour, остальное → white
HA_COLOR_MODE_TO_SBER_LIGHT_MODE = {
    "hs":      "colour",
    "rgb":     "colour",
    "rgbw":    "colour",
    "rgbww":   "colour",
    "xy":      "colour",
    "color_temp": "white",
    "white":   "white",
    "brightness": "white",
    "onoff":   "white",
}

# Фичи лампы, которые пользователь может включить при добавлении
LIGHT_OPTIONAL_FEATURES = [
    "light_brightness",
    "light_colour",
    "light_colour_temp",
    "light_mode",
]

# ── Маппинги для типа "шторы/жалюзи" (cover) ─────────────────────────────
# Сбер категория: window_blind
# HA domain: cover

# Состояние HA → open_set Сбера
HA_COVER_STATE_TO_SBER_OPEN_SET = {
    "open":    "open",
    "opening": "open",
    "closed":  "close",
    "closing": "close",
}

# Состояние HA → open_state Сбера
HA_COVER_STATE_TO_SBER_OPEN_STATE = {
    "open":    "open",
    "opening": "opening",
    "closed":  "close",
    "closing": "closing",
}

# Команда Сбера → сервис HA
SBER_COVER_COMMAND_TO_HA = {
    "open":  ("cover", "open_cover"),
    "close": ("cover", "close_cover"),
    "stop":  ("cover", "stop_cover"),
}

# ── Телевизор (tv) ────────────────────────────────────────────────────────
# Сбер категория: tv. HA domain: media_player.
# Поддерживаемые функции Сбера: online, on_off, mute, volume_int, volume.
# Остальные (channel, source, direction, custom_key, number…) пока не реализованы.
TV_DOMAINS = {"media_player"}

# Состояния media_player, которые считаем «выключен» (всё остальное — включён).
# standby — телевизор в режиме ожидания, для пользователя это «выключен».
TV_OFF_STATES = {"off", "standby"}

# Биты MediaPlayerEntityFeature (supported_features)
TV_FEATURE_VOLUME_SET  = 4
TV_FEATURE_VOLUME_MUTE = 8
TV_FEATURE_VOLUME_STEP = 1024

# Шаг громкости (в долях 0..1) для команды volume "+"/"-",
# если сущность не поддерживает volume_up/volume_down, но умеет volume_set
TV_VOLUME_FALLBACK_STEP = 0.05

# Значения команды volume от Сбера → направление
SBER_TV_VOLUME_UP   = {"+", "up", "volume_up", "louder"}
SBER_TV_VOLUME_DOWN = {"-", "down", "volume_down", "quieter"}

# ── Очиститель воздуха (hvac_air_purifier) ────────────────────────────────
# В HA очиститель — это не одна сущность, а набор switch / select / sensor.
# Пользователь сопоставляет их функциям Сбера в мастере добавления.
#
# Обязательные функции Сбера: online, on_off.
# Поддерживаются: hvac_air_flow_power, hvac_night_mode, hvac_ionization,
#   hvac_aromatization, hvac_decontaminate, hvac_replace_filter, hvac_replace_ionizator.
#
# Атрибуты устройства (device["attributes"]):
#   entity_id                    — включение/выключение (switch / input_boolean / fan)
#   speed_entity + speed_map     — скорость вентилятора: select/input_select и
#                                  словарь {значение Сбера: опция select}
#   <name>_entity                — булевые режимы (night_mode, ionization, aromatization,
#   <name>_on_option/_off_option   decontaminate): switch/input_boolean либо select
#                                  (тогда нужны опции «включено» / «выключено»)
#   replace_filter_entity,       — «нужно менять»: binary_sensor либо числовой sensor
#   replace_ionizator_entity       (+ <name>_threshold и <name>_cmp: "le" — меньше или равно,
#   + _threshold, _cmp             "ge" — больше или равно)
#   online_entity                — binary_sensor доступности (опционально)
AIR_PURIFIER_SPEED_VALUES = ["auto", "quiet", "low", "medium", "high", "turbo"]

# имя слота → функция Сбера (управляемые BOOL-режимы)
AIR_PURIFIER_BOOL_FEATURES: dict[str, str] = {
    "night_mode":    "hvac_night_mode",
    "ionization":    "hvac_ionization",
    "aromatization": "hvac_aromatization",
    "decontaminate": "hvac_decontaminate",
}
# имя слота → функция Сбера (только состояние, менять нельзя)
AIR_PURIFIER_REPLACE_FEATURES: dict[str, str] = {
    "replace_filter":    "hvac_replace_filter",
    "replace_ionizator": "hvac_replace_ionizator",
}

AIR_PURIFIER_POWER_DOMAINS  = {"switch", "input_boolean", "fan"}
AIR_PURIFIER_SELECT_DOMAINS = {"select", "input_select"}
AIR_PURIFIER_SWITCH_DOMAINS = {"switch", "input_boolean"}

# Все ключи атрибутов, содержащие entity_id (для подписки на изменения)
AIR_PURIFIER_ENTITY_KEYS = (
    "entity_id", "speed_entity", "online_entity",
    *(f"{n}_entity" for n in AIR_PURIFIER_BOOL_FEATURES),
    *(f"{n}_entity" for n in AIR_PURIFIER_REPLACE_FEATURES),
)
