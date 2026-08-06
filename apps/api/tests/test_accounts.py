import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from modules.accounts.models import Role, RoleCode
from modules.accounts.permissions import IsStudent, IsTeacherOrAdministrator
from modules.accounts.phone import normalize_phone
from modules.teaching.models import ClassGroup, ClassMembership, Course

User = get_user_model()
PASSWORD = "MolarTraining!2026"


def make_registration_class(suffix: str) -> ClassGroup:
    teacher = User.objects.create_user(
        phone=f"13710000{suffix}",
        password=PASSWORD,
        display_name="测试教师",
    )
    course = Course.objects.create(
        code=f"REGISTER-{suffix}",
        name="注册课程",
        created_by=teacher,
    )
    return ClassGroup.objects.create(course=course, code="CLASS-A", name="注册班级")


@pytest.mark.django_db
def test_superuser_requires_a_display_name():
    with pytest.raises(ValueError, match="必须提供姓名"):
        User.objects.create_superuser(phone="13900139999", password=PASSWORD)

    administrator = User.objects.create_superuser(
        phone="13900139999",
        password=PASSWORD,
        display_name="  李一帆  ",
    )

    assert administrator.display_name == "李一帆"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("13800138000", "+8613800138000"),
        ("86 138-0013-8000", "+8613800138000"),
        ("0086 138 0013 8000", "+8613800138000"),
        ("+86 138 0013 8000", "+8613800138000"),
    ],
)
def test_phone_normalization(source, expected):
    assert normalize_phone(source) == expected


@pytest.mark.django_db
def test_registration_requires_csrf_and_assigns_student_role():
    class_group = make_registration_class("001")
    client = Client(enforce_csrf_checks=True)
    payload = {
        "phone": "13800138000",
        "password": PASSWORD,
        "display_name": "测试学生",
        "class_group_id": str(class_group.id),
    }

    rejected = client.post(reverse("auth-register"), payload, content_type="application/json")
    assert rejected.status_code == 403

    csrf_response = client.get(reverse("auth-csrf"))
    csrf_token = csrf_response.json()["csrf_token"]
    response = client.post(
        reverse("auth-register"),
        payload,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )

    assert response.status_code == 201
    assert response.json()["phone"] == "+8613800138000"
    assert response.json()["roles"] == [RoleCode.STUDENT]
    student = User.objects.get(phone="+8613800138000")
    assert student.check_password(PASSWORD)
    assert ClassMembership.objects.filter(class_group=class_group, student=student).exists()

    me_response = client.get(reverse("auth-me"))
    assert me_response.status_code == 200
    assert me_response.json()["display_name"] == "测试学生"

    logout_without_csrf = client.post(reverse("auth-logout"))
    assert logout_without_csrf.status_code == 403

    logout_csrf_token = client.get(reverse("auth-csrf")).json()["csrf_token"]
    logout_response = client.post(reverse("auth-logout"), HTTP_X_CSRFTOKEN=logout_csrf_token)
    assert logout_response.status_code == 204
    assert client.get(reverse("auth-me")).status_code == 403


@pytest.mark.django_db
def test_login_uses_normalized_phone_and_returns_generic_error():
    User.objects.create_user(phone="+8613900139000", password=PASSWORD, display_name="学生乙")
    client = Client(enforce_csrf_checks=True)
    csrf_token = client.get(reverse("auth-csrf")).json()["csrf_token"]

    failed = client.post(
        reverse("auth-login"),
        {"phone": "13900139000", "password": "wrong-password"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    assert failed.status_code == 400
    assert failed.json() == {"detail": "手机号或密码错误。"}

    response = client.post(
        reverse("auth-login"),
        {"phone": "13900139000", "password": PASSWORD},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    assert response.status_code == 200
    assert response.json()["phone"] == "+8613900139000"


@pytest.mark.django_db
def test_duplicate_phone_registration_is_rejected():
    class_group = make_registration_class("002")
    User.objects.create_user(phone="13800138000", password=PASSWORD, display_name="已有学生")
    client = Client(enforce_csrf_checks=True)
    csrf_token = client.get(reverse("auth-csrf")).json()["csrf_token"]

    response = client.post(
        reverse("auth-register"),
        {
            "phone": "+86 138 0013 8000",
            "password": PASSWORD,
            "display_name": "重复学生",
            "class_group_id": str(class_group.id),
        },
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )

    assert response.status_code == 400
    assert response.json()["phone"] == ["该手机号已经注册。"]


@pytest.mark.django_db
def test_registration_class_list_only_exposes_active_choices():
    active = make_registration_class("003")
    inactive_class = ClassGroup.objects.create(
        course=active.course,
        code="CLASS-B",
        name="停用班级",
        is_active=False,
    )
    inactive_course_class = make_registration_class("004")
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
def test_registration_rejects_an_inactive_class():
    class_group = make_registration_class("005")
    class_group.is_active = False
    class_group.save(update_fields=["is_active"])

    response = Client().post(
        reverse("auth-register"),
        {
            "phone": "13800138009",
            "password": PASSWORD,
            "display_name": "不可入班学生",
            "class_group_id": str(class_group.id),
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert "class_group_id" in response.json()
    assert not User.objects.filter(phone="+8613800138009").exists()


@pytest.mark.django_db
def test_role_permissions_distinguish_students_and_teachers():
    user = User.objects.create_user(
        phone="13800138003",
        password=PASSWORD,
        display_name="权限测试学生",
    )
    user.roles.add(Role.objects.get(code=RoleCode.STUDENT), through_defaults={})

    request = type("Request", (), {"user": user})()
    assert IsStudent().has_permission(request, None) is True
    assert IsTeacherOrAdministrator().has_permission(request, None) is False
