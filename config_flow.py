"""Config Flow — мастер добавления интеграции через UI Home Assistant.

Открывается через: Настройки → Устройства и сервисы → + Добавить интеграцию → Sber MQTT Bridge

Шаги:
  1. async_step_user — ввод учётных данных MQTT (логин, пароль, брокер, порт)
     Перед сохранением проверяется подключение к брокеру.

Редактирование учётных данных (OptionsFlow):
  Настройки → Устройства и сервисы → Sber MQTT Bridge → Настройки
"""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_MQTT_LOGIN,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_BROKER,
    CONF_MQTT_PORT,
    DEFAULT_MQTT_BROKER,
    DEFAULT_MQTT_PORT,
)
from .mqtt_client import test_mqtt_connection

_LOGGER = logging.getLogger(__name__)

# Схема формы для первоначальной настройки
STEP_USER_SCHEMA = vol.Schema({
    vol.Required(CONF_MQTT_LOGIN):                                   str,  # Логин Сбера
    vol.Required(CONF_MQTT_PASSWORD):                                str,  # Пароль
    vol.Optional(CONF_MQTT_BROKER, default=DEFAULT_MQTT_BROKER):    str,  # Адрес брокера
    vol.Optional(CONF_MQTT_PORT,   default=DEFAULT_MQTT_PORT):      int,  # Порт
})


class SberMQTTConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Мастер первоначальной настройки интеграции."""

    # Версия схемы конфигурации — увеличивается при изменении структуры данных
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Шаг 1: ввод учётных данных MQTT.

        Вызывается когда пользователь нажимает «Добавить интеграцию».
        При повторном вызове (user_input не None) — валидируем и сохраняем.
        """
        # Запрещаем создание более одного экземпляра интеграции
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors: dict[str, str] = {}

        if user_input is not None:
            # Проверяем подключение к брокеру перед сохранением
            ok = await test_mqtt_connection(user_input)
            if ok:
                # Подключение успешно — создаём config entry
                return self.async_create_entry(
                    title=f"Sber MQTT ({user_input[CONF_MQTT_LOGIN]})",
                    data=user_input,
                )
            # Подключение не удалось — показываем ошибку
            errors["base"] = "cannot_connect"

        # Показываем форму (первый раз или после ошибки)
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Возвращает обработчик редактирования настроек (OptionsFlow)."""
        return SberMQTTOptionsFlow(config_entry)


class SberMQTTOptionsFlow(config_entries.OptionsFlow):
    """Форма редактирования учётных данных MQTT.

    Доступна через кнопку «Настройки» на странице интеграции.
    После сохранения интеграция автоматически перезагружается с новыми данными.
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Форма с текущими значениями учётных данных."""
        errors: dict[str, str] = {}

        # Текущие настройки — используются как значения по умолчанию в форме
        current = dict(self.config_entry.data)

        if user_input is not None:
            # Проверяем новые учётные данные
            ok = await test_mqtt_connection(user_input)
            if ok:
                # Сохраняем в options — __init__.py объединит data + options
                return self.async_create_entry(title="", data=user_input)
            errors["base"] = "cannot_connect"

        # Форма с предзаполненными текущими значениями
        schema = vol.Schema({
            vol.Required(CONF_MQTT_LOGIN,   default=current.get(CONF_MQTT_LOGIN, "")):              str,
            vol.Required(CONF_MQTT_PASSWORD, default=current.get(CONF_MQTT_PASSWORD, "")):          str,
            vol.Optional(CONF_MQTT_BROKER,  default=current.get(CONF_MQTT_BROKER, DEFAULT_MQTT_BROKER)): str,
            vol.Optional(CONF_MQTT_PORT,    default=current.get(CONF_MQTT_PORT,   DEFAULT_MQTT_PORT)):   int,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
