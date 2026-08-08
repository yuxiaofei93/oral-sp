from django.conf import settings
from django.core.checks import Error, register

CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"
SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"


@register()
def email_configuration_check(app_configs, **kwargs):
    errors = []
    if settings.EMAIL_USE_TLS and settings.EMAIL_USE_SSL:
        errors.append(
            Error(
                "EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled.",
                hint="Use TLS with port 587 or SSL with port 465.",
                id="oral_sp.E002",
            )
        )

    if settings.DEBUG:
        return errors

    if settings.EMAIL_BACKEND == CONSOLE_BACKEND:
        errors.append(
            Error(
                "The console email backend cannot deliver production verification emails.",
                hint=f"Set EMAIL_BACKEND={SMTP_BACKEND} and configure the SMTP credentials.",
                id="oral_sp.E001",
            )
        )

    if settings.EMAIL_BACKEND == SMTP_BACKEND:
        required_settings = {
            "EMAIL_HOST": settings.EMAIL_HOST,
            "EMAIL_HOST_USER": settings.EMAIL_HOST_USER,
            "EMAIL_HOST_PASSWORD": settings.EMAIL_HOST_PASSWORD,
            "DEFAULT_FROM_EMAIL": settings.DEFAULT_FROM_EMAIL,
        }
        missing = [name for name, value in required_settings.items() if not value]
        if settings.EMAIL_HOST == "localhost":
            missing.append("EMAIL_HOST")
        if "no-reply@localhost" in settings.DEFAULT_FROM_EMAIL:
            missing.append("DEFAULT_FROM_EMAIL")
        if missing:
            errors.append(
                Error(
                    "The production SMTP configuration is incomplete.",
                    hint=f"Set these values in .env.production: {', '.join(sorted(set(missing)))}.",
                    id="oral_sp.E003",
                )
            )
    return errors
