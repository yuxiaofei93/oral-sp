import re

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client
from django.urls import reverse

from modules.accounts.identifiers import normalize_email_identifier
from modules.accounts.models import (
    EmailVerificationCode,
    Role,
    RoleCode,
    VerificationPurpose,
)
from modules.accounts.permissions import IsStudent, IsTeacherOrAdministrator
from modules.accounts.verification import VerificationCodeError, consume_verification_code
from modules.teaching.models import ClassGroup, ClassMembership, Course

User = get_user_model()
PASSWORD = "MolarTraining!2026"
NEW_PASSWORD = "NewMolarTraining!2026"


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    cache.clear()


def make_registration_class(suffix: str) -> ClassGroup:
    teacher = User.objects.create_user(
        email=f"teacher-{suffix}@example.com",
        password=PASSWORD,
        display_name="测试教师",
    )
    course = Course.objects.create(
        code=f"REGISTER-{suffix}",
        name="注册课程",
        created_by=teacher,
    )
    return ClassGroup.objects.create(course=course, code="CLASS-A", name="注册班级")


def csrf_post(client: Client, url: str, payload: dict):
    csrf_token = client.get(reverse("auth-csrf")).json()["csrf_token"]
    return client.post(
        url,
        payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )


def latest_code() -> str:
    match = re.search(r"验证码是：(\d{6})", mail.outbox[-1].body)
    assert match is not None
    return match.group(1)


@pytest.mark.django_db
def test_superuser_requires_a_display_name():
    with pytest.raises(ValueError, match="必须提供姓名"):
        User.objects.create_superuser(email="admin@example.com", password=PASSWORD)

    administrator = User.objects.create_superuser(
        email=" ADMIN@Example.COM ",
        password=PASSWORD,
        display_name="  李一帆  ",
    )

    assert administrator.display_name == "李一帆"
    assert administrator.email == "admin@example.com"


def test_email_identifier_normalization():
    assert normalize_email_identifier(" Student.Name@Example.COM ") == "student.name@example.com"


@pytest.mark.django_db
def test_registration_code_requires_csrf_and_stores_only_a_hash():
    client = Client(enforce_csrf_checks=True)
    url = reverse("auth-registration-code")
    payload = {"email": " Student@Example.COM "}

    assert client.post(url, payload, content_type="application/json").status_code == 403
    response = csrf_post(client, url, payload)

    assert response.status_code == 200
    assert response.json()["expires_in"] == 600
    assert len(mail.outbox) == 1
    code = latest_code()
    record = EmailVerificationCode.objects.get()
    assert record.email == "student@example.com"
    assert record.code_hash != code
    assert code not in record.code_hash


@pytest.mark.django_db
def test_registration_assigns_student_role_and_consumes_code():
    class_group = make_registration_class("001")
    client = Client(enforce_csrf_checks=True)
    email = "student@example.com"
    csrf_post(client, reverse("auth-registration-code"), {"email": email})
    code = latest_code()

    response = csrf_post(
        client,
        reverse("auth-register"),
        {
            "email": email,
            "verification_code": code,
            "password": PASSWORD,
            "display_name": "测试学生",
            "class_group_id": str(class_group.id),
        },
    )

    assert response.status_code == 201
    assert response.json()["email"] == email
    assert response.json()["roles"] == [RoleCode.STUDENT]
    student = User.objects.get(email=email)
    assert student.check_password(PASSWORD)
    assert student.email_verified_at is not None
    assert ClassMembership.objects.filter(class_group=class_group, student=student).exists()
    assert EmailVerificationCode.objects.get().consumed_at is not None

    me_response = client.get(reverse("auth-me"))
    assert me_response.status_code == 200
    assert me_response.json()["display_name"] == "测试学生"

    assert client.post(reverse("auth-logout")).status_code == 403
    logout_response = csrf_post(client, reverse("auth-logout"), {})
    assert logout_response.status_code == 204
    assert client.get(reverse("auth-me")).status_code == 403


@pytest.mark.django_db
def test_registration_code_cannot_be_reused():
    first_class = make_registration_class("002")
    client = Client(enforce_csrf_checks=True)
    email = "first@example.com"
    csrf_post(client, reverse("auth-registration-code"), {"email": email})
    code = latest_code()
    first_payload = {
        "email": email,
        "verification_code": code,
        "password": PASSWORD,
        "display_name": "第一位学生",
        "class_group_id": str(first_class.id),
    }
    assert csrf_post(client, reverse("auth-register"), first_payload).status_code == 201

    with pytest.raises(VerificationCodeError, match="无效或已过期"):
        consume_verification_code(
            email=email,
            purpose=VerificationPurpose.REGISTRATION,
            code=code,
        )


