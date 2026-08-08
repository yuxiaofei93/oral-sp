import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import (
    Case,
    CaseCodeSequence,
    CaseFact,
    CaseVersion,
    DiagnosisRule,
    PatientProfile,
    PatientPromptMode,
    PatientPromptTemplate,
    ScoringItem,
    TestDefinition,
    VersionStatus,
)
from .prompts import (
    DEFAULT_PATIENT_PROMPT,
    PATIENT_PROMPT_TEMPLATE_ID,
    PATIENT_PROMPT_TEMPLATE_NAME,
)


class DraftConflictError(Exception):
    pass


class PublishValidationError(Exception):
    pass


@dataclass(frozen=True)
class PublishResult:
    version: CaseVersion
    created: bool


def get_patient_prompt_template() -> PatientPromptTemplate:
    template, _ = PatientPromptTemplate.objects.get_or_create(
        pk=PATIENT_PROMPT_TEMPLATE_ID,
        defaults={
            "name": PATIENT_PROMPT_TEMPLATE_NAME,
            "content": DEFAULT_PATIENT_PROMPT,
        },
    )
    return template


def default_patient_prompt() -> str:
    template = PatientPromptTemplate.objects.filter(pk=PATIENT_PROMPT_TEMPLATE_ID).first()
    if template and template.content.strip():
        return template.content.strip()
    return DEFAULT_PATIENT_PROMPT


def effective_patient_prompt(version: CaseVersion) -> str:
    configured = version.patient_prompt.strip()
    if version.patient_prompt_mode == PatientPromptMode.CUSTOM:
        return configured or DEFAULT_PATIENT_PROMPT
    if version.status == VersionStatus.PUBLISHED and configured:
        return configured
    return default_patient_prompt()


def create_case_with_draft(*, title_internal: str, user) -> Case:
    with transaction.atomic():
        sequence = CaseCodeSequence.objects.select_for_update().get(pk=1)
        sequence.last_value += 1
        sequence.save(update_fields=["last_value"])
        case = Case.objects.create(
            code=f"CASE-{sequence.last_value:06d}",
            created_by=user,
        )
        draft = CaseVersion.objects.create(
            case=case,
            status=VersionStatus.DRAFT,
            title_internal=title_internal,
            created_by=user,
        )
        PatientProfile.objects.create(version=draft)
        return case


def update_draft(*, draft: CaseVersion, data: dict) -> CaseVersion:
    expected_updated_at: datetime | None = data.pop("expected_updated_at", None)
    nested = {
        name: data.pop(name)
        for name in ("patient_profile", "facts", "tests", "diagnosis_rules", "scoring_items")
        if name in data
    }

    with transaction.atomic():
        locked = CaseVersion.objects.select_for_update().get(pk=draft.pk)
        if expected_updated_at and locked.updated_at != expected_updated_at:
            raise DraftConflictError("病例草稿已被其他操作更新，请刷新后重试。")

        for field, value in data.items():
            setattr(locked, field, value)

        if "patient_profile" in nested:
            profile, _ = PatientProfile.objects.get_or_create(version=locked)
            for field, value in nested["patient_profile"].items():
                setattr(profile, field, value)
            profile.save()

        replacement_models = {
            "facts": (CaseFact, locked.facts),
            "tests": (TestDefinition, locked.tests),
            "diagnosis_rules": (DiagnosisRule, locked.diagnosis_rules),
            "scoring_items": (ScoringItem, locked.scoring_items),
        }
        for name, (model, manager) in replacement_models.items():
            if name not in nested:
                continue
            manager.all().delete()
            for item in nested[name]:
                item.pop("id", None)
                if name == "facts":
                    item["patient_expression"] = item["standard_fact"]
                model.objects.create(version=locked, **item)

        locked.save()
        return locked


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def draft_content(draft: CaseVersion) -> dict:
    scalar_fields = [
        "title_internal",
        "difficulty",
        "is_exam_mode",
        "time_limit_minutes",
        "enabled_stages",
        "patient_prompt_mode",
    ]
    profile_fields = [
        "display_name",
        "age",
        "sex",
        "occupation",
        "education",
        "personality",
        "emotion",
        "cooperation",
        "medical_literacy",
        "opening_statement",
        "avatar_asset_id",
        "voice_id",
    ]
    child_fields = {
        "facts": [
            field.name for field in CaseFact._meta.fields if field.name not in {"id", "version"}
        ],
        "tests": [
            field.name
            for field in TestDefinition._meta.fields
            if field.name not in {"id", "version"}
        ],
        "diagnosis_rules": [
            field.name
            for field in DiagnosisRule._meta.fields
            if field.name not in {"id", "version"}
        ],
        "scoring_items": [
            field.name for field in ScoringItem._meta.fields if field.name not in {"id", "version"}
        ],
    }
    profile = draft.patient_profile
    content = {field: _json_value(getattr(draft, field)) for field in scalar_fields}
    content["patient_prompt"] = effective_patient_prompt(draft)
    content["patient_profile"] = {
        field: _json_value(getattr(profile, field)) for field in profile_fields
    }
    for related_name, fields in child_fields.items():
        content[related_name] = [
            {field: _json_value(getattr(item, field)) for field in fields}
            for item in getattr(draft, related_name).all()
        ]
    return content


