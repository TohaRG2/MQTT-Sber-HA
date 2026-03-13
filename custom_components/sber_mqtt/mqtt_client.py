"""MQTT клиент для подключения к брокеру Сбера.

Paho-MQTT работает в отдельном потоке. Все входящие сообщения обрабатываются
в этом потоке, но бизнес-логика (команды, обновления состояния) должна
выполняться в event loop Home Assistant.

Для безопасной передачи управления из потока paho в event loop HA
используется asyncio.run_coroutine_threadsafe(coro, hass.loop).
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
from typing import Any, Callable

import paho.mqtt.client as mqtt

from homeassistant.core import HomeAssistant

from .const import (
    CONF_MQTT_LOGIN,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_BROKER,
    CONF_MQTT_PORT,
    DEFAULT_MQTT_BROKER,
    DEFAULT_MQTT_PORT,
    TOPIC_UP_CONFIG,
    TOPIC_UP_STATUS,
    TOPIC_DOWN_COMMANDS,
    TOPIC_DOWN_STATUS_REQUEST,
    TOPIC_DOWN_CONFIG_REQUEST,
    TOPIC_DOWN_ERRORS,
)

_LOGGER = logging.getLogger(__name__)


class SberMQTTClient:
    """Управляет MQTT-подключением к брокеру Сбера.

    Публичный интерфейс:
      connect()         — подключение (блокирующий, вызывать через async_add_executor_job)
      disconnect()      — отключение (блокирующий, вызывать через async_add_executor_job)
      publish_config()  — отправка конфигурации устройств
      publish_status()  — отправка состояния устройств
      is_connected      — текущий статус подключения

    Колбэки (все async, выполняются в event loop HA):
      on_command(device_id, states)  — получена команда управления устройством
      on_status_request(device_ids)  — Сбер запросил текущие состояния
      on_config_request()             — Сбер запросил конфигурацию
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        on_command: Callable,
        on_status_request: Callable,
        on_config_request: Callable,
    ) -> None:
        self._hass = hass

        # Параметры подключения из config entry
        self._login    = config[CONF_MQTT_LOGIN]
        self._password = config[CONF_MQTT_PASSWORD]
        self._broker   = config.get(CONF_MQTT_BROKER, DEFAULT_MQTT_BROKER)
        self._port     = config.get(CONF_MQTT_PORT, DEFAULT_MQTT_PORT)

        # Колбэки бизнес-логики — передаются снаружи, не зависят от клиента
        self._on_command        = on_command
        self._on_status_request = on_status_request
        self._on_config_request = on_config_request

        self._client: mqtt.Client | None = None
        self._connected = False

    # ── Публичный интерфейс ────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """Возвращает True если соединение с брокером установлено."""
        return self._connected

    def connect(self) -> bool:
        """Подключается к брокеру Сбера. Блокирующий метод — вызывать через executor."""
        import threading
        try:
            client = mqtt.Client()
            client.username_pw_set(self._login, self._password)

            # Сбер требует TLS, но использует самоподписанный сертификат —
            # поэтому проверку сертификата отключаем
            client.tls_set(certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE)
            client.tls_insecure_set(True)

            # Системные колбэки paho
            client.on_connect    = self._on_connect
            client.on_disconnect = self._on_disconnect
            client.on_message    = self._on_message_fallback  # для необработанных топиков

            # Назначаем обработчики для каждого входящего топика
            client.message_callback_add(self._fmt(TOPIC_DOWN_COMMANDS),       self._handle_commands)
            client.message_callback_add(self._fmt(TOPIC_DOWN_STATUS_REQUEST), self._handle_status_request)
            client.message_callback_add(self._fmt(TOPIC_DOWN_CONFIG_REQUEST), self._handle_config_request)
            client.message_callback_add(self._fmt(TOPIC_DOWN_ERRORS),         self._handle_errors)
            client.message_callback_add(
                self._fmt("sberdevices/v1/{login}/down/change_group_device_request"),
                self._handle_change_group,
            )

            # Event для ожидания подтверждения подключения от on_connect
            connect_event = threading.Event()
            connect_result: list[int] = []

            original_on_connect = self._on_connect
            def _on_connect_with_event(c, userdata, flags, rc):
                connect_result.append(rc)
                connect_event.set()
                original_on_connect(c, userdata, flags, rc)
            client.on_connect = _on_connect_with_event

            client.connect(self._broker, self._port, keepalive=60)
            client.loop_start()  # запускает фоновый поток обработки MQTT
            self._client = client

            _LOGGER.info(
                "Sber MQTT: подключение к %s:%s как %s",
                self._broker, self._port, self._login,
            )

            # Ждём подтверждения подключения (on_connect) максимум 10 секунд
            connected = connect_event.wait(timeout=10)
            if connected and connect_result and connect_result[0] == 0:
                _LOGGER.info("Sber MQTT: соединение подтверждено брокером")
                return True
            elif connected and connect_result:
                _LOGGER.error("Sber MQTT: брокер отклонил подключение, rc=%s", connect_result[0])
                return False
            else:
                _LOGGER.error("Sber MQTT: таймаут ожидания подключения (10с)")
                return False

        except Exception as exc:
            _LOGGER.error("Sber MQTT: ошибка подключения: %s", exc)
            return False

    def disconnect(self) -> None:
        """Отключается от брокера. Блокирующий метод — вызывать через executor."""
        if self._client:
            self._client.loop_stop()
            try:
                self._client.disconnect()
            except Exception:
                pass
            self._client = None
        self._connected = False

    def publish_config(self, payload: str) -> None:
        """Отправляет конфигурацию устройств в Сбер."""
        self._publish(self._fmt(TOPIC_UP_CONFIG), payload)

    def publish_status(self, payload: str) -> None:
        """Отправляет текущие состояния устройств в Сбер."""
        self._publish(self._fmt(TOPIC_UP_STATUS), payload)

    # ── Внутренние методы ──────────────────────────────────────────────────

    def _fmt(self, template: str) -> str:
        """Подставляет логин в шаблон топика."""
        return template.format(login=self._login)

    def _publish(self, topic: str, payload: str) -> None:
        """Отправляет сообщение в MQTT. Если нет соединения — логирует предупреждение."""
        if self._client and self._connected:
            self._client.publish(topic, payload, qos=0)
            _LOGGER.info("MQTT → %s | payload: %s", topic, payload)
        else:
            _LOGGER.warning(
                "MQTT publish skipped: not connected | topic: %s | connected: %s | client: %s",
                topic, self._connected, self._client is not None,
            )

    def _schedule(self, coro) -> None:
        """Планирует выполнение корутины в event loop HA из потока paho."""
        asyncio.run_coroutine_threadsafe(coro, self._hass.loop)

    # ── Колбэки paho (выполняются в потоке paho, не в event loop HA) ──────

    def _on_connect(self, client, userdata, flags, rc) -> None:
        """Вызывается при установке соединения с брокером."""
        if rc == 0:
            self._connected = True
            sub_topic = f"sberdevices/v1/{self._login}/down/#"
            client.subscribe(sub_topic, qos=0)
            _LOGGER.info(
                "Sber MQTT: подключён к %s:%s | подписан на %s",
                self._broker, self._port, sub_topic,
            )
        else:
            self._connected = False
            codes = {
                1: "неподдерживаемая версия протокола",
                2: "client_id отклонён",
                3: "сервер недоступен",
                4: "неверный логин или пароль",
                5: "не авторизован",
            }
            _LOGGER.error(
                "Sber MQTT: соединение отклонено rc=%s (%s)",
                rc, codes.get(rc, "неизвестная ошибка"),
            )

    def _on_disconnect(self, client, userdata, rc) -> None:
        """Вызывается при разрыве соединения. Paho автоматически переподключается."""
        self._connected = False
        _LOGGER.warning(
            "Sber MQTT: соединение разорвано rc=%s (%s)",
            rc, "штатное отключение" if rc == 0 else "неожиданный разрыв — paho переподключится",
        )

    def _on_message_fallback(self, client, userdata, message) -> None:
        """Обработчик для топиков без явного колбэка (на случай новых топиков от Сбера)."""
        payload_str = message.payload.decode("utf-8", errors="replace")
        _LOGGER.info(
            "MQTT ← необработанный топик: %s | payload: %s",
            message.topic, payload_str[:500],
        )
        self._devtools_hook(message.topic, payload_str)

    def _handle_commands(self, client, userdata, message) -> None:
        """Обрабатывает команды управления устройствами от Сбера.

        Формат: {"devices": {"device_id": {"states": [{"key": "on_off", ...}]}}}
        """
        payload_str = message.payload.decode("utf-8", errors="replace")
        self._devtools_hook(message.topic, payload_str)
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError:
            _LOGGER.error("MQTT ← команды: невалидный JSON: %s", payload_str[:200])
            return

        _LOGGER.info("MQTT ← команды: %s", json.dumps(data, ensure_ascii=False))

        # Передаём каждую команду в обработчик бизнес-логики
        for device_id, device_data in data.get("devices", {}).items():
            states = device_data.get("states", [])
            _LOGGER.info("MQTT ← команда для device_id=%s states=%s", device_id, states)
            self._schedule(self._on_command(device_id, states))

    def _handle_status_request(self, client, userdata, message) -> None:
        """Сбер запрашивает текущие состояния устройств.

        Формат: {"devices": ["device_id1", "device_id2"]}
        Пустой список означает запрос состояний всех устройств.
        """
        payload_str = message.payload.decode("utf-8", errors="replace")
        self._devtools_hook(message.topic, payload_str)
        try:
            data = json.loads(payload_str)
            device_ids = data.get("devices", [])
        except Exception:
            device_ids = []
        _LOGGER.info("MQTT ← запрос состояний для device_ids: %s", device_ids)
        self._schedule(self._on_status_request(device_ids))

    def _handle_config_request(self, client, userdata, message) -> None:
        """Сбер запрашивает полную конфигурацию устройств."""
        payload_str = message.payload.decode("utf-8", errors="replace")
        self._devtools_hook(message.topic, payload_str)
        _LOGGER.info("MQTT ← запрос конфигурации от Сбера")
        self._schedule(self._on_config_request())

    def _handle_change_group(self, client, userdata, message) -> None:
        """Сбер подтверждает что устройство добавлено в комнату/дом.

        Приходит после успешной регистрации устройства через config payload.
        Формат: {"device_id": "...", "home": "Мой дом", "room": "Гостиная"}
        """
        payload_str = message.payload.decode("utf-8", errors="replace")
        self._devtools_hook(message.topic, payload_str)
        try:
            data = json.loads(payload_str)
            _LOGGER.info(
                "Сбер: устройство '%s' добавлено в дом='%s' комната='%s'",
                data.get("device_id"), data.get("home"), data.get("room"),
            )
        except Exception:
            _LOGGER.info("MQTT ← change_group_device_request: %s", payload_str)

    def _handle_errors(self, client, userdata, message) -> None:
        """Ошибки от брокера Сбера (невалидный payload, неизвестные поля и т.д.)."""
        payload_str = message.payload.decode("utf-8", errors="replace")
        self._devtools_hook(message.topic, payload_str)
        _LOGGER.error("MQTT ← ошибка от Сбера: %s", payload_str)

    @staticmethod
    def _devtools_hook(topic: str, payload_str: str) -> None:
        """Отправляет входящее сообщение в буфер DevTools (без исключений)."""
        try:
            from .api_views import devtools_on_command
            devtools_on_command(topic, payload_str)
        except Exception:
            pass


