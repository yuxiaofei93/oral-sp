from rest_framework import serializers

from .models import (
    Case,
    CaseFact,
    CaseVersion,
    DiagnosisRule,
    PatientProfile,
    PatientPromptMode,
    PatientPromptTemplate,
    PhysicalExam,
    PhysicalExamAsset,
    ScoringItem,
    TestDefinition,
)
from .services import default_patient_prompt, effective_patient_prompt


class StringListField(serializers.ListField):
    child = serializers.CharField(max_length=160)


class PhysicalExamAssetUploadSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["image", "attachment"])
    file = serializers.FileField()
    deidentified_confirmed = serializers.BooleanField()
    expected_updated_at = serializers.DateTimeField()


class PhysicalExamAssetDeleteSerializer(serializers.Serializer):
    expected_updated_at = serializers.DateTimeField()


class PatientProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientProfile
        exclude = ["version"]
        read_only_fields = ["id"]


class PhysicalExamAssetSerializer(serializers.ModelSerializer):
    filename = serializers.CharField(source="stored_asset.original_name", read_only=True)
    content_type = serializers.CharField(source="stored_asset.content_type", read_only=True)
    size_bytes = serializers.IntegerField(source="stored_asset.size_bytes", read_only=True)
    deidentified_confirmed = serializers.BooleanField(
        source="stored_asset.deidentified_confirmed",
        read_only=True,
    )
    content_url = serializers.SerializerMethodField()

    class Meta:
        model = PhysicalExamAsset
        fields = [
            "id",
            "kind",
            "display_order",
            "filename",
            "content_type",
            "size_bytes",
            "deidentified_confirmed",
            "content_url",
        ]

    def get_content_url(self, link: PhysicalExamAsset) -> str:
        return (
            f"/api/teacher/cases/{link.version.case_id}/draft/"
            f"physical-exam/assets/{link.id}/content/"
        )


