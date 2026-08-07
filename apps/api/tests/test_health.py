import pytest
from django.urls import reverse

from config.settings import database_config


def test_sqlite_database_config_is_tuned_for_the_native_deployment(monkeypatch):
    monkeypatch.setenv("SQLITE_TIMEOUT_SECONDS", "20")

    config = database_config("sqlite:////home/nick/oral-sp/var/production.sqlite3")

    assert config == {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": "/home/nick/oral-sp/var/production.sqlite3",
        "OPTIONS": {
            "timeout": 20,
            "transaction_mode": "IMMEDIATE",
        },
    }


def test_live_endpoint_does_not_require_authentication(client):
    response = client.get(reverse("health-live"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "oral-sp-api"}
    assert response.headers["Cache-Control"] == (
        "max-age=0, no-cache, no-store, must-revalidate, private"
    )


@pytest.mark.django_db
def test_ready_endpoint_checks_database(client):
    response = client.get(reverse("health-ready"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ready"}
