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

# Словарь типов для UI панели: type_id → отображаемое название
SUPPORTED_DEVICE_TYPES = {
    DEVICE_TYPE_RELAY:           "Реле",
    DEVICE_TYPE_SENSOR_TEMP:     "Датчик температуры/влажности",
    DEVICE_TYPE_SCENARIO_BUTTON: "Сценарная кнопка",
    DEVICE_TYPE_HVAC_AC:         "Кондиционер",
    DEVICE_TYPE_VACUUM:          "Пылесос",
}

# ── Домены HA для типа "реле" ─────────────────────────────────────────────
# Только сущности из этих доменов можно привязать как реле
RELAY_DOMAINS = {"switch", "input_boolean", "script", "button", "input_button", "light", "media_player"}

# Домены у которых нет состояния on/off (кнопки, сценарии)
# Для них всегда отправляем on_off=false и не отслеживаем изменения состояния
RELAY_BUTTON_DOMAINS = {"script", "button", "input_button"}

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
