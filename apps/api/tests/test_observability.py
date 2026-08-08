import json
import logging
import smtplib
import uuid
from unittest.mock import patch

import pytest
from django.core.checks import run_checks
from django.test import Client, override_settings
from django.urls import reverse

from modules.accounts.models import EmailVerificationCode
from modules.core.observability import JsonFormatter


def csrf_post(client: Client, url: str, payload: dict, **headers):
    csrf_token = client.get(reverse("auth-csrf"), **headers).json()["csrf_token"]
    return client.post(
        url,
        payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
        **headers,
    )


def test_request_id_is_returned_and_logged(client, caplog):
    caplog.set_level(logging.INFO, logger="oral_sp.request")

    response = client.get(reverse("health-live"), HTTP_X_REQUEST_ID="support-case-123")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "support-case-123"
    completed = next(record for record in caplog.records if record.msg == "request.completed")
    assert completed.request_id == "support-case-123"
    assert completed.path == "/api/health/live/"
    assert completed.status_code == 200


def test_invalid_request_id_is_replaced(client):
    response = client.get(reverse("health-live"), HTTP_X_REQUEST_ID="invalid id with spaces")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "invalid id with spaces"
    assert len(response.headers["X-Request-ID"]) == 32


@pytest.mark.django_db
def test_email_success_log_is_correlated_without_recipient_or_code(caplog):
    caplog.set_level(logging.INFO)
    client = Client(enforce_csrf_checks=True)
    recipient = "student.secret@example.com"

    response = csrf_post(
        client,
        reverse("auth-registration-code"),
        {"email": recipient},
        HTTP_X_REQUEST_ID="mail-success-123",
    )

    assert response.status_code == 200
    sent = next(record for record in caplog.records if record.msg == "verification_email.sent")
    payload = JsonFormatter().format(sent)
    assert sent.request_id == "mail-success-123"
    assert sent.backend == "django.core.mail.backends.locmem.EmailBackend"
    assert recipient not in payload
    assert "验证码是" not in payload


@pytest.mark.django_db
def test_email_failure_is_correlated_and_redacted(caplog):
    caplog.set_level(logging.INFO)
    client = Client(enforce_csrf_checks=True)
    recipient = "student.secret@example.com"
    smtp_error = smtplib.SMTPAuthenticationError(
        535,
        b"Authentication failed while sending to student.secret@example.com",
    )

    with patch("modules.accounts.verification.send_mail", side_effect=smtp_error):
        response = csrf_post(
            client,
            reverse("auth-registration-code"),
            {"email": recipient},
            HTTP_X_REQUEST_ID="mail-failure-123",
        )

    assert response.status_code == 503
    assert response.headers["X-Request-ID"] == "mail-failure-123"
    assert response.json() == {
        "detail": "验证码邮件发送失败，请稍后重试。",
        "request_id": "mail-failure-123",
    }
    assert not EmailVerificationCode.objects.exists()
    failed = next(record for record in caplog.records if record.msg == "verification_email.failed")
    assert failed.request_id == "mail-failure-123"
    assert failed.error_type == "SMTPAuthenticationError"
    assert "<redacted-email>" in failed.error_message
    assert recipient not in failed.error_message
    assert "verification.py" in failed.stack_trace


def test_json_formatter_emits_safe_diagnostic_fields():
    record = logging.LogRecord(
        name="modules.accounts.verification",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="verification_email.failed",
        args=(),
        exc_info=None,
    )
    record.request_id = "mail-failure-123"
    record.email_ref = "abc123def456"
    record.error_type = "SMTPAuthenticationError"
    record.record_id = uuid.UUID("b709a64a-36c4-4016-aece-e9d2ffdccd44")

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "verification_email.failed"
    assert payload["request_id"] == "mail-failure-123"
    assert payload["email_ref"] == "abc123def456"
    assert payload["error_type"] == "SMTPAuthenticationError"
    assert payload["record_id"] == "b709a64a-36c4-4016-aece-e9d2ffdccd44"


@override_settings(
    DEBUG=False,
    EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    EMAIL_USE_TLS=False,
    EMAIL_USE_SSL=False,
)
def test_production_check_rejects_console_email_backend():
    errors = run_checks()

    assert "oral_sp.E001" in {error.id for error in errors}


@override_settings(
    DEBUG=False,
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="smtp.example.com",
    EMAIL_HOST_USER="mailer@example.com",
    EMAIL_HOST_PASSWORD="authorization-code",
    DEFAULT_FROM_EMAIL="mailer@example.com",
    EMAIL_USE_TLS=True,
    EMAIL_USE_SSL=True,
)
def test_production_check_rejects_conflicting_smtp_encryption():
    errors = run_checks()

    assert "oral_sp.E002" in {error.id for error in errors}


@override_settings(
    DEBUG=False,
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="",
    EMAIL_HOST_USER="",
    EMAIL_HOST_PASSWORD="",
    DEFAULT_FROM_EMAIL="",
    EMAIL_USE_TLS=False,
    EMAIL_USE_SSL=True,
)
def test_production_check_rejects_incomplete_smtp_configuration():
    errors = run_checks()

    assert "oral_sp.E003" in {error.id for error in errors}
