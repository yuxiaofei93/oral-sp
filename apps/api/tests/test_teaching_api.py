import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from modules.accounts.models import Role, RoleCode
from modules.teaching.models import ClassGroup, ClassMembership

User = get_user_model()
PASSWORD = "MolarTraining!2026"


def make_user(identifier: str, role_code: str):
    user = User.objects.create_user(
        email=f"{identifier}@example.com",
        password=PASSWORD,
        display_name=role_code,
    )
    user.roles.add(Role.objects.get(code=role_code))
    return user


@pytest.mark.django_db
def test_teacher_creates_a_class_and_views_registered_students():
    teacher = make_user("teacher-1", RoleCode.TEACHER)
    student = make_user("student-1", RoleCode.STUDENT)
    client = APIClient()
    client.force_authenticate(teacher)

    response = client.post(
        reverse("teacher-class-list"),
        {"name": "A 班"},
        format="json",
    )

    assert response.status_code == 201
    class_group = ClassGroup.objects.get(pk=response.json()["id"])
    assert class_group.created_by == teacher
    ClassMembership.objects.create(class_group=class_group, student=student)

    roster = client.get(reverse("teacher-class-list")).json()[0]
    assert roster["code"] == f"CLASS-{class_group.id.hex.upper()}"
    assert roster["created_by_name"] == RoleCode.TEACHER
    assert roster["student_count"] == 1
    assert roster["students"][0]["display_name"] == RoleCode.STUDENT
    assert roster["students"][0]["email"] == student.email


