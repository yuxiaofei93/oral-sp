import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from modules.accounts.models import Role, RoleCode
from modules.teaching.models import ClassGroup, ClassMembership, Course, CourseTeacher

User = get_user_model()
PASSWORD = "MolarTraining!2026"


def make_user(phone: str, role_code: str):
    user = User.objects.create_user(phone=phone, password=PASSWORD, display_name=role_code)
    user.roles.add(Role.objects.get(code=role_code))
    return user


@pytest.mark.django_db
def test_teacher_creates_course_class_and_imports_registered_students_atomically():
    teacher = make_user("13700000001", RoleCode.TEACHER)
    student = make_user("13600000001", RoleCode.STUDENT)
    client = APIClient()
    client.force_authenticate(teacher)

    course_response = client.post(
        reverse("teacher-course-list"),
        {"code": "ORAL-2026", "name": "口腔问诊训练"},
        format="json",
    )
    assert course_response.status_code == 201
    course_id = course_response.json()["id"]
    assert CourseTeacher.objects.filter(course_id=course_id, teacher=teacher).exists()

    class_response = client.post(
        reverse("teacher-class-create"),
        {"course_id": course_id, "code": "CLASS-A", "name": "A 班"},
        format="json",
    )
    assert class_response.status_code == 201
    class_id = class_response.json()["id"]
    assert class_response.json()["course_id"] == course_id

    roster_url = reverse("teacher-class-roster", kwargs={"class_id": class_id})
    rejected = client.post(
        roster_url,
        {"phones": [student.phone, "13699999999"]},
        format="json",
    )
    assert rejected.status_code == 400
    assert rejected.json()["missing"] == ["+8613699999999"]
    assert ClassMembership.objects.filter(class_group_id=class_id).count() == 0

    imported = client.post(
        roster_url,
        {"phones": ["13600000001", "+86 136 0000 0001"]},
        format="json",
    )
    assert imported.status_code == 200
    assert imported.json() == {"created_count": 1, "existing_count": 0}

    course_list = client.get(reverse("teacher-course-list"))
    assert course_list.json()[0]["class_count"] == 1
    class_list = client.get(reverse("teacher-class-create"))
    roster = class_list.json()[0]
    assert roster["student_count"] == 1
    assert roster["students"][0]["display_name"] == RoleCode.STUDENT


@pytest.mark.django_db
def test_non_student_account_is_rejected_from_class_roster():
    teacher = make_user("13700000002", RoleCode.TEACHER)
    other_teacher = make_user("13700000003", RoleCode.TEACHER)
    course = Course.objects.create(code="ORAL-OTHER", name="课程", created_by=teacher)
    CourseTeacher.objects.create(course=course, teacher=teacher)
    class_group = course.classes.create(code="CLASS-B", name="B 班")
    client = APIClient()
    client.force_authenticate(teacher)

    response = client.post(
        reverse("teacher-class-roster", kwargs={"class_id": class_group.id}),
        {"phones": [other_teacher.phone]},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["not_students"] == [other_teacher.phone]
    assert not class_group.memberships.exists()


@pytest.mark.django_db
def test_teacher_cannot_view_or_modify_another_teachers_courses():
    owner = make_user("13700000004", RoleCode.TEACHER)
    outsider = make_user("13700000005", RoleCode.TEACHER)
    student = make_user("13600000005", RoleCode.STUDENT)
    course = Course.objects.create(code="PRIVATE", name="其他教师课程", created_by=owner)
    CourseTeacher.objects.create(course=course, teacher=owner)
    class_group = course.classes.create(code="PRIVATE-A", name="内部班级")
    client = APIClient()
    client.force_authenticate(outsider)

    assert client.get(reverse("teacher-course-list")).json() == []
    assert client.get(reverse("teacher-class-create")).json() == []
    roster_response = client.post(
        reverse("teacher-class-roster", kwargs={"class_id": class_group.id}),
        {"phones": [student.phone]},
        format="json",
    )
    assert roster_response.status_code == 404

    assert client.delete(
        reverse("teacher-course-detail", kwargs={"course_id": course.id})
    ).status_code == 404


@pytest.mark.django_db
def test_teacher_archives_course_without_deleting_historical_structure():
    teacher = make_user("13700000007", RoleCode.TEACHER)
    course = Course.objects.create(code="ARCHIVE", name="待删除课程", created_by=teacher)
    CourseTeacher.objects.create(course=course, teacher=teacher)
    class_group = ClassGroup.objects.create(course=course, code="CLASS-A", name="历史班级")
    client = APIClient()
    client.force_authenticate(teacher)

    response = client.delete(
        reverse("teacher-course-detail", kwargs={"course_id": course.id})
    )

    assert response.status_code == 204
    course.refresh_from_db()
    class_group.refresh_from_db()
    assert course.is_active is False
    assert class_group.is_active is False
    assert Course.objects.filter(pk=course.id).exists()
    assert client.get(reverse("teacher-course-list")).json() == []
    assert client.get(reverse("teacher-class-create")).json() == []


@pytest.mark.django_db
def test_student_cannot_access_teaching_management_api():
    student = make_user("13600000006", RoleCode.STUDENT)
    client = APIClient()
    client.force_authenticate(student)

    assert client.get(reverse("teacher-course-list")).status_code == 403
    assert client.get(reverse("teacher-class-create")).status_code == 403
