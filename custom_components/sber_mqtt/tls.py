"""SSL-контекст для подключения к MQTT-брокеру Сбера.

Брокер mqtt-partners.iot.sberdevices.ru использует сертификат, выпущенный
приватным CA Сбера (CN=iot.sberdevices.ru). Этот CA нигде не опубликован и
брокер отдаёт только листовой сертификат, без цепочки, поэтому проверить его
через системное хранилище или корни Минцифры нельзя (раньше проверка
отключалась полностью).

Вместо этого сертификат брокера закреплён (pinning): файл
certs/sber_mqtt_broker.pem добавляется в доверенные как есть, а при
проверке разрешена «частичная цепочка» — листовой сертификат принимается
как якорь доверия. Имя хоста тоже проверяется (в SAN: *.iot.sberdevices.ru).

Когда Сбер перевыпустит сертификат (текущий действует до 2028-09-06),
подключение перестанет проходить проверку — тогда нужно заменить/дополнить
PEM-файл. В файле может быть несколько сертификатов подряд.
"""
from __future__ import annotations

import logging
import ssl
from pathlib import Path

_LOGGER = logging.getLogger(__name__)

CA_BUNDLE_PATH = Path(__file__).parent / "certs" / "sber_mqtt_broker.pem"


def build_ssl_context(verify: bool = True) -> ssl.SSLContext:
    """Создаёт SSL-контекст для подключения к брокеру Сбера.

    verify=True  — проверка сертификата по закреплённому PEM и по имени хоста.
                   Блокирующая функция (читает файл) — вызывать из executor /
                   потока paho. Бросает FileNotFoundError, если файла нет:
                   молча откатываться на «без проверки» нельзя.
    verify=False — шифрование есть, но сертификат и имя хоста не проверяются
                   (уязвимо к подмене сервера). Включается явно в настройках.
    """
    if not verify:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False  # порядок важен: сначала hostname,
        ctx.verify_mode = ssl.CERT_NONE  # потом verify_mode
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        return ctx

    if not CA_BUNDLE_PATH.is_file():
        raise FileNotFoundError(
            f"Не найден файл с сертификатом брокера Сбера: {CA_BUNDLE_PATH}"
        )

    ctx = ssl.create_default_context()  # CERT_REQUIRED + check_hostname
    ctx.load_verify_locations(cafile=str(CA_BUNDLE_PATH))
    # Закреплён листовой сертификат, а не CA — без этого флага OpenSSL
    # не примет его как якорь доверия
    ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx
