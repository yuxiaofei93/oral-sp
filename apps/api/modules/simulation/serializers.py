from rest_framework import serializers

from modules.cases.models import CaseVersion, VersionStatus
from modules.teaching.models import ClassGroup

from .models import (
    CaseAssignment,
    Message,
    SimulationSession,
    StageSubmission,
    SubmissionType,
)
from .services import remaining_seconds


class AssignmentCreateSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=160)
    case_version_id = serializers.PrimaryKeyRelatedField(
        source="case_version",
        queryset=CaseVersion.objects.filter(status=VersionStatus.PUBLISHED),
    )
    class_group_id = serializers.PrimaryKeyRelatedField(
        source="class_group",
        queryset=ClassGroup.objects.filter(is_active=True),
    )
    duration_minutes = serializers.IntegerField(min_value=1, max_value=240)
    opens_at = serializers.DateTimeField()
    deadline_at = serializers.DateTimeField()

    def validate(self, attrs):
        if attrs["deadline_at"] <= attrs["opens_at"]:
            raise serializers.ValidationError({"deadline_at": "截止时间必须晚于开放时间。"})
        return attrs


class TeacherAssignmentSerializer(serializers.ModelSerializer):
    case_version_id = serializers.UUIDField(read_only=True)
    class_group_id = serializers.UUIDField(read_only=True)
    case_title = serializers.CharField(source="case_version.title_internal", read_only=True)
    case_version_number = serializers.IntegerField(
        source="case_version.version_number",
        read_only=True,
    )
    class_name = serializers.CharField(source="class_group.name", read_only=True)
    course_name = serializers.CharField(source="class_group.course.name", read_only=True)
    student_count = serializers.IntegerField(read_only=True)
    submitted_count = serializers.IntegerField(read_only=True)
    active_count = serializers.IntegerField(read_only=True)
    expired_count = serializers.IntegerField(read_only=True)
    not_started_count = serializers.SerializerMethodField()

    def get_not_started_count(self, assignment):
        return max(0, assignment.student_count - assignment.session_count)

    class Meta:
        model = CaseAssignment
        fields = [
            "id",
            "title",
            "case_version_id",
            "class_group_id",
            "case_title",
            "case_version_number",
            "course_name",
            "class_name",
            "duration_minutes",
            "opens_at",
            "deadline_at",
            "status",
            "feedback_released_at",
            "student_count",
            "not_started_count",
            "active_count",
            "submitted_count",
            "expired_count",
            "created_at",
        ]


class AssignmentOptionSerializer(serializers.Serializer):
    case_versions = serializers.ListField(child=serializers.DictField())
    class_groups = serializers.ListField(child=serializers.DictField())


class StudentAssignmentSerializer(serializers.ModelSerializer):
    case_title = serializers.CharField(source="case_version.title_student", read_only=True)
    difficulty = serializers.CharField(source="case_version.difficulty", read_only=True)
    attempt_status = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()

    class Meta:
        model = CaseAssignment
        fields = [
            "id",
            "title",
            "case_title",
            "difficulty",
            "duration_minutes",
            "opens_at",
            "deadline_at",
            "status",
            "feedback_released_at",
            "attempt_status",
            "session_id",
        ]

    def _session(self, assignment):
        sessions = getattr(assignment, "student_sessions", [])
        return sessions[0] if sessions else None

    def get_attempt_status(self, assignment):
        session = self._session(assignment)
        return session.status if session else "not_started"

    def get_session_id(self, assignment):
        session = self._session(assignment)
        return session.id if session else None


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = [
            "id",
            "sequence",
            "role",
            "content",
            "client_message_id",
            "reply_to_id",
            "response_status",
            "error_code",
            "created_at",
        ]


class StageSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StageSubmission
        fields = ["id", "submission_type", "payload", "submitted_at"]


class SessionSerializer(serializers.ModelSerializer):
    assignment_title = serializers.CharField(source="assignment.title", read_only=True)
    case_title = serializers.CharField(source="case_version.title_student", read_only=True)
    patient_name = serializers.CharField(
        source="case_version.patient_profile.display_name",
        read_only=True,
    )
    opening_statement = serializers.CharField(
        source="case_version.patient_profile.opening_statement",
        read_only=True,
    )
    remaining_seconds = serializers.SerializerMethodField()
    messages = MessageSerializer(many=True, read_only=True)
    submissions = StageSubmissionSerializer(many=True, read_only=True)

    class Meta:
        model = SimulationSession
        fields = [
            "id",
            "assignment_id",
            "assignment_title",
            "case_title",
            "patient_name",
            "opening_statement",
            "status",
            "stage",
            "started_at",
            "deadline_at",
            "completed_at",
            "remaining_seconds",
            "messages",
            "submissions",
        ]

    def get_remaining_seconds(self, session):
        return remaining_seconds(session)


class AskPatientSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=2000, trim_whitespace=True)
    client_message_id = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")


class ExchangeSerializer(serializers.Serializer):
    student_message = MessageSerializer()
    patient_message = MessageSerializer(allow_null=True)
    reused = serializers.BooleanField()


class SubmissionCreateSerializer(serializers.Serializer):
    submission_type = serializers.ChoiceField(choices=SubmissionType.choices)
    payload = serializers.DictField()

    def validate_payload(self, value):
        if not value:
            raise serializers.ValidationError("提交内容不能为空。")
        return value


class FeedbackSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    standard_diagnoses = serializers.ListField(child=serializers.DictField())
    standard_tests = serializers.ListField(child=serializers.DictField())
    score = serializers.FloatField(allow_null=True)
    ai_feedback = serializers.CharField()