def _content_hash(content: dict) -> str:
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def publish_draft(*, draft: CaseVersion, user) -> PublishResult:
    with transaction.atomic():
        locked = (
            CaseVersion.objects.select_for_update()
            .select_related("case", "patient_profile")
            .get(pk=draft.pk, status=VersionStatus.DRAFT)
        )
        if not locked.patient_profile.opening_statement.strip():
            raise PublishValidationError("发布前必须填写患者开场白。")
        if not locked.facts.exists():
            raise PublishValidationError("发布前至少需要一条病情信息。")

        content = draft_content(locked)
        digest = _content_hash(content)
        patient_prompt = effective_patient_prompt(locked)
        latest = (
            CaseVersion.objects.filter(case=locked.case, status=VersionStatus.PUBLISHED)
            .order_by("-version_number")
            .first()
        )
        if latest and latest.content_hash == digest:
            return PublishResult(version=latest, created=False)

        max_version = CaseVersion.objects.filter(case=locked.case).aggregate(
            maximum=Max("version_number")
        )["maximum"]
        published = CaseVersion.objects.create(
            case=locked.case,
            status=VersionStatus.PUBLISHED,
            version_number=(max_version or 0) + 1,
            title_internal=locked.title_internal,
            difficulty=locked.difficulty,
            is_exam_mode=locked.is_exam_mode,
            time_limit_minutes=locked.time_limit_minutes,
            enabled_stages=locked.enabled_stages,
            patient_prompt_mode=locked.patient_prompt_mode,
            patient_prompt=patient_prompt,
            based_on=latest,
            created_by=user,
            published_at=timezone.now(),
            content_hash=digest,
        )

        profile_values = {
            field.name: getattr(locked.patient_profile, field.name)
            for field in PatientProfile._meta.fields
            if field.name not in {"id", "version"}
        }
        PatientProfile.objects.bulk_create([PatientProfile(version=published, **profile_values)])

        for model, related_name in (
            (CaseFact, "facts"),
            (TestDefinition, "tests"),
            (DiagnosisRule, "diagnosis_rules"),
            (ScoringItem, "scoring_items"),
        ):
            field_names = [
                field.name for field in model._meta.fields if field.name not in {"id", "version"}
            ]
            copies = [
                model(
                    version=published,
                    **{field: getattr(item, field) for field in field_names},
                )
                for item in getattr(locked, related_name).all()
            ]
            model.objects.bulk_create(copies)

        return PublishResult(version=published, created=True)