@pytest.mark.django_db
def test_wrong_verification_code_is_limited_to_five_attempts():
    client = Client(enforce_csrf_checks=True)
    email = "attempts@example.com"
    csrf_post(client, reverse("auth-registration-code"), {"email": email})
    correct_code = latest_code()

    for attempt in range(5):
        with pytest.raises(VerificationCodeError, match="错误|次数过多"):
            consume_verification_code(
                email=email,
                purpose=VerificationPurpose.REGISTRATION,
                code="000000" if correct_code != "000000" else "999999",
            )
        assert EmailVerificationCode.objects.get().failed_attempts == attempt + 1

    with pytest.raises(VerificationCodeError, match="次数过多"):
        consume_verification_code(
            email=email,
            purpose=VerificationPurpose.REGISTRATION,
            code=correct_code,
        )


@pytest.mark.django_db
def test_verification_code_resend_has_a_cooldown():
    client = Client(enforce_csrf_checks=True)
    url = reverse("auth-registration-code")
    assert csrf_post(client, url, {"email": "cooldown@example.com"}).status_code == 200

    response = csrf_post(client, url, {"email": "cooldown@example.com"})

    assert response.status_code == 429
    assert int(response["Retry-After"]) > 0
    assert response.json()["retry_after"] > 0


@pytest.mark.django_db
def test_login_normalizes_email_and_returns_a_generic_error():
    User.objects.create_user(email="student@example.com", password=PASSWORD, display_name="学生乙")
    client = Client(enforce_csrf_checks=True)

    failed = csrf_post(
        client,
        reverse("auth-login"),
        {"email": "unknown@example.com", "password": "wrong-password"},
    )
    assert failed.status_code == 400
    assert failed.json() == {"detail": "邮箱或密码错误。"}

    response = csrf_post(
        client,
        reverse("auth-login"),
        {"email": " STUDENT@Example.COM ", "password": PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "student@example.com"


@pytest.mark.django_db
def test_password_reset_is_generic_for_unknown_email_and_changes_password():
    user = User.objects.create_user(
        email="reset@example.com",
        password=PASSWORD,
        display_name="重置密码学生",
    )
    client = Client(enforce_csrf_checks=True)
    code_url = reverse("auth-password-reset-code")

    unknown = csrf_post(client, code_url, {"email": "unknown@example.com"})
    assert unknown.status_code == 200
    assert unknown.json() == {"detail": "如果该邮箱已注册，验证码将发送到邮箱。"}
    assert len(mail.outbox) == 0

    sent = csrf_post(client, code_url, {"email": user.email})
    assert sent.status_code == 200
    code = latest_code()
    reset_payload = {
        "email": user.email,
        "verification_code": code,
        "new_password": NEW_PASSWORD,
    }
    reset_response = csrf_post(client, reverse("auth-password-reset"), reset_payload)

    assert reset_response.status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    replay = csrf_post(client, reverse("auth-password-reset"), reset_payload)
    assert replay.status_code == 400
    assert "verification_code" in replay.json()


@pytest.mark.django_db
def test_registration_code_rejects_an_existing_email():
    User.objects.create_user(
        email="existing@example.com",
        password=PASSWORD,
        display_name="已有账号",
    )
    client = Client(enforce_csrf_checks=True)

    response = csrf_post(
        client,
        reverse("auth-registration-code"),
        {"email": "EXISTING@example.com"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "该邮箱已经注册。"}
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_registration_class_list_only_exposes_active_choices():
    active = make_registration_class("004")
    inactive_class = ClassGroup.objects.create(
        course=active.course,
        code="CLASS-B",
        name="停用班级",
        is_active=False,
    )
    inactive_course_class = make_registration_class("005")
    inactive_course_class.course.is_active = False
    inactive_course_class.course.save(update_fields=["is_active"])

    response = Client().get(reverse("auth-registration-classes"))

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(active.id),
            "code": active.code,
            "name": active.name,
            "course_id": str(active.course_id),
            "course_code": active.course.code,
            "course_name": active.course.name,
        }
    ]
    assert str(inactive_class.id) not in str(response.json())


@pytest.mark.django_db
def test_registration_rejects_an_inactive_class_before_consuming_code():
    class_group = make_registration_class("006")
    class_group.is_active = False
    class_group.save(update_fields=["is_active"])
    client = Client(enforce_csrf_checks=True)
    email = "inactive-class@example.com"
    csrf_post(client, reverse("auth-registration-code"), {"email": email})
    code = latest_code()

    response = csrf_post(
        client,
        reverse("auth-register"),
        {
            "email": email,
            "verification_code": code,
            "password": PASSWORD,
            "display_name": "不可入班学生",
            "class_group_id": str(class_group.id),
        },
    )

    assert response.status_code == 400
    assert "class_group_id" in response.json()
    assert not User.objects.filter(email=email).exists()
    assert EmailVerificationCode.objects.get().consumed_at is None


@pytest.mark.django_db
def test_role_permissions_distinguish_students_and_teachers():
    user = User.objects.create_user(
        email="permission-student@example.com",
        password=PASSWORD,
        display_name="权限测试学生",
    )
    user.roles.add(Role.objects.get(code=RoleCode.STUDENT), through_defaults={})

    request = type("Request", (), {"user": user})()
    assert IsStudent().has_permission(request, None) is True
    assert IsTeacherOrAdministrator().has_permission(request, None) is False
