from rest_framework import serializers

from modules.cases.models import CaseVersion, PhysicalExam, VersionStatus
from modules.teaching.models import ClassGroup

from .models import (
    AIEvaluationRun,
    AIScoreResult,
    CaseAssignment,
    Message,
    PhysicalExamRelease,
    ScoreResult,
    SessionAssessment,
    SimulationSession,
    SubmissionType,
    TeacherReview,
)
from .reviews import (
    ai_results_by_code,
    effective_decision,
    effective_score,
    review_overrides,
    score_summary,
)
from .services import patient_initiative_payload, remaining_seconds


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
    class_code = serializers.CharField(source="class_group.code", read_only=True)
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
            "class_code",
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
    difficulty = serializers.CharField(source="case_version.difficulty", read_only=True)
    attempt_status = serializers.SerializerMethodField()
    session_id = serializers.SerializerMethodField()

    class Meta:
        model = CaseAssignment
        fields = [
            "id",
            "title",
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
            "kind",
            "content",
            "client_message_id",
            "reply_to_id",
            "response_status",
            "error_code",
            "created_at",
        ]


CASE_RECORD_FIELDS = (
    "chief_complaint",
    "present_illness",
    "past_history",
    "family_history",
    "diagnosis",
    "treatment",
    "medical_advice",
)


def normalized_case_draft(value):
    source = value if isinstance(value, dict) else {}
    return {field: str(source.get(field, "")) for field in CASE_RECORD_FIELDS}


class CaseRecordInputSerializer(serializers.Serializer):
    chief_complaint = serializers.CharField(
        max_length=4000, allow_blank=True, trim_whitespace=False
    )
    present_illness = serializers.CharField(
        max_length=4000, allow_blank=True, trim_whitespace=False
    )
    past_history = serializers.CharField(max_length=4000, allow_blank=True, trim_whitespace=False)
    family_history = serializers.CharField(max_length=4000, allow_blank=True, trim_whitespace=False)
    diagnosis = serializers.CharField(max_length=4000, allow_blank=True, trim_whitespace=False)
    treatment = serializers.CharField(max_length=4000, allow_blank=True, trim_whitespace=False)
    medical_advice = serializers.CharField(max_length=4000, allow_blank=True, trim_whitespace=False)


class CaseDraftUpdateSerializer(serializers.Serializer):
    expected_revision = serializers.IntegerField(min_value=0)
    case_draft = CaseRecordInputSerializer()


class SessionCompleteSerializer(serializers.Serializer):
    expected_revision = serializers.IntegerField(min_value=0)
    case_record = CaseRecordInputSerializer()


class SessionSerializer(serializers.ModelSerializer):
    assignment_title = serializers.CharField(source="assignment.title", read_only=True)
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
    case_draft = serializers.SerializerMethodField()
    case_record = serializers.SerializerMethodField()
    physical_exam_result = serializers.SerializerMethodField()
    patient_initiative = serializers.SerializerMethodField()

    class Meta:
        model = SimulationSession
        fields = [
            "id",
            "assignment_id",
            "assignment_title",
            "patient_name",
            "opening_statement",
            "status",
            "stage",
            "started_at",
            "deadline_at",
            "completed_at",
            "remaining_seconds",
            "messages",
            "case_draft",
            "case_draft_revision",
            "case_record",
            "physical_exam_result",
            "patient_initiative",
        ]

    def get_remaining_seconds(self, session):
        return remaining_seconds(session)

    def get_case_draft(self, session):
        return normalized_case_draft(session.case_draft)

    def get_case_record(self, session):
        submission = next(
            (
                item
                for item in session.submissions.all()
                if item.submission_type == SubmissionType.CASE_RECORD
            ),
            None,
        )
        if submission is None:
            return None
        return {
            **normalized_case_draft(submission.payload),
            "specialty_exam": str(submission.payload.get("specialty_exam", "")),
            "submitted_at": submission.submitted_at,
        }

    def get_physical_exam_result(self, session):
        try:
            release = session.physical_exam_release
        except PhysicalExamRelease.DoesNotExist:
            release = None
        teacher_access = bool(self.context.get("teacher_access"))
        feedback_access = session.assignment.feedback_released_at is not None
        if not (release or teacher_access or feedback_access):
            return None
        try:
            physical_exam = session.case_version.physical_exam
        except PhysicalExam.DoesNotExist:
            return None
        if not physical_exam.findings_text.strip():
            return None
        audience = "teacher" if teacher_access else "student"

        def assets(kind):
            return [
                {
                    "id": link.id,
                    "kind": link.kind,
                    "filename": link.stored_asset.original_name,
                    "content_type": link.stored_asset.content_type,
                    "size_bytes": link.stored_asset.size_bytes,
                    "content_url": (
                        f"/api/{audience}/sessions/{session.id}/physical-exam/"
                        f"assets/{link.id}/content/"
                    ),
                }
                for link in physical_exam.assets.filter(kind=kind).select_related(
                    "stored_asset"
                )
            ]

        return {
            "release_id": str(release.id) if release else None,
            "released_at": release.released_at if release else None,
            "access_reason": (
                "triggered" if release else "teacher" if teacher_access else "feedback"
            ),
            "findings_text": physical_exam.findings_text,
            "images": assets("image"),
            "attachments": assets("attachment"),
        }

    def get_patient_initiative(self, session):
        return patient_initiative_payload(session)


class AskPatientSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=2000, trim_whitespace=True)
    client_message_id = serializers.RegexField(r"^[A-Za-z0-9_-]{8,64}$")


class ExchangeSerializer(serializers.Serializer):
    student_message = MessageSerializer()
    patient_message = MessageSerializer(allow_null=True)
    reused = serializers.BooleanField()
    interaction_type = serializers.ChoiceField(
        choices=[
            "patient_answer",
            "physical_exam_released",
            "physical_exam_reopened",
            "patient_initiative_response",
        ]
    )


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
    physical_exam_result = serializers.DictField(allow_null=True, required=False)


class ScoreResultSerializer(serializers.ModelSerializer):
    automatic_score = serializers.FloatField(allow_null=True)
    max_score = serializers.FloatField()
    confidence = serializers.FloatField(allow_null=True)
    teacher_score = serializers.SerializerMethodField()
    effective_score = serializers.SerializerMethodField()
    effective_decision = serializers.SerializerMethodField()
    adjustment_reason = serializers.SerializerMethodField()
    ai_score = serializers.SerializerMethodField()
    ai_confidence = serializers.SerializerMethodField()
    ai_reason = serializers.SerializerMethodField()
    ai_feedback = serializers.SerializerMethodField()
    ai_evidence_excerpt = serializers.SerializerMethodField()

    def _override(self, result):
        return review_overrides(self.context.get("review")).get(result.code)

    def get_teacher_score(self, result):
        override = self._override(result)
        if not isinstance(override, dict) or override.get("score") in (None, ""):
            return None
        return float(override["score"])

    def _ai_result(self, result):
        return self.context.get("ai_results", {}).get(result.code)

    def get_ai_score(self, result):
        ai_result = self._ai_result(result)
        return float(ai_result.score) if ai_result else None

    def get_ai_confidence(self, result):
        ai_result = self._ai_result(result)
        return float(ai_result.confidence) if ai_result else None

    def get_ai_reason(self, result):
        ai_result = self._ai_result(result)
        return ai_result.reason if ai_result else ""

    def get_ai_feedback(self, result):
        ai_result = self._ai_result(result)
        return ai_result.feedback if ai_result else ""

    def get_ai_evidence_excerpt(self, result):
        ai_result = self._ai_result(result)
        return ai_result.evidence_excerpt if ai_result else ""

    def get_effective_score(self, result):
        score = effective_score(
            result,
            self.context.get("review"),
            ai_run=self.context.get("ai_run"),
            ai_results=self.context.get("ai_results", {}),
        )
        return float(score) if score is not None else None

    def get_effective_decision(self, result):
        return effective_decision(
            result,
            self.context.get("review"),
            ai_run=self.context.get("ai_run"),
            ai_results=self.context.get("ai_results", {}),
        )

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
            "ai_score",
            "ai_confidence",
            "ai_reason",
            "ai_feedback",
            "ai_evidence_excerpt",
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
            context={
                "review": self.context.get("review"),
                "ai_run": self.context.get("ai_run"),
                "ai_results": self.context.get("ai_results", {}),
            },
        ).data