@pytest.mark.django_db
def test_class_code_is_generated_automatically_and_is_unique():
    teacher = make_user("teacher-2", RoleCode.TEACHER)
    client = APIClient()
    client.force_authenticate(teacher)

    first_response = client.post(
        reverse("teacher-class-list"),
        {"name": "一班"},
        format="json",
    )
    second_response = client.post(
        reverse("teacher-class-list"),
        {"name": "二班"},
        format="json",
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["code"].startswith("CLASS-")
    assert second_response.json()["code"].startswith("CLASS-")
    assert first_response.json()["code"] != second_response.json()["code"]


@pytest.mark.django_db
def test_teacher_cannot_view_or_modify_another_teachers_class():
    owner = make_user("teacher-owner", RoleCode.TEACHER)
    outsider = make_user("teacher-outsider", RoleCode.TEACHER)
    student = make_user("student-private", RoleCode.STUDENT)
    class_group = ClassGroup.objects.create(
        code="PRIVATE-A",
        name="内部班级",
        created_by=owner,
    )
    ClassMembership.objects.create(class_group=class_group, student=student)
    client = APIClient()
    client.force_authenticate(outsider)

    assert client.get(reverse("teacher-class-list")).json() == []
    assert client.delete(
        reverse("teacher-class-detail", kwargs={"class_id": class_group.id})
    ).status_code == 404
    assert client.patch(
        reverse("teacher-class-detail", kwargs={"class_id": class_group.id}),
        {"is_active": False},
        format="json",
    ).status_code == 404
    assert client.delete(
        reverse(
            "teacher-class-roster-member",
            kwargs={"class_id": class_group.id, "student_id": student.id},
        )
    ).status_code == 404
    assert class_group.memberships.filter(student=student).exists()


@pytest.mark.django_db
def test_teacher_archives_class_without_deleting_historical_structure():
    teacher = make_user("teacher-archive", RoleCode.TEACHER)
    class_group = ClassGroup.objects.create(
        code="ARCHIVE-A",
        name="历史班级",
        created_by=teacher,
    )
    client = APIClient()
    client.force_authenticate(teacher)

    response = client.delete(
        reverse("teacher-class-detail", kwargs={"class_id": class_group.id})
    )

    assert response.status_code == 204
    class_group.refresh_from_db()
    assert class_group.is_active is False
    assert ClassGroup.objects.filter(pk=class_group.id).exists()
    archived_class = client.get(reverse("teacher-class-list")).json()[0]
    assert archived_class["id"] == str(class_group.id)
    assert archived_class["is_active"] is False


@pytest.mark.django_db
def test_teacher_freezes_and_reactivates_owned_class():
    teacher = make_user("teacher-status", RoleCode.TEACHER)
    class_group = ClassGroup.objects.create(
        code="STATUS-A",
        name="状态班级",
        created_by=teacher,
    )
    client = APIClient()
    client.force_authenticate(teacher)

    freeze_response = client.patch(
        reverse("teacher-class-detail", kwargs={"class_id": class_group.id}),
        {"is_active": False},
        format="json",
    )

    assert freeze_response.status_code == 204
    class_group.refresh_from_db()
    assert class_group.is_active is False

    activate_response = client.patch(
        reverse("teacher-class-detail", kwargs={"class_id": class_group.id}),
        {"is_active": True},
        format="json",
    )

    assert activate_response.status_code == 204
    class_group.refresh_from_db()
    assert class_group.is_active is True


@pytest.mark.django_db
def test_teacher_transfers_student_to_another_owned_class():
    teacher = make_user("teacher-transfer", RoleCode.TEACHER)
    student = make_user("student-transfer", RoleCode.STUDENT)
    source_class = ClassGroup.objects.create(
        code="TRANSFER-A",
        name="原班级",
        created_by=teacher,
    )
    target_class = ClassGroup.objects.create(
        code="TRANSFER-B",
        name="目标班级",
        created_by=teacher,
    )
    ClassMembership.objects.create(class_group=source_class, student=student)
    client = APIClient()
    client.force_authenticate(teacher)

    response = client.patch(
        reverse(
            "teacher-class-roster-member",
            kwargs={"class_id": source_class.id, "student_id": student.id},
        ),
        {"target_class_id": str(target_class.id)},
        format="json",
    )

    assert response.status_code == 204
    assert not ClassMembership.objects.filter(
        class_group=source_class,
        student=student,
    ).exists()
    assert ClassMembership.objects.filter(
        class_group=target_class,
        student=student,
    ).exists()


@pytest.mark.django_db
def test_teacher_cannot_transfer_student_to_another_teachers_class():
    teacher = make_user("teacher-transfer-owner", RoleCode.TEACHER)
    other_teacher = make_user("teacher-transfer-other", RoleCode.TEACHER)
    student = make_user("student-transfer-private", RoleCode.STUDENT)
    source_class = ClassGroup.objects.create(
        code="TRANSFER-PRIVATE-A",
        name="原班级",
        created_by=teacher,
    )
    target_class = ClassGroup.objects.create(
        code="TRANSFER-PRIVATE-B",
        name="其他教师班级",
        created_by=other_teacher,
    )
    ClassMembership.objects.create(class_group=source_class, student=student)
    client = APIClient()
    client.force_authenticate(teacher)

    response = client.patch(
        reverse(
            "teacher-class-roster-member",
            kwargs={"class_id": source_class.id, "student_id": student.id},
        ),
        {"target_class_id": str(target_class.id)},
        format="json",
    )

    assert response.status_code == 404
    assert ClassMembership.objects.filter(
        class_group=source_class,
        student=student,
    ).exists()


@pytest.mark.django_db
def test_teacher_cannot_transfer_student_to_the_same_class():
    teacher = make_user("teacher-transfer-same", RoleCode.TEACHER)
    student = make_user("student-transfer-same", RoleCode.STUDENT)
    class_group = ClassGroup.objects.create(
        code="TRANSFER-SAME",
        name="当前班级",
        created_by=teacher,
    )
    ClassMembership.objects.create(class_group=class_group, student=student)
    client = APIClient()
    client.force_authenticate(teacher)

    response = client.patch(
        reverse(
            "teacher-class-roster-member",
            kwargs={"class_id": class_group.id, "student_id": student.id},
        ),
        {"target_class_id": str(class_group.id)},
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_student_transfer"
    assert ClassMembership.objects.filter(
        class_group=class_group,
        student=student,
    ).exists()


@pytest.mark.django_db
def test_student_cannot_access_class_management_api():
    student = make_user("student-no-access", RoleCode.STUDENT)
    client = APIClient()
    client.force_authenticate(student)

    assert client.get(reverse("teacher-class-list")).status_code == 403


@pytest.mark.django_db
def test_administrator_lists_student_details_and_filters_by_name_email_and_class():
    administrator = make_user("administrator-students", RoleCode.ADMINISTRATOR)
    teacher = make_user("teacher-students", RoleCode.TEACHER)
    first_student = make_user("lin-xiaoya", RoleCode.STUDENT)
    first_student.display_name = "林晓雅"
    first_student.save(update_fields=["display_name"])
    second_student = make_user("wang-ming", RoleCode.STUDENT)
    second_student.display_name = "王明"
    second_student.save(update_fields=["display_name"])
    first_class = ClassGroup.objects.create(
        code="STUDENT-A",
        name="口腔一班",
        created_by=teacher,
    )
    second_class = ClassGroup.objects.create(
        code="STUDENT-B",
        name="口腔二班",
        created_by=teacher,
    )
    ClassMembership.objects.create(class_group=first_class, student=first_student)
    ClassMembership.objects.create(class_group=second_class, student=second_student)
    client = APIClient()
    client.force_authenticate(administrator)

    response = client.get(reverse("managed-student-list"))

    assert response.status_code == 200
    assert [item["display_name"] for item in response.json()] == ["林晓雅", "王明"]
    first_record = response.json()[0]
    assert first_record["email"] == first_student.email
    assert first_record["classes"] == [
        {
            "id": str(first_class.id),
            "code": "STUDENT-A",
            "name": "口腔一班",
            "is_active": True,
        }
    ]
    assert first_record["is_active"] is True
    assert first_record["date_joined"]

    assert [
        item["id"]
        for item in client.get(reverse("managed-student-list"), {"name": "晓雅"}).json()
    ] == [str(first_student.id)]
    assert [
        item["id"]
        for item in client.get(
            reverse("managed-student-list"),
            {"email": "WANG-MING"},
        ).json()
    ] == [str(second_student.id)]
    assert [
        item["id"]
        for item in client.get(
            reverse("managed-student-list"),
            {"class_group_id": str(first_class.id)},
        ).json()
    ] == [str(first_student.id)]

    detail = client.get(
        reverse("managed-student-detail", kwargs={"student_id": first_student.id})
    )
    assert detail.status_code == 200
    assert detail.json() == first_record


@pytest.mark.django_db
def test_administrator_changes_a_students_class():
    administrator = make_user("administrator-transfer", RoleCode.ADMINISTRATOR)
    teacher = make_user("teacher-admin-transfer", RoleCode.TEACHER)
    student = make_user("student-admin-transfer", RoleCode.STUDENT)
    source_class = ClassGroup.objects.create(
        code="ADMIN-TRANSFER-A",
        name="原班级",
        created_by=teacher,
    )
    target_class = ClassGroup.objects.create(
        code="ADMIN-TRANSFER-B",
        name="目标班级",
        created_by=teacher,
    )
    ClassMembership.objects.create(class_group=source_class, student=student)
    client = APIClient()
    client.force_authenticate(administrator)

    response = client.patch(
        reverse("managed-student-detail", kwargs={"student_id": student.id}),
        {"class_group_id": str(target_class.id)},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["classes"][0]["id"] == str(target_class.id)
    assert not ClassMembership.objects.filter(
        class_group=source_class,
        student=student,
    ).exists()
    assert ClassMembership.objects.filter(
        class_group=target_class,
        student=student,
    ).exists()


@pytest.mark.django_db
def test_teacher_cannot_access_administrator_student_management_api():
    teacher = make_user("teacher-no-student-management", RoleCode.TEACHER)
    student = make_user("student-private-management", RoleCode.STUDENT)
    client = APIClient()
    client.force_authenticate(teacher)

    assert client.get(reverse("managed-student-list")).status_code == 403
    assert client.get(
        reverse("managed-student-detail", kwargs={"student_id": student.id})
    ).status_code == 403
