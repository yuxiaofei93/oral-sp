from rest_framework import serializers

from .models import (
    Case,
    CaseFact,
    CaseVersion,
    DiagnosisRule,
    PatientProfile,
    ScoringItem,
    TestDefinition,
)


class StringListField(serializers.ListField):
    child = serializers.CharField(max_length=160)


class PatientProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientProfile
        exclude = ["version"]
        read_only_fields = ["id"]


class CaseFactSerializer(serializers.ModelSerializer):
    semantic_tags = StringListField(required=False)
    synonyms = StringListField(required=False)

    class Meta:
        model = CaseFact
        exclude = ["version"]
        read_only_fields = ["id"]


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


class CaseDraftSerializer(serializers.ModelSerializer):
    case_id = serializers.UUIDField(source="case.id", read_only=True)
    case_code = serializers.CharField(source="case.code", read_only=True)
    patient_profile = PatientProfileSerializer(required=False)
    facts = CaseFactSerializer(many=True, required=False)
    tests = TestDefinitionSerializer(many=True, required=False)
    diagnosis_rules = DiagnosisRuleSerializer(many=True, required=False)
    scoring_items = ScoringItemSerializer(many=True, required=False)
    disease_tags = StringListField(required=False)
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
            "title_student",
            "specialty",
            "disease_tags",
            "difficulty",
            "estimated_minutes",
            "teaching_objectives",
            "target_grade",
            "is_exam_mode",
            "time_limit_minutes",
            "enabled_stages",
            "created_at",
            "updated_at",
            "expected_updated_at",
            "patient_profile",
            "facts",
            "tests",
            "diagnosis_rules",
            "scoring_items",
        ]
        read_only_fields = ["id", "status", "version_number", "created_at", "updated_at"]


class CaseCreateSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^[A-Z0-9][A-Z0-9_-]*$", max_length=40)
    title_internal = serializers.CharField(max_length=160)
    title_student = serializers.CharField(max_length=160)

    def validate_code(self, value: str) -> str:
        if Case.objects.filter(code=value).exists():
            raise serializers.ValidationError("病例编号已经存在。")
        return value


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
            "title_student": draft.title_student,
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
