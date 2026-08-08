import logging
import re
import secrets
import traceback
from datetime import timedelta
from time import monotonic

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from modules.core.observability import current_request_id

from .identifiers import normalize_email_identifier
from .models import EmailVerificationCode, VerificationPurpose

CODE_TTL_SECONDS = 600
CODE_RESEND_SECONDS = 60
CODE_MAX_ATTEMPTS = 5
logger = logging.getLogger(__name__)


class VerificationCodeError(Exception):
    pass


class VerificationCodeCooldownError(VerificationCodeError):
    def __init__(self, retry_after: int):
        super().__init__(f"请在 {retry_after} 秒后重新获取验证码。")
        self.retry_after = retry_after


class VerificationEmailError(VerificationCodeError):
    pass


def _email_reference(email: str) -> str:
    return salted_hmac("accounts.email-log-reference", email).hexdigest()[:12]


def _safe_error_message(error: Exception) -> str:
    message = str(error)
    message = re.sub(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        "<redacted-email>",
        message,
        flags=re.IGNORECASE,
    )
    return message[:500]


def _code_hash(*, email: str, purpose: str, code: str) -> str:
    value = f"{normalize_email_identifier(email)}:{purpose}:{code}"
    return salted_hmac("accounts.email-verification", value).hexdigest()


def send_verification_email(*, email: str, purpose: str) -> None:
    normalized = normalize_email_identifier(email)
    now = timezone.now()
    latest = EmailVerificationCode.objects.filter(
        email=normalized,
        purpose=purpose,
    ).order_by("-created_at").first()
    if latest:
        elapsed = int((now - latest.created_at).total_seconds())
        if elapsed < CODE_RESEND_SECONDS:
            raise VerificationCodeCooldownError(CODE_RESEND_SECONDS - elapsed)

    code = f"{secrets.randbelow(1_000_000):06d}"
    record = EmailVerificationCode.objects.create(
        email=normalized,
        purpose=purpose,
        code_hash=_code_hash(email=normalized, purpose=purpose, code=code),
        expires_at=now + timedelta(seconds=CODE_TTL_SECONDS),
    )
    action = "注册" if purpose == VerificationPurpose.REGISTRATION else "重置密码"
    log_context = {
        "backend": settings.EMAIL_BACKEND,
        "email_ref": _email_reference(normalized),
        "purpose": purpose,
        "record_id": str(record.pk),
        "request_id": current_request_id(),
        "smtp_host": settings.EMAIL_HOST,
        "smtp_port": settings.EMAIL_PORT,
        "use_ssl": settings.EMAIL_USE_SSL,
        "use_tls": settings.EMAIL_USE_TLS,
    }
    started_at = monotonic()
    logger.info("verification_email.started", extra=log_context)
    try:
        sent_count = send_mail(
            subject=f"口腔模拟问诊系统{action}验证码",
            message=(
                f"你的{action}验证码是：{code}\n\n"
                f"验证码 {CODE_TTL_SECONDS // 60} 分钟内有效，请勿转发给他人。"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[normalized],
            fail_silently=False,
        )
    except Exception as error:
        record.delete()
        logger.error(
            "verification_email.failed",
            extra={
                **log_context,
                "duration_ms": round((monotonic() - started_at) * 1000),
                "error_type": type(error).__name__,
                "error_message": _safe_error_message(error),
                "stack_trace": "".join(traceback.format_tb(error.__traceback__)),
            },
        )
        raise VerificationEmailError("验证码邮件发送失败，请稍后重试。") from error

    if sent_count != 1:
        record.delete()
        logger.error(
            "verification_email.failed",
            extra={
                **log_context,
                "duration_ms": round((monotonic() - started_at) * 1000),
                "error_type": "UnexpectedDeliveryCount",
                "error_message": (
                    f"Email backend reported {sent_count} delivered messages; expected 1."
                ),
            },
        )
        raise VerificationEmailError("验证码邮件发送失败，请稍后重试。")

    logger.info(
        "verification_email.sent",
        extra={
            **log_context,
            "duration_ms": round((monotonic() - started_at) * 1000),
        },
    )

    EmailVerificationCode.objects.filter(
        email=normalized,
        purpose=purpose,
        consumed_at__isnull=True,
    ).exclude(pk=record.pk).update(consumed_at=now)


def consume_verification_code(*, email: str, purpose: str, code: str) -> None:
    normalized = normalize_email_identifier(email)
    now = timezone.now()
    verification_error = ""
    with transaction.atomic():
        record = EmailVerificationCode.objects.select_for_update().filter(
            email=normalized,
            purpose=purpose,
            consumed_at__isnull=True,
        ).order_by("-created_at").first()
        if record is None or record.expires_at <= now:
            raise VerificationCodeError("验证码无效或已过期。")
        if record.failed_attempts >= CODE_MAX_ATTEMPTS:
            raise VerificationCodeError("验证码尝试次数过多，请重新获取。")
        expected = _code_hash(email=normalized, purpose=purpose, code=code)
        if not constant_time_compare(record.code_hash, expected):
            record.failed_attempts += 1
            record.save(update_fields=["failed_attempts"])
            if record.failed_attempts >= CODE_MAX_ATTEMPTS:
                verification_error = "验证码尝试次数过多，请重新获取。"
            else:
                verification_error = "验证码错误。"
        else:
            record.consumed_at = now
            record.save(update_fields=["consumed_at"])
    if verification_error:
        raise VerificationCodeError(verification_error)