class AIScoreResultSerializer(serializers.ModelSerializer):
    code = serializers.CharField(source="score_result.code", read_only=True)
    label = serializers.CharField(source="score_result.label", read_only=True)
    score = serializers.FloatField()
    max_score = serializers.FloatField(source="score_result.max_score", read_only=True)
    confidence = serializers.FloatField()

    class Meta:
        model = AIScoreResult
        fields = [
            "code",
            "label",
            "score",
            "max_score",
            "decision",
            "confidence",
            "evidence_message_ids",
            "evidence_submission_ids",
            "evidence_excerpt",
            "reason",
            "feedback",
        ]


class AIEvaluationRunSerializer(serializers.ModelSerializer):
    results = AIScoreResultSerializer(many=True, read_only=True)
    requested_by_name = serializers.CharField(
        source="requested_by.display_name",
        read_only=True,
    )

    class Meta:
        model = AIEvaluationRun
        fields = [
            "id",
            "status",
            "requested_by_id",
            "requested_by_name",
            "provider",
            "model",
            "resolved_model",
            "prompt_version",
            "scoring_item_codes",
            "feedback_summary",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "error_code",
            "created_at",
            "completed_at",
            "results",
        ]


class AIEvaluationCreateSerializer(serializers.Serializer):
    force = serializers.BooleanField(required=False, default=False)


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
    email = serializers.EmailField()
    attempt_status = serializers.CharField()
    session_id = serializers.UUIDField(allow_null=True)
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    elapsed_seconds = serializers.IntegerField(allow_null=True)
    score = serializers.DictField(allow_null=True)


class AssignmentStatisticsSummarySerializer(serializers.Serializer):
    student_count = serializers.IntegerField()
    started_count = serializers.IntegerField()
    completed_count = serializers.IntegerField()
    expired_count = serializers.IntegerField()
    assessed_count = serializers.IntegerField()
    completion_rate = serializers.FloatField()
    average_score = serializers.FloatField(allow_null=True)
    average_score_percentage = serializers.FloatField(allow_null=True)
    average_duration_seconds = serializers.IntegerField(allow_null=True)


class AssignmentStatisticsIssueSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()
    rate = serializers.FloatField()


class AssignmentStatisticsSerializer(serializers.Serializer):
    summary = AssignmentStatisticsSummarySerializer()
    frequent_omissions = AssignmentStatisticsIssueSerializer(many=True)
    common_errors = AssignmentStatisticsIssueSerializer(many=True)


class TeacherSessionRecordSerializer(SessionSerializer):
    student_id = serializers.UUIDField(read_only=True)
    student_name = serializers.CharField(source="student.display_name", read_only=True)
    student_email = serializers.EmailField(source="student.email", read_only=True)
    assessment = serializers.SerializerMethodField()
    latest_review = serializers.SerializerMethodField()
    ai_evaluation = serializers.SerializerMethodField()
    standard_diagnoses = serializers.SerializerMethodField()
    standard_tests = serializers.SerializerMethodField()

    class Meta(SessionSerializer.Meta):
        fields = [
            *SessionSerializer.Meta.fields,
            "student_id",
            "student_name",
            "student_email",
            "assessment",
            "latest_review",
            "ai_evaluation",
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
            context={
                "review": self.context.get("review"),
                "ai_run": self.context.get("ai_run"),
                "ai_results": ai_results_by_code(self.context.get("ai_run")),
            },
        ).data

    def get_latest_review(self, session):
        review = self.context.get("review")
        return TeacherReviewSerializer(review).data if review else None

    def get_ai_evaluation(self, session):
        run = self.context.get("latest_ai_attempt")
        return AIEvaluationRunSerializer(run).data if run else None

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
