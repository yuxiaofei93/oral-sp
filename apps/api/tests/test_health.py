import pytest
from django.urls import reverse


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
