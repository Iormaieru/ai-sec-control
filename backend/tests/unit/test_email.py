import smtplib

import pytest

from app.core import email
from app.core.config import Settings


def _use(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> None:
    settings = Settings(_env_file=None, **overrides)
    monkeypatch.setattr(email, "get_settings", lambda: settings)


def _enviar() -> None:
    email.send_email(to="ana@proveedor.com", subject="Asunto", text="texto", html="<p>html</p>")


def test_backend_console_no_abre_conexion(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, email_backend="console")
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: pytest.fail("no debería conectar"))

    _enviar()


def test_backend_smtp_sin_host_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, email_backend="smtp", smtp_host=None)

    with pytest.raises(email.EmailNoEnviado, match="AISEC_SMTP_HOST"):
        _enviar()


def test_backend_desconocido_falla(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, email_backend="paloma")

    with pytest.raises(email.EmailNoEnviado, match="desconocido"):
        _enviar()


def test_backend_smtp_envia_con_starttls_y_login(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, email_backend="smtp", smtp_host="relay.local", smtp_user="u", smtp_password="p")
    llamadas: list[str] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            llamadas.append(f"connect {host}:{port}")

        def __enter__(self) -> "FakeSMTP":
            return self

        def __exit__(self, *exc: object) -> None:
            pass

        def starttls(self) -> None:
            llamadas.append("starttls")

        def login(self, user: str, password: str) -> None:
            llamadas.append(f"login {user}")

        def send_message(self, message: object) -> None:
            llamadas.append(f"send {message['To']}")

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    _enviar()

    assert llamadas == ["connect relay.local:587", "starttls", "login u", "send ana@proveedor.com"]


def test_error_smtp_se_traduce_a_email_no_enviado(monkeypatch: pytest.MonkeyPatch) -> None:
    _use(monkeypatch, email_backend="smtp", smtp_host="relay.local")

    def _rechaza(*_a: object, **_k: object) -> None:
        raise ConnectionRefusedError

    monkeypatch.setattr(smtplib, "SMTP", _rechaza)

    with pytest.raises(email.EmailNoEnviado):
        _enviar()
