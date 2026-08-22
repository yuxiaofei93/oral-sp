from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient

from modules.accounts.models import Role, RoleCode
from modules.cases.models import CaseVersion, PhysicalExamAsset, VersionStatus

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
def test_teacher_can_edit_default_patient_style_and_override_it_per_case():
    teacher = make_user("13800138105", RoleCode.TEACHER)
    client = APIClient()
    client.force_authenticate(teacher)

    template_url = reverse("teacher-patient-prompt-template")
    template = client.get(template_url)
    assert template.status_code == 200
    assert template.json()["name"] == "默认患者表达风格"
    assert "自然的日常汉语" in template.json()["content"]
    assert "certainty" not in template.json()["content"]

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
            "physical_exam": {"findings_text": "牙龈局部红肿。"},
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
            "physical_exam": {"findings_text": "右下后牙区牙龈红肿。"},
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
def test_publish_requires_physical_exam_findings():
    teacher = make_user("13800138108", RoleCode.TEACHER)
    client = APIClient()
    client.force_authenticate(teacher)
    created = client.post(reverse("teacher-case-list"), {}, format="json")
    case_id = created.json()["case_id"]
    client.patch(
        reverse("teacher-case-draft", kwargs={"case_id": case_id}),
        {
            "patient_profile": {"opening_statement": "医生您好，我牙龈疼。"},
            "facts": [{"code": "pain", "standard_fact": "牙龈疼痛三天"}],
        },
        format="json",
    )

    response = client.post(reverse("teacher-case-publish", kwargs={"case_id": case_id}))

    assert response.status_code == 400
    assert response.json()["detail"] == "发布前必须填写口腔体格检查所见。"


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


@pytest.mark.django_db
def test_teacher_uploads_private_physical_exam_media_and_publish_snapshots_it(
    settings,
    tmp_path,
):
    settings.MEDIA_ROOT = tmp_path
    teacher = make_user("13800138107", RoleCode.TEACHER)
    client = APIClient()
    client.force_authenticate(teacher)
    created = client.post(reverse("teacher-case-list"), {}, format="json")
    case_id = created.json()["case_id"]
    draft_url = reverse("teacher-case-draft", kwargs={"case_id": case_id})
    configured = client.patch(
        draft_url,
        {
            "expected_updated_at": created.json()["updated_at"],
            "patient_profile": {"opening_statement": "医生您好，我牙龈疼。"},
            "physical_exam": {
                "findings_text": "右下后牙区牙龈红肿，局部可见瘘管。",
            },
            "facts": [{"code": "pain", "standard_fact": "牙龈疼痛三天"}],
        },
        format="json",
    )
    assert configured.status_code == 200

    image_buffer = BytesIO()
    Image.new("RGB", (12, 8), color=(180, 20, 30)).save(image_buffer, format="JPEG")
    upload_url = reverse(
        "teacher-physical-exam-asset-upload",
        kwargs={"case_id": case_id},
    )
    rejected = client.post(
        upload_url,
        {
            "kind": "image",
            "file": SimpleUploadedFile(
                "口内照片.jpg",
                image_buffer.getvalue(),
                content_type="image/jpeg",
            ),
            "deidentified_confirmed": False,
            "expected_updated_at": configured.json()["updated_at"],
        },
        format="multipart",
    )
    assert rejected.status_code == 400

    uploaded_image = client.post(
        upload_url,
        {
            "kind": "image",
            "file": SimpleUploadedFile(
                "口内照片.jpg",
                image_buffer.getvalue(),
                content_type="image/jpeg",
            ),
            "deidentified_confirmed": True,
            "expected_updated_at": configured.json()["updated_at"],
        },
        format="multipart",
    )
    assert uploaded_image.status_code == 201
    image_data = uploaded_image.json()["physical_exam"]["images"][0]
    assert image_data["filename"] == "口内照片.jpg"
    image_link = PhysicalExamAsset.objects.get(pk=image_data["id"])
    assert image_link.stored_asset.object_key.endswith(".jpg")
    assert image_link.stored_asset.deidentified_confirmed is True

    image_content = client.get(
        reverse(
            "teacher-physical-exam-asset-content",
            kwargs={"case_id": case_id, "asset_id": image_data["id"]},
        )
    )
    assert image_content.status_code == 200
    assert image_content["Content-Type"] == "image/jpeg"
    assert image_content["X-Content-Type-Options"] == "nosniff"

    uploaded_attachment = client.post(
        upload_url,
        {
            "kind": "attachment",
            "file": SimpleUploadedFile(
                "任意资料.custom",
                b"private attachment",
                content_type="application/x-custom",
            ),
            "deidentified_confirmed": True,
            "expected_updated_at": uploaded_image.json()["updated_at"],
        },
        format="multipart",
    )
    assert uploaded_attachment.status_code == 201
    attachment_data = uploaded_attachment.json()["physical_exam"]["attachments"][0]
    attachment_content = client.get(
        reverse(
            "teacher-physical-exam-asset-content",
            kwargs={"case_id": case_id, "asset_id": attachment_data["id"]},
        )
    )
    assert attachment_content.status_code == 200
    assert attachment_content["Content-Type"] == "application/octet-stream"
    assert "attachment;" in attachment_content["Content-Disposition"]

    published_response = client.post(
        reverse("teacher-case-publish", kwargs={"case_id": case_id})
    )
    assert published_response.status_code == 201
    published = CaseVersion.objects.get(pk=published_response.json()["version"]["id"])
    assert published.physical_exam.findings_text == configured.json()["physical_exam"][
        "findings_text"
    ]
    assert published.physical_exam.assets.count() == 2

    deleted = client.delete(
        reverse(
            "teacher-physical-exam-asset-delete",
            kwargs={"case_id": case_id, "asset_id": image_data["id"]},
        ),
        {"expected_updated_at": uploaded_attachment.json()["updated_at"]},
        format="json",
    )
    assert deleted.status_code == 200
    assert deleted.json()["physical_exam"]["images"] == []
    assert published.physical_exam.assets.count() == 2
    assert image_link.stored_asset_id in published.physical_exam.assets.values_list(
        "stored_asset_id", flat=True
    )