class PhysicalExamSerializer(serializers.ModelSerializer):
    images = serializers.SerializerMethodField()
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = PhysicalExam
        fields = ["findings_text", "consent_text", "images", "attachments"]
        extra_kwargs = {
            "findings_text": {"required": False, "allow_blank": True},
            "consent_text": {"required": False},
        }

    def _assets(self, exam: PhysicalExam, kind: str):
        return PhysicalExamAssetSerializer(
            exam.assets.filter(kind=kind).select_related("stored_asset", "version__case"),
            many=True,
        ).data

    def get_images(self, exam: PhysicalExam):
        return self._assets(exam, "image")

    def get_attachments(self, exam: PhysicalExam):
        return self._assets(exam, "attachment")

    def validate_consent_text(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("患者同意语不能为空。")
        return value.strip()


class CaseFactSerializer(serializers.ModelSerializer):
    patient_expression = serializers.CharField(required=False)

    class Meta:
        model = CaseFact
        exclude = ["version"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if "standard_fact" in attrs:
            attrs["patient_expression"] = attrs["standard_fact"]
        return attrs


class TestDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestDefinition
        exclude = ["version"]
        read_only_fields = ["id"]


class DiagnosisRuleSerializer(serializers.ModelSerializer):
    aliases = StringListField(required=False)
    supporting_evidence = StringListField(required=False)
    opposing_evidence = StringListField(required=False)

    class Meta:
        model = DiagnosisRule
        exclude = ["version"]
        read_only_fields = ["id"]


class ScoringItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScoringItem
        exclude = ["version"]
        read_only_fields = ["id"]


class PatientPromptTemplateSerializer(serializers.ModelSerializer):
    content = serializers.CharField(max_length=8000, trim_whitespace=False)
    updated_by_name = serializers.CharField(
        source="updated_by.display_name",
        read_only=True,
        default="",
    )

    class Meta:
        model = PatientPromptTemplate
        fields = ["id", "name", "content", "updated_by_name", "updated_at"]
        read_only_fields = ["id", "name", "updated_by_name", "updated_at"]

    def validate_content(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("默认提示词不能为空。")
        return value.strip()


class CaseDraftSerializer(serializers.ModelSerializer):
    case_id = serializers.UUIDField(source="case.id", read_only=True)
    case_code = serializers.CharField(source="case.code", read_only=True)
    patient_profile = PatientProfileSerializer(required=False)
    physical_exam = PhysicalExamSerializer(required=False)
    facts = CaseFactSerializer(many=True, required=False)
    tests = TestDefinitionSerializer(many=True, required=False)
    diagnosis_rules = DiagnosisRuleSerializer(many=True, required=False)
    scoring_items = ScoringItemSerializer(many=True, required=False)
    patient_prompt = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=8000,
        trim_whitespace=False,
    )
    effective_patient_prompt = serializers.SerializerMethodField()
    default_patient_prompt = serializers.SerializerMethodField()
    enabled_stages = StringListField(required=False)
    expected_updated_at = serializers.DateTimeField(write_only=True, required=False)

    class Meta:
        model = CaseVersion
        fields = [
            "id",
            "case_id",
            "case_code",
            "status",
            "version_number",
            "title_internal",
            "difficulty",
            "is_exam_mode",
            "time_limit_minutes",
            "enabled_stages",
            "patient_prompt_mode",
            "patient_prompt",
            "effective_patient_prompt",
            "default_patient_prompt",
            "created_at",
            "updated_at",
            "expected_updated_at",
            "patient_profile",
            "physical_exam",
            "facts",
            "tests",
            "diagnosis_rules",
            "scoring_items",
        ]
        read_only_fields = [
            "id",
            "status",
            "version_number",
            "effective_patient_prompt",
            "default_patient_prompt",
            "created_at",
            "updated_at",
        ]

    def get_effective_patient_prompt(self, version: CaseVersion) -> str:
        return effective_patient_prompt(version)

    def get_default_patient_prompt(self, version: CaseVersion) -> str:
        del version
        return default_patient_prompt()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        current_mode = getattr(self.instance, "patient_prompt_mode", PatientPromptMode.DEFAULT)
        current_prompt = getattr(self.instance, "patient_prompt", "")
        mode = attrs.get("patient_prompt_mode", current_mode)
        prompt = attrs.get("patient_prompt", current_prompt)
        if mode == PatientPromptMode.CUSTOM and not prompt.strip():
            raise serializers.ValidationError(
                {"patient_prompt": "使用自定义提示词时，提示词不能为空。"}
            )
        if mode == PatientPromptMode.DEFAULT and (
            "patient_prompt_mode" in attrs or "patient_prompt" in attrs
        ):
            attrs["patient_prompt"] = ""
        elif "patient_prompt" in attrs:
            attrs["patient_prompt"] = prompt.strip()
        return attrs


class CaseCreateSerializer(serializers.Serializer):
    title_internal = serializers.CharField(
        max_length=160,
        required=False,
        default="未命名病例",
    )


class CaseListSerializer(serializers.ModelSerializer):
    draft = serializers.SerializerMethodField()
    latest_published = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = ["id", "code", "is_active", "created_at", "draft", "latest_published"]

    def get_draft(self, case: Case):
        draft = next(
            (version for version in case.versions.all() if version.status == "draft"),
            None,
        )
        if draft is None:
            return None
        return {
            "id": draft.id,
            "title_internal": draft.title_internal,
            "updated_at": draft.updated_at,
        }

    def get_latest_published(self, case: Case):
        versions = [version for version in case.versions.all() if version.status == "published"]
        if not versions:
            return None
        version = max(versions, key=lambda item: item.version_number or 0)
        return {
            "id": version.id,
            "version_number": version.version_number,
            "published_at": version.published_at,
        }


class PublishedVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaseVersion
        fields = ["id", "version_number", "published_at", "content_hash"]
