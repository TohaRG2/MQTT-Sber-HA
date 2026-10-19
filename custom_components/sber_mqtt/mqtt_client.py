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
import time as _time
from typing import Any, Callable

import paho.mqtt.client as mqtt

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant

from .tls import build_ssl_context
from .const import (
    CERT_FAILURES_BEFORE_FALLBACK,
    CONF_MQTT_LOGIN,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_BROKER,
    CONF_MQTT_PORT,
    CONF_VERIFY_SSL,
    DEFAULT_MQTT_BROKER,
    DEFAULT_MQTT_PORT,
    DEFAULT_VERIFY_SSL,
    TOPIC_UP_CONFIG,
    TOPIC_UP_STATUS,
    TOPIC_DOWN_COMMANDS,
    TOPIC_DOWN_STATUS_REQUEST,
    TOPIC_DOWN_CONFIG_REQUEST,
    TOPIC_DOWN_ERRORS,
)

_LOGGER = logging.getLogger(__name__)

# id постоянного уведомления в HA о подключении без проверки сертификата
_INSECURE_NOTIFICATION_ID = "sber_mqtt_insecure_ssl"


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
        self._verify_ssl = config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL)

        # Автоматический откат на подключение без проверки сертификата
        self._cert_failures: int = 0              # подряд неудачных проверок сертификата
        self._insecure_fallback: bool = False     # сейчас подключены без проверки
        self._last_cert_error: str | None = None  # текст последней ошибки проверки

        # Колбэки бизнес-логики — передаются снаружи, не зависят от клиента
        self._on_command        = on_command
        self._on_status_request = on_status_request
        self._on_config_request = on_config_request

        self._client: mqtt.Client | None = None
        self._connected = False

        # Последняя ошибка подключения — хранится для DevTools
        self._last_error: str | None = None
        self._last_error_time: float | None = None
        self._last_connected_time: float | None = None

        # Автоматическое переподключение
        self._reconnect_task: asyncio.Task | None = None
        self._reconnect_attempt: int = 0
        # Экспоненциальная задержка: 10с, 30с, 1мин, 2мин, 5мин, 10мин, 15мин (макс)
        self._reconnect_delays = [10, 30, 60, 120, 300, 600, 900]
        
        # Колбэк для уведомления о переподключении (для republish config/status)
        self._on_reconnect_callback: Callable | None = None

    # ── Публичный интерфейс ────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """Возвращает True если соединение с брокером установлено."""
        return self._connected

    @property
    def connection_info(self) -> dict:
        """Возвращает расширенную информацию о состоянии соединения для DevTools."""
        import time as _time
        return {
            "connected":           self._connected,
            "broker":              self._broker,
            "port":                self._port,
            "verify_ssl":         self._verify_ssl,
            "insecure_fallback":   self._insecure_fallback,
            "cert_failures":       self._cert_failures,
            "login":               self._login,
            "last_error":          self._last_error,
            "last_error_time":     self._last_error_time,
            "last_connected_time": self._last_connected_time,
            "auto_reconnect_active": self._reconnect_task is not None and not self._reconnect_task.done(),
            "reconnect_attempt":   self._reconnect_attempt,
        }

    def set_on_reconnect_callback(self, callback: Callable | None) -> None:
        """Устанавливает колбэк, вызываемый после успешного переподключения.

        Колбэк вызывается без аргументов в event loop HA.
        Используется для повторной отправки config/status после восстановления связи.
        """
        self._on_reconnect_callback = callback

    def start_auto_reconnect(self) -> None:
        """Запускает фоновую задачу автоматического переподключения.

        Вызывается если первичное подключение не удалось.
        Задача пытается переподключиться с экспоненциальной задержкой.
        """
        if self._reconnect_task is not None and not self._reconnect_task.done():
            _LOGGER.debug("Sber MQTT: автопереподключение уже запущено")
            return

        self._reconnect_attempt = 0
        self._reconnect_task = self._hass.async_create_task(
            self._async_auto_reconnect_loop(),
            name="sber_mqtt_auto_reconnect"
        )
        _LOGGER.info("Sber MQTT: запущено автоматическое переподключение")

    def stop_auto_reconnect(self) -> None:
        """Останавливает фоновую задачу автоматического переподключения."""
        if self._reconnect_task is not None and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            _LOGGER.info("Sber MQTT: автоматическое переподключение остановлено")
        self._reconnect_task = None
        self._reconnect_attempt = 0

    async def _async_auto_reconnect_loop(self) -> None:
        """Фоновая задача: пытается переподключиться с экспоненциальной задержкой.

        Работает пока не будет достигнуто успешное подключение или пока не будет
        остановлена вызовом stop_auto_reconnect().
        """
        try:
            while not self._connected:
                # Рассчитываем задержку
                delay_index = min(self._reconnect_attempt, len(self._reconnect_delays) - 1)
                delay = self._reconnect_delays[delay_index]

                _LOGGER.info(
                    "Sber MQTT: попытка переподключения #%d через %d сек",
                    self._reconnect_attempt + 1, delay
                )

                # Ждём
                await asyncio.sleep(delay)

                # Проверяем, не отменили ли нас
                if self._connected:
                    break

                # Пытаемся подключиться
                self._reconnect_attempt += 1
                connected = await self._hass.async_add_executor_job(self.connect)

                if connected:
                    _LOGGER.info(
                        "Sber MQTT: переподключение успешно с попытки #%d",
                        self._reconnect_attempt
                    )
                    self._reconnect_attempt = 0

                    # Вызываем колбэк для повторной отправки config/status
                    if self._on_reconnect_callback:
                        try:
                            await self._on_reconnect_callback()
                        except Exception as exc:
                            _LOGGER.error("Ошибка в колбэке переподключения: %s", exc)
                    break
                else:
                    _LOGGER.warning(
                        "Sber MQTT: переподключение #%d не удалось, следующая попытка через %d сек",
                        self._reconnect_attempt,
                        self._reconnect_delays[min(self._reconnect_attempt, len(self._reconnect_delays) - 1)]
                    )

        except asyncio.CancelledError:
            _LOGGER.debug("Sber MQTT: задача автопереподключения отменена")
        except Exception as exc:
            _LOGGER.error("Sber MQTT: ошибка в задаче автопереподключения: %s", exc)

    def reconnect(self) -> bool:
        """Переподключается к брокеру. Блокирующий — вызывать через executor."""
        self.disconnect()
        return self.connect()

    def connect(self) -> bool:
        """Подключается к брокеру Сбера. Блокирующий метод — вызывать через executor.

        Если проверка сертификата включена, но подряд CERT_FAILURES_BEFORE_FALLBACK
        попыток не прошли именно из-за сертификата (например, Сбер его перевыпустил),
        подключается без проверки и показывает уведомление в HA. Сетевые ошибки,
        таймауты и отказ по логину/паролю в счётчик не входят. Пока клиент в режиме
        отката, каждое переподключение сначала снова пробует с проверкой — как
        только сертификат снова проходит проверку, режим отката выключается.
        """
        if not self._verify_ssl:
            _LOGGER.warning("Sber MQTT: проверка TLS-сертификата брокера отключена в настройках")
            ok, _ = self._connect_with(verify=False)
            return ok

        ok, cert_error = self._connect_with(verify=True)
        if ok:
            self._cert_failures = 0
            if self._insecure_fallback:
                self._insecure_fallback = False
                _LOGGER.info("Sber MQTT: сертификат брокера снова проходит проверку")
                self._hass.add_job(
                    persistent_notification.async_dismiss,
                    self._hass,
                    _INSECURE_NOTIFICATION_ID,
                )
            return True
        if not cert_error:
            return False

        self._cert_failures += 1
        if self._cert_failures < CERT_FAILURES_BEFORE_FALLBACK:
            _LOGGER.warning(
                "Sber MQTT: проверка сертификата не пройдена (%d из %d) — "
                "после %d неудач подключимся без проверки",
                self._cert_failures, CERT_FAILURES_BEFORE_FALLBACK,
                CERT_FAILURES_BEFORE_FALLBACK,
            )
            return False

        _LOGGER.warning(
            "Sber MQTT: проверка сертификата не прошла %d раз подряд — "
            "подключаемся без проверки сертификата",
            self._cert_failures,
        )
        ok, _ = self._connect_with(verify=False)
        if ok and not self._insecure_fallback:
            self._insecure_fallback = True
            self._hass.add_job(
                persistent_notification.async_create,
                self._hass,
                "Не удалось проверить TLS-сертификат MQTT-брокера Сбера "
                f"({self._last_cert_error}). Возможно, Сбер перевыпустил сертификат.\n\n"
                "Подключение выполнено **без проверки сертификата**: трафик зашифрован, "
                "но защиты от подмены сервера нет. Интеграция будет при каждом "
                "переподключении снова пробовать подключаться с проверкой. "
                "Обновите интеграцию (в ней может быть новый сертификат "
                "`certs/sber_mqtt_broker.pem`) или проверьте, что сертификат "
                "действительно перевыпущен Сбером.",
                "Sber MQTT: подключение без проверки сертификата",
                _INSECURE_NOTIFICATION_ID,
            )
        elif ok:
            _LOGGER.warning("Sber MQTT: подключение без проверки сертификата сохраняется")
        return ok

    def _connect_with(self, verify: bool) -> tuple[bool, bool]:
        """Одна попытка подключения. Блокирующий метод.

        Возвращает (успех, ошибка_проверки_сертификата). Второй флаг True только
        если подключение не удалось именно из-за проверки сертификата — по нему
        connect() решает, считать ли попытку в счётчик отката.
        """
        import threading
        try:
            client = mqtt.Client()
            client.username_pw_set(self._login, self._password)

            # Сертификат брокера Сбера закреплён в certs/ (приватный CA Сбера)
            client.tls_set_context(build_ssl_context(verify))

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
                return True, False
            elif connected and connect_result:
                _LOGGER.error("Sber MQTT: брокер отклонил подключение, rc=%s", connect_result[0])
                return False, False
            else:
                _LOGGER.error("Sber MQTT: таймаут ожидания подключения (10с)")
                self._last_error = "Таймаут ожидания подключения (10 с). Проверьте адрес брокера и порт."
                self._last_error_time = _time.time()
                return False, False

        except (ssl.SSLCertVerificationError, FileNotFoundError) as exc:
            # FileNotFoundError — нет закреплённого PEM (build_ssl_context(True))
            _LOGGER.error("Sber MQTT: сертификат брокера не прошёл проверку: %s", exc)
            self._last_cert_error = str(exc)
            self._last_error = f"Проверка сертификата: {exc}"
            self._last_error_time = _time.time()
            return False, True

        except Exception as exc:
            _LOGGER.error("Sber MQTT: ошибка подключения: %s", exc)
            self._last_error = str(exc)
            self._last_error_time = _time.time()
            return False, False

    def disconnect(self) -> None:
        """Отключается от брокера. Блокирующий метод — вызывать через executor."""
        # Останавливаем автопереподключение при штатном отключении
        self.stop_auto_reconnect()
        
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
            self._devtools_publish_hook(topic, payload)
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
            self._last_error = None
            self._last_connected_time = _time.time()
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
            reason = codes.get(rc, "неизвестная ошибка")
            self._last_error = f"Брокер отклонил подключение: rc={rc} — {reason}"
            self._last_error_time = _time.time()
            _LOGGER.error(
                "Sber MQTT: соединение отклонено rc=%s (%s)",
                rc, reason,
            )

    def _on_disconnect(self, client, userdata, rc) -> None:
        """Вызывается при разрыве соединения.
        
        При неожиданном разрыве (rc != 0) запускает автоматическое переподключение.
        Paho-MQTT имеет встроенный механизм переподключения, но он не работает если
        loop был остановлен или соединение не было установлено изначально.
        """
        self._connected = False
        if rc != 0:
            self._last_error = f"Соединение разорвано неожиданно (rc={rc}). Запущено автопереподключение."
            self._last_error_time = _time.time()
            _LOGGER.warning(
                "Sber MQTT: соединение разорвано rc=%s — запускаем автопереподключение",
                rc,
            )
            # Запускаем автопереподключение из потока paho через schedule
            self._schedule(self._async_start_auto_reconnect_from_disconnect())
        else:
            _LOGGER.info("Sber MQTT: штатное отключение от брокера")
    
    async def _async_start_auto_reconnect_from_disconnect(self) -> None:
        """Запускает автопереподключение после неожиданного разрыва соединения.
        
        Вызывается из _on_disconnect через _schedule (из потока paho в event loop HA).
        """
        # Небольшая задержка чтобы Paho успел завершить внутренние операции
        await asyncio.sleep(2)
        if not self._connected:
            self.start_auto_reconnect()

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

        _LOGGER.info("MQTT ← команды: %s", payload_str)

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

    @staticmethod
    def _devtools_publish_hook(topic: str, payload_str: str) -> None:
        """Отправляет исходящее сообщение в буфер DevTools (без исключений)."""
        try:
            from .api_views import devtools_on_publish
            devtools_on_publish(topic, payload_str)
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
            c.tls_set_context(
                build_ssl_context(config.get(CONF_VERIFY_SSL, DEFAULT_VERIFY_SSL))
            )
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
