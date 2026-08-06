import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from modules.accounts.models import Role, RoleCode
from modules.cases.models import CaseVersion, VersionStatus

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
def test_students_cannot_access_teacher_case_api():
    student = make_user("13800138100", RoleCode.STUDENT)
    client = APIClient()
    client.force_authenticate(student)

    assert client.get(reverse("teacher-case-list")).status_code == 403


@pytest.mark.django_db
def test_teacher_can_create_and_update_structured_case_draft():
    teacher = make_user("13800138101", RoleCode.TEACHER)
    client = APIClient()
    client.force_authenticate(teacher)

    created = client.post(
        reverse("teacher-case-list"),
        {
            "code": "OM-001",
            "title_internal": "内部病例名称",
            "title_student": "牙龈疼痛病例",
        },
        format="json",
    )
    assert created.status_code == 201
    case_id = created.json()["case_id"]

    updated = client.patch(
        reverse("teacher-case-draft", kwargs={"case_id": case_id}),
        {
            "expected_updated_at": created.json()["updated_at"],
            "teaching_objectives": "训练系统病史采集",
            "patient_profile": {
                "display_name": "陈女士",
                "age": 55,
                "sex": "female",
                "opening_statement": "医生您好，我的牙龈反复疼痛。",
            },
            "facts": [
                {
                    "code": "history.duration",
                    "category": "present_illness",
                    "standard_fact": "病程约三年",
                    "patient_expression": "差不多三年了。",
                    "semantic_tags": ["病程", "多久"],
                    "is_required": True,
                    "score": "2.00",
                }
            ],
        },
        format="json",
    )

    assert updated.status_code == 200
    assert updated.json()["patient_profile"]["age"] == 55
    assert updated.json()["facts"][0]["code"] == "history.duration"


@pytest.mark.django_db
def test_publish_creates_immutable_snapshot_and_is_idempotent():
    teacher = make_user("13800138102", RoleCode.TEACHER)
    client = APIClient()
    client.force_authenticate(teacher)
    created = client.post(
        reverse("teacher-case-list"),
        {"code": "OM-002", "title_internal": "病例二", "title_student": "口腔不适病例"},
        format="json",
    )
    case_id = created.json()["case_id"]
    draft_url = reverse("teacher-case-draft", kwargs={"case_id": case_id})
    client.patch(
        draft_url,
        {
            "patient_profile": {"opening_statement": "医生您好，我口腔不舒服。"},
            "facts": [
                {
                    "code": "chief.issue",
                    "category": "chief_complaint",
                    "standard_fact": "口腔疼痛",
                    "patient_expression": "嘴里有点痛。",
                }
            ],
        },
        format="json",
    )

    first = client.post(reverse("teacher-case-publish", kwargs={"case_id": case_id}))
    assert first.status_code == 201
    assert first.json()["version"]["version_number"] == 1

    second = client.post(reverse("teacher-case-publish", kwargs={"case_id": case_id}))
    assert second.status_code == 200
    assert second.json()["created"] is False

    published = CaseVersion.objects.get(case_id=case_id, status=VersionStatus.PUBLISHED)
    published_fact = published.facts.get(code="chief.issue")
    client.patch(
        draft_url,
        {
            "facts": [
                {
                    "code": "new.fact",
                    "category": "other",
                    "standard_fact": "新事实",
                    "patient_expression": "新回答",
                }
            ]
        },
        format="json",
    )
    assert published.facts.get().standard_fact == "口腔疼痛"

    published_fact.standard_fact = "试图修改"
    with pytest.raises(ValidationError):
        published_fact.save()

    with pytest.raises(ValidationError):
        published.delete()


@pytest.mark.django_db
def test_draft_update_rejects_stale_timestamp():
    teacher = make_user("13800138103", RoleCode.TEACHER)
    client = APIClient()
    client.force_authenticate(teacher)
    created = client.post(
        reverse("teacher-case-list"),
        {"code": "OM-003", "title_internal": "病例三", "title_student": "学生病例三"},
        format="json",
    )
    case_id = created.json()["case_id"]
    url = reverse("teacher-case-draft", kwargs={"case_id": case_id})
    stale_timestamp = created.json()["updated_at"]
    assert client.patch(url, {"specialty": "口腔黏膜科"}, format="json").status_code == 200

    conflict = client.patch(
        url,
        {"expected_updated_at": stale_timestamp, "specialty": "牙周科"},
        format="json",
    )
    assert conflict.status_code == 409
