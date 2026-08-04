from rest_framework import serializers

from modules.cases.models import CaseVersion, VersionStatus
from modules.teaching.models import ClassGroup

from .models import (
    CaseAssignment,
    Message,
    ScoreResult,
    SessionAssessment,
    SimulationSession,
    StageSubmission,
    SubmissionType,
    TeacherReview,
)
from .reviews import effective_decision, effective_score, review_overrides, score_summary
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
    score = serializers.DictField()
    scoring_items = serializers.ListField(child=serializers.DictField())
    omissions = serializers.ListField(child=serializers.DictField())
    errors = serializers.ListField(child=serializers.DictField())
    feedback_summary = serializers.CharField()
    ai_feedback = serializers.CharField(allow_null=True, allow_blank=True)
    teacher_comment = serializers.CharField(allow_blank=True)


class ScoreResultSerializer(serializers.ModelSerializer):
    automatic_score = serializers.FloatField(allow_null=True)
    max_score = serializers.FloatField()
    confidence = serializers.FloatField(allow_null=True)
    teacher_score = serializers.SerializerMethodField()
    effective_score = serializers.SerializerMethodField()
    effective_decision = serializers.SerializerMethodField()
    adjustment_reason = serializers.SerializerMethodField()

    def _override(self, result):
        return review_overrides(self.context.get("review")).get(result.code)

    def get_teacher_score(self, result):
        override = self._override(result)
        if not isinstance(override, dict) or override.get("score") in (None, ""):
            return None
        return float(override["score"])

    def get_effective_score(self, result):
        score = effective_score(result, self.context.get("review"))
        return float(score) if score is not None else None

    def get_effective_decision(self, result):
        return effective_decision(result, self.context.get("review"))

    def get_adjustment_reason(self, result):
        override = self._override(result)
        return str(override.get("reason", "")) if isinstance(override, dict) else ""

    class Meta:
        model = ScoreResult
        fields = [
            "id",
            "code",
            "label",
            "dimension",
            "evaluation_method",
            "automatic_score",
            "teacher_score",
            "effective_score",
            "effective_decision",
            "adjustment_reason",
            "max_score",
            "decision",
            "confidence",
            "evidence_message_ids",
            "evidence_submission_ids",
            "evidence_excerpt",
            "standard_answer",
            "reason",
            "is_student_visible",
            "rule_version",
            "model_version",
        ]


class AssessmentSerializer(serializers.ModelSerializer):
    automatic_score = serializers.SerializerMethodField()
    final_score = serializers.SerializerMethodField()
    scored_maximum = serializers.SerializerMethodField()
    maximum_score = serializers.SerializerMethodField()
    provisional = serializers.SerializerMethodField()
    scoring_items = serializers.SerializerMethodField()

    def _summary(self, assessment):
        cache = getattr(self, "_summary_cache", {})
        if assessment.pk not in cache:
            cache[assessment.pk] = score_summary(
                assessment.session,
                student_visible_only=self.context.get("student_visible_only", False),
                review=self.context.get("review"),
            )
            self._summary_cache = cache
        return cache[assessment.pk]

    def get_automatic_score(self, assessment):
        return self._summary(assessment)["automatic_score"]

    def get_final_score(self, assessment):
        return self._summary(assessment)["final_score"]

    def get_scored_maximum(self, assessment):
        return self._summary(assessment)["scored_maximum"]

    def get_maximum_score(self, assessment):
        return self._summary(assessment)["maximum_score"]

    def get_provisional(self, assessment):
        return self._summary(assessment)["provisional"]

    class Meta:
        model = SessionAssessment
        fields = [
            "automatic_score",
            "final_score",
            "scored_maximum",
            "maximum_score",
            "provisional",
            "omissions",
            "errors",
            "feedback_summary",
            "ai_feedback",
            "scoring_version",
            "generated_at",
            "scoring_items",
        ]

    def get_scoring_items(self, assessment):
        results = assessment.session.score_results.all()
        if self.context.get("student_visible_only"):
            results = results.filter(is_student_visible=True)
        return ScoreResultSerializer(
            results,
            many=True,
            context={"review": self.context.get("review")},
        ).data


class TeacherReviewSerializer(serializers.ModelSerializer):
    reviewer_id = serializers.UUIDField(read_only=True)
    reviewer_name = serializers.CharField(source="reviewer.display_name", read_only=True)
    final_score = serializers.FloatField()
    scored_maximum = serializers.FloatField()
    maximum_score = serializers.FloatField()

    class Meta:
        model = TeacherReview
        fields = [
            "id",
            "revision",
            "reviewer_id",
            "reviewer_name",
            "score_overrides",
            "comment",
            "final_score",
            "scored_maximum",
            "maximum_score",
            "provisional",
            "created_at",
        ]


class TeacherReviewScoreInputSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=160)
    score = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        allow_null=True,
        required=False,
    )
    reason = serializers.CharField(max_length=2000, trim_whitespace=True)


class TeacherReviewCreateSerializer(serializers.Serializer):
    comment = serializers.CharField(
        max_length=4000,
        allow_blank=True,
        required=False,
        default="",
    )
    scores = TeacherReviewScoreInputSerializer(many=True, required=False, default=list)


class TeacherResponseRowSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    display_name = serializers.CharField()
    phone = serializers.CharField()
    attempt_status = serializers.CharField()
    session_id = serializers.UUIDField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    elapsed_seconds = serializers.IntegerField(allow_null=True)
    score = serializers.DictField(allow_null=True)


class TeacherSessionRecordSerializer(SessionSerializer):
    student_id = serializers.UUIDField(read_only=True)
    student_name = serializers.CharField(source="student.display_name", read_only=True)
    student_phone = serializers.CharField(source="student.phone", read_only=True)
    assessment = serializers.SerializerMethodField()
    latest_review = serializers.SerializerMethodField()
    standard_diagnoses = serializers.SerializerMethodField()
    standard_tests = serializers.SerializerMethodField()

    class Meta(SessionSerializer.Meta):
        fields = [
            *SessionSerializer.Meta.fields,
            "student_id",
            "student_name",
            "student_phone",
            "assessment",
            "latest_review",
            "standard_diagnoses",
            "standard_tests",
        ]

    def get_assessment(self, session):
        try:
            assessment = session.assessment
        except SessionAssessment.DoesNotExist:
            return None
        return AssessmentSerializer(
            assessment,
            context={"review": self.context.get("review")},
        ).data

    def get_latest_review(self, session):
        review = self.context.get("review")
        return TeacherReviewSerializer(review).data if review else None

    def get_standard_diagnoses(self, session):
        return [
            {
                "type": rule.diagnosis_type,
                "name": rule.name,
                "supporting_evidence": rule.supporting_evidence,
            }
            for rule in session.case_version.diagnosis_rules.all()
        ]

    def get_standard_tests(self, session):
        return [
            {
                "code": test.code,
                "name": test.name,
                "result": test.result_text,
                "interpretation": test.teacher_interpretation,
            }
            for test in session.case_version.tests.all()
        ]