# ── Проверка подключения (используется в Config Flow) ─────────────────────

async def test_mqtt_connection(config: dict[str, Any]) -> bool:
    """Проверяет корректность учётных данных MQTT.

    Пытается подключиться к брокеру и возвращает True если соединение
    принято. Используется при добавлении интеграции через UI.
    """
    import threading as _threading

    def _test() -> bool:
        result = {"ok": False}
        done = _threading.Event()

        def on_connect(c, ud, flags, rc):
            result["ok"] = (rc == 0)
            done.set()
            c.disconnect()

        def on_connect_fail(c, ud):
            done.set()

        try:
            c = mqtt.Client()
            c.username_pw_set(config[CONF_MQTT_LOGIN], config[CONF_MQTT_PASSWORD])
            c.tls_set(certfile=None, keyfile=None, cert_reqs=ssl.CERT_NONE)
            c.tls_insecure_set(True)
            c.on_connect      = on_connect
            c.on_connect_fail = on_connect_fail
            c.connect_async(
                config.get(CONF_MQTT_BROKER, DEFAULT_MQTT_BROKER),
                config.get(CONF_MQTT_PORT, DEFAULT_MQTT_PORT),
                keepalive=10,
            )
            c.loop_start()
            done.wait(timeout=10)  # ждём ответа максимум 10 секунд
            c.loop_stop()
        except Exception as exc:
            _LOGGER.error("MQTT тест подключения: ошибка: %s", exc)
        return result["ok"]

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _test)
