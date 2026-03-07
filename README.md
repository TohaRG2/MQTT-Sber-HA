# Sber MQTT Bridge — интеграция Home Assistant со Сбером

Кастомная интеграция для Home Assistant, которая пробрасывает ваши устройства из HA в экосистему умного дома Сбера через MQTT.

## Что умеет

- Подключается к MQTT-брокеру Сбера (`mqtt.sberdevices.ru:8883`)
- Пробрасывает выбранные устройства HA в экосистему Сбера (приложение СберДом, голосовой помощник Салют)
- Поддерживает устройства: **Реле** (switch, input_boolean, script, button, input_button, light) и **Датчик температуры/влажности**
- Отслеживает изменения состояний в HA и мгновенно передаёт их в Сбер
- Обрабатывает команды от Сбера (включить/выключить)
- Имеет веб-панель управления прямо в интерфейсе Home Assistant

## Поддерживаемые типы устройств

| Тип | Категория Сбера | HA домены |
|-----|----------------|-----------|
| Реле | `relay` | switch, input_boolean, script, button, input_button, light |
| Датчик температуры/влажности | `sensor_temp` | sensor (temperature, humidity, battery, signal) |

> В будущем планируется поддержка: кнопка, кондиционер, лампочка, кран, пылесос, реле с энергомониторингом.

## Установка

### Способ 1 — HACS (рекомендуется)

1. Откройте HACS → Интеграции → ⋮ → Пользовательские репозитории
2. Добавьте URL: `https://github.com/yourusername/ha-sber-mqtt`
3. Тип: **Integration**
4. Найдите "Sber MQTT Bridge" → Установить
5. Перезапустите Home Assistant

### Способ 2 — Ручная установка

1. Скачайте папку `custom_components/sber_mqtt` из этого репозитория
2. Скопируйте её в `/config/custom_components/sber_mqtt/`
3. Перезапустите Home Assistant

### Установка зависимостей

```bash
pip install paho-mqtt>=1.6.1
```

В Home Assistant OS зависимости устанавливаются автоматически из `manifest.json`.

## Настройка

1. Перейдите в **Настройки → Устройства и службы → Добавить интеграцию**
2. Найдите **"Sber MQTT Bridge"**
3. Введите учётные данные MQTT Сбера:
   - **Логин MQTT** — логин от SberDevices
   - **Пароль MQTT** — пароль от SberDevices
   - **Брокер** — `mqtt.sberdevices.ru` (по умолчанию)
   - **Порт** — `8883` (по умолчанию)
4. После успешного подключения интеграция будет добавлена

## Управление устройствами

После установки в боковом меню HA появится раздел **"Sber MQTT"**.

В панели управления вы можете:
- Просматривать список пробрасываемых устройств с их состояниями
- Добавлять новые устройства через пошаговый мастер
- Удалять устройства
- Сортировать список по любому полю
- Вручную переотправить конфигурацию в Сбер

### Добавление реле

1. Шаг 1: выберите тип **Реле**
2. Шаг 2: выберите сущность из HA (switch, input_boolean, script, button, input_button, light). Доступен поиск по имени, комнате, домену
3. Шаг 3: задайте имя, ID и комнату устройства (заполняются автоматически из HA)

### Добавление датчика температуры/влажности

1. Шаг 1: выберите тип **Датчик температуры/влажности**
2. Шаг 2: выберите сенсоры (можно не заполнять все поля, но хотя бы температура или влажность обязательны):
   - Сенсор температуры
   - Сенсор влажности
   - Сенсор заряда батареи
   - Сенсор силы сигнала
3. Шаг 3: задайте имя, ID и комнату

## HTTP API

Интеграция предоставляет REST API для управления устройствами:

| Метод | URL | Описание |
|-------|-----|----------|
| `GET` | `/api/sber_mqtt/devices` | Список всех устройств |
| `POST` | `/api/sber_mqtt/devices` | Добавить устройство |
| `DELETE` | `/api/sber_mqtt/devices/{id}` | Удалить устройство |
| `GET` | `/api/sber_mqtt/ha_entities/relay` | HA сущности для реле |
| `GET` | `/api/sber_mqtt/ha_entities/sensors` | HA сенсоры |
| `POST` | `/api/sber_mqtt/publish_config` | Переотправить конфиг в Сбер |

Все запросы требуют авторизации HA (cookie или Bearer-токен).

## Структура проекта

```
custom_components/sber_mqtt/
├── __init__.py           # Точка входа, инициализация интеграции
├── manifest.json         # Метаданные интеграции
├── const.py              # Константы
├── config_flow.py        # Config Flow (мастер добавления через UI HA)
├── device_registry.py    # Persistent storage для устройств
├── mqtt_client.py        # MQTT-клиент для брокера Сбера
├── sber_serializer.py    # Формирование MQTT-пакетов для Сбера
├── state_tracker.py      # Отслеживание изменений состояний HA
├── ha_command_handler.py # Выполнение команд от Сбера в HA
├── ha_helpers.py         # Хелперы для работы с реестрами HA
├── api_views.py          # HTTP REST API для панели управления
├── strings.json          # UI строки
├── translations/
│   └── ru.json           # Русский перевод
└── www/
    └── index.html        # SPA панель управления
```

## MQTT-топики

| Топик | Направление | Назначение |
|-------|------------|-----------|
| `sberdevices/v1/{login}/up/config` | → Сбер | Конфигурация устройств |
| `sberdevices/v1/{login}/up/status` | → Сбер | Текущие состояния |
| `sberdevices/v1/{login}/down/commands` | Сбер → | Команды управления |
| `sberdevices/v1/{login}/down/status_request` | Сбер → | Запрос состояний |
| `sberdevices/v1/{login}/down/config_request` | Сбер → | Запрос конфигурации |
| `sberdevices/v1/{login}/down/errors` | Сбер → | Ошибки |

## Формат устройств в Сбере

### Реле
```json
{
  "id": "my_relay_01",
  "manufacturer": "TM Integation",
  "model": "RELAY_TM_1",
  "hw_version": "1.1",
  "sw_version": "3.1",
  "description": "Свет в гостиной",
  "category": "relay",
  "features": ["online", "on_off"]
}
```

### Датчик температуры/влажности
```json
{
  "id": "temp_sensor_01",
  "manufacturer": "TM Integation",
  "model": "TEMP_HUM_SENSOR_1",
  "hw_version": "1.1",
  "sw_version": "3.1",
  "description": "Датчик в спальне",
  "category": "sensor_temp",
  "features": ["online", "temperature", "humidity", "battery_percentage"]
}
```

## Лицензия

MIT
