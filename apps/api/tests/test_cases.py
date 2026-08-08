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
    assert client.get(reverse("teacher-patient-prompt-template")).status_code == 403


@pytest.mark.django_db
def test_teacher_can_create_and_update_structured_case_draft():
    teacher = make_user("13800138101", RoleCode.TEACHER)
    client = APIClient()
    client.force_authenticate(teacher)

    created = client.post(
        reverse("teacher-case-list"),
        {
            "title_internal": "内部病例名称",
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.json()["case_code"] == "CASE-000001"
    assert "title_student" not in created.json()
    case_id = created.json()["case_id"]

    updated = client.patch(
        reverse("teacher-case-draft", kwargs={"case_id": case_id}),
        {
            "expected_updated_at": created.json()["updated_at"],
            "patient_profile": {
                "display_name": "陈女士",
                "age": 55,
                "sex": "female",
                "opening_statement": "医生您好，我的牙龈反复疼痛。",
            },
            "facts": [
                {
                    "code": "history.duration",
                    "standard_fact": "病程约三年",
                }
            ],
        },
        format="json",
    )

    assert updated.status_code == 200
    assert updated.json()["patient_profile"]["age"] == 55
    assert updated.json()["facts"][0]["code"] == "history.duration"
    assert updated.json()["facts"][0]["standard_fact"] == "病程约三年"
    assert updated.json()["facts"][0]["patient_expression"] == "病程约三年"


@pytest.mark.django_db
def test_teacher_can_edit_default_patient_prompt_and_override_it_per_case():
    teacher = make_user("13800138105", RoleCode.TEACHER)
    client = APIClient()
    client.force_authenticate(teacher)

    template_url = reverse("teacher-patient-prompt-template")
    template = client.get(template_url)
    assert template.status_code == 200
    assert template.json()["name"] == "默认患者问诊模板"
    assert "口腔医学教学模拟" in template.json()["content"]

    updated_template = client.patch(
        template_url,
        {"content": "请以谨慎、简短的口语回答本次口腔疾病问诊。"},
        format="json",
    )
    assert updated_template.status_code == 200
    assert updated_template.json()["updated_by_name"] == teacher.display_name

    created = client.post(reverse("teacher-case-list"), {}, format="json")
    assert created.status_code == 201
    assert created.json()["patient_prompt_mode"] == "default"
    assert created.json()["patient_prompt"] == ""
    assert created.json()["effective_patient_prompt"] == updated_template.json()["content"]

    case_id = created.json()["case_id"]
    customized = client.patch(
        reverse("teacher-case-draft", kwargs={"case_id": case_id}),
        {
            "patient_prompt_mode": "custom",
            "patient_prompt": "请表现得有些紧张，只用一两句话回答。",
        },
        format="json",
    )
    assert customized.status_code == 200
    assert customized.json()["effective_patient_prompt"] == customized.json()["patient_prompt"]

    empty_custom = client.patch(
        reverse("teacher-case-draft", kwargs={"case_id": case_id}),
        {"patient_prompt_mode": "custom", "patient_prompt": "  "},
        format="json",
    )
    assert empty_custom.status_code == 400


@pytest.mark.django_db
def test_published_case_snapshots_default_patient_prompt():
    teacher = make_user("13800138106", RoleCode.TEACHER)
    client = APIClient()
    client.force_authenticate(teacher)
    template_url = reverse("teacher-patient-prompt-template")
    client.patch(template_url, {"content": "默认模板第一版。"}, format="json")

    created = client.post(reverse("teacher-case-list"), {}, format="json")
    case_id = created.json()["case_id"]
    draft_url = reverse("teacher-case-draft", kwargs={"case_id": case_id})
    client.patch(
        draft_url,
        {
            "patient_profile": {"opening_statement": "医生您好，我牙龈疼。"},
            "facts": [{"code": "pain", "standard_fact": "牙龈疼痛三天"}],
        },
        format="json",
    )

    first = client.post(reverse("teacher-case-publish", kwargs={"case_id": case_id}))
    assert first.status_code == 201
    first_version = CaseVersion.objects.get(pk=first.json()["version"]["id"])
    assert first_version.patient_prompt == "默认模板第一版。"

    client.patch(template_url, {"content": "默认模板第二版。"}, format="json")
    first_version.refresh_from_db()
    assert first_version.patient_prompt == "默认模板第一版。"
    assert client.get(draft_url).json()["effective_patient_prompt"] == "默认模板第二版。"

    second = client.post(reverse("teacher-case-publish", kwargs={"case_id": case_id}))
    assert second.status_code == 201
    second_version = CaseVersion.objects.get(pk=second.json()["version"]["id"])
    assert second_version.version_number == 2
    assert second_version.patient_prompt == "默认模板第二版。"


@pytest.mark.django_db
def test_publish_creates_immutable_snapshot_and_is_idempotent():
    teacher = make_user("13800138102", RoleCode.TEACHER)
    client = APIClient()
    client.force_authenticate(teacher)
    created = client.post(
        reverse("teacher-case-list"),
        {"title_internal": "病例二"},
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
                    "standard_fact": "口腔疼痛",
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
                    "standard_fact": "新事实",
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
        {"title_internal": "病例三"},
        format="json",
    )
    case_id = created.json()["case_id"]
    url = reverse("teacher-case-draft", kwargs={"case_id": case_id})
    stale_timestamp = created.json()["updated_at"]
    assert client.patch(url, {"difficulty": "basic"}, format="json").status_code == 200

    conflict = client.patch(
        url,
        {"expected_updated_at": stale_timestamp, "difficulty": "advanced"},
        format="json",
    )
    assert conflict.status_code == 409


@pytest.mark.django_db
def test_case_codes_are_generated_in_sequence():
    teacher = make_user("13800138104", RoleCode.TEACHER)
    client = APIClient()
    client.force_authenticate(teacher)

    first = client.post(
        reverse("teacher-case-list"),
        {},
        format="json",
    )
    second = client.post(
        reverse("teacher-case-list"),
        {"title_internal": "顺序病例二"},
        format="json",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["title_internal"] == "未命名病例"
    assert first.json()["case_code"] == "CASE-000001"
    assert second.json()["case_code"] == "CASE-000002"
