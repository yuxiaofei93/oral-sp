from rest_framework import serializers

from .models import (
    Case,
    CaseFact,
    CaseVersion,
    DiagnosisRule,
    PatientFollowUpMode,
    PatientFollowUpTemplate,
    PatientProfile,
    PatientPromptMode,
    PatientPromptTemplate,
    PhysicalExam,
    PhysicalExamAsset,
    ScoringItem,
    TestDefinition,
)
from .services import (
    default_patient_follow_up,
    default_patient_style,
    effective_patient_follow_up,
    effective_patient_style,
)


class StringListField(serializers.ListField):
    child = serializers.CharField(max_length=160)


class PatientFollowUpQuestionsField(serializers.ListField):
    child = serializers.CharField(max_length=500)


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
            raise serializers.ValidationError("默认表达风格不能为空。")
        return value.strip()


class PatientFollowUpTemplateSerializer(serializers.ModelSerializer):
    questions = PatientFollowUpQuestionsField(allow_empty=False)
    closing_text = serializers.CharField(max_length=500)
    updated_by_name = serializers.CharField(
        source="updated_by.display_name",
        read_only=True,
        default="",
    )

    class Meta:
        model = PatientFollowUpTemplate
        fields = [
            "id",
            "name",
            "questions",
            "closing_text",
            "updated_by_name",
            "updated_at",
        ]
        read_only_fields = ["id", "name", "updated_by_name", "updated_at"]

    def validate_questions(self, value: list[str]) -> list[str]:
        return [question.strip() for question in value]

    def validate_closing_text(self, value: str) -> str:
        if not value.strip():
            raise serializers.ValidationError("主动问答收尾语不能为空。")
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
    patient_follow_up_questions = PatientFollowUpQuestionsField(
        required=False,
        allow_empty=True,
    )
    patient_follow_up_closing_text = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
    )
    effective_patient_follow_up_questions = serializers.SerializerMethodField()
    effective_patient_follow_up_closing_text = serializers.SerializerMethodField()
    default_patient_follow_up_questions = serializers.SerializerMethodField()
    default_patient_follow_up_closing_text = serializers.SerializerMethodField()
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
            "patient_follow_up_mode",
            "patient_follow_up_questions",
            "patient_follow_up_closing_text",
            "effective_patient_follow_up_questions",
            "effective_patient_follow_up_closing_text",
            "default_patient_follow_up_questions",
            "default_patient_follow_up_closing_text",
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
            "effective_patient_follow_up_questions",
            "effective_patient_follow_up_closing_text",
            "default_patient_follow_up_questions",
            "default_patient_follow_up_closing_text",
            "created_at",
            "updated_at",
        ]

    def get_effective_patient_prompt(self, version: CaseVersion) -> str:
        return effective_patient_style(version)

    def get_default_patient_prompt(self, version: CaseVersion) -> str:
        del version
        return default_patient_style()

    def get_effective_patient_follow_up_questions(self, version: CaseVersion) -> list[str]:
        return effective_patient_follow_up(version)[0]

    def get_effective_patient_follow_up_closing_text(self, version: CaseVersion) -> str:
        return effective_patient_follow_up(version)[1]

    def get_default_patient_follow_up_questions(self, version: CaseVersion) -> list[str]:
        del version
        return default_patient_follow_up()[0]

    def get_default_patient_follow_up_closing_text(self, version: CaseVersion) -> str:
        del version
        return default_patient_follow_up()[1]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        current_mode = getattr(self.instance, "patient_prompt_mode", PatientPromptMode.DEFAULT)
        current_prompt = getattr(self.instance, "patient_prompt", "")
        mode = attrs.get("patient_prompt_mode", current_mode)
        prompt = attrs.get("patient_prompt", current_prompt)
        if mode == PatientPromptMode.CUSTOM and not prompt.strip():
            raise serializers.ValidationError(
                {"patient_prompt": "使用自定义表达风格时，内容不能为空。"}
            )
        if mode == PatientPromptMode.DEFAULT and (
            "patient_prompt_mode" in attrs or "patient_prompt" in attrs
        ):
            attrs["patient_prompt"] = ""
        elif "patient_prompt" in attrs:
            attrs["patient_prompt"] = prompt.strip()

        current_follow_up_mode = getattr(
            self.instance,
            "patient_follow_up_mode",
            PatientFollowUpMode.DEFAULT,
        )
        current_questions = getattr(self.instance, "patient_follow_up_questions", [])
        current_closing = getattr(self.instance, "patient_follow_up_closing_text", "")
        follow_up_mode = attrs.get("patient_follow_up_mode", current_follow_up_mode)
        questions = attrs.get("patient_follow_up_questions", current_questions)
        closing = attrs.get("patient_follow_up_closing_text", current_closing)
        if follow_up_mode == PatientFollowUpMode.CUSTOM:
            errors = {}
            if not questions:
                errors["patient_follow_up_questions"] = "自定义主动询问至少需要一个问题。"
            if not closing.strip():
                errors["patient_follow_up_closing_text"] = "自定义主动问答收尾语不能为空。"
            if errors:
                raise serializers.ValidationError(errors)
            attrs["patient_follow_up_questions"] = [item.strip() for item in questions]
            attrs["patient_follow_up_closing_text"] = closing.strip()
        elif (
            "patient_follow_up_mode" in attrs
            or "patient_follow_up_questions" in attrs
            or "patient_follow_up_closing_text" in attrs
        ):
            attrs["patient_follow_up_questions"] = []
            attrs["patient_follow_up_closing_text"] = ""
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
