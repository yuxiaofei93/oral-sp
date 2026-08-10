import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from modules.cases.models import CaseVersion, VersionStatus
from modules.teaching.models import ClassGroup


class AssignmentStatus(models.TextChoices):
    OPEN = "open", "进行中"
    CLOSED = "closed", "已结束"


class CaseAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=160)
    case_version = models.ForeignKey(
        CaseVersion,
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    class_group = models.ForeignKey(
        ClassGroup,
        on_delete=models.PROTECT,
        related_name="case_assignments",
    )
    duration_minutes = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(240)],
    )
    opens_at = models.DateTimeField()
    deadline_at = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.OPEN,
    )
    feedback_released_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="case_assignments_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-opens_at", "title"]
        constraints = [
            models.CheckConstraint(
                condition=Q(deadline_at__gt=models.F("opens_at")),
                name="assignment_deadline_after_open",
            )
        ]

    def clean(self):
        if self.case_version_id and self.case_version.status != VersionStatus.PUBLISHED:
            raise ValidationError("只能把已发布病例版本分配给学生。")

    def __str__(self) -> str:
        return self.title


class AssignmentStudent(models.Model):
    assignment = models.ForeignKey(
        CaseAssignment,
        on_delete=models.CASCADE,
        related_name="student_links",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assignment_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "student"],
                name="unique_assignment_student",
            )
        ]


class SessionStatus(models.TextChoices):
    ACTIVE = "active", "进行中"
    COMPLETED = "completed", "已交卷"
    EXPIRED = "expired", "已超时"


class SessionStage(models.TextChoices):
    INTERVIEW = "interview", "问诊"
    COMPLETED = "completed", "已完成"


class SimulationSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(
        CaseAssignment,
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="simulation_sessions",
    )
    case_version = models.ForeignKey(
        CaseVersion,
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    status = models.CharField(
        max_length=16,
        choices=SessionStatus.choices,
        default=SessionStatus.ACTIVE,
    )
    stage = models.CharField(
        max_length=32,
        choices=SessionStage.choices,
        default=SessionStage.INTERVIEW,
    )
    started_at = models.DateTimeField()
    deadline_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    retention_expires_at = models.DateTimeField()
    last_message_sequence = models.PositiveIntegerField(default=0)
    case_draft = models.JSONField(default=dict, blank=True)
    case_draft_revision = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "student"],
                name="one_attempt_per_assignment",
            ),
            models.CheckConstraint(
                condition=Q(deadline_at__gt=models.F("started_at")),
                name="session_deadline_after_start",
            ),
        ]


class SessionStageEvent(models.Model):
    session = models.ForeignKey(
        SimulationSession,
        on_delete=models.CASCADE,
        related_name="stage_events",
    )
    from_stage = models.CharField(max_length=32, blank=True)
    to_stage = models.CharField(max_length=32, choices=SessionStage.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class MessageRole(models.TextChoices):
    STUDENT = "student", "学生"
    PATIENT = "patient", "患者"
    SYSTEM = "system", "系统"


class MessageKind(models.TextChoices):
    CHAT = "chat", "普通消息"
    PHYSICAL_EXAM_CONSENT = "physical_exam_consent", "体格检查同意"
    PHYSICAL_EXAM_RESULT = "physical_exam_result", "体格检查结果"


class ResponseStatus(models.TextChoices):
    PROCESSING = "processing", "生成中"
    COMPLETED = "completed", "已完成"
    FAILED = "failed", "失败"
    NOT_APPLICABLE = "not_applicable", "不适用"


class Message(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        SimulationSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sequence = models.PositiveIntegerField()
    role = models.CharField(max_length=16, choices=MessageRole.choices)
    kind = models.CharField(
        max_length=32,
        choices=MessageKind.choices,
        default=MessageKind.CHAT,
    )
    content = models.TextField()
    client_message_id = models.CharField(max_length=64, blank=True)
    reply_to = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="patient_reply",
    )
    response_status = models.CharField(
        max_length=24,
        choices=ResponseStatus.choices,
        default=ResponseStatus.NOT_APPLICABLE,
    )
    error_code = models.CharField(max_length=80, blank=True)
    input_mode = models.CharField(max_length=16, default="text")
    transcript = models.TextField(blank=True)
    audio_asset_id = models.CharField(max_length=120, blank=True)
    asr_confidence = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "sequence"],
                name="unique_message_sequence",
            ),
            models.UniqueConstraint(
                fields=["session", "client_message_id"],
                condition=~Q(client_message_id=""),
                name="unique_session_client_message",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = type(self).objects.get(pk=self.pk)
            immutable_fields = (
                "session_id",
                "sequence",
                "role",
                "kind",
                "content",
                "client_message_id",
                "reply_to_id",
                "input_mode",
                "transcript",
                "audio_asset_id",
                "asr_confidence",
                "created_at",
            )
            if any(getattr(self, field) != getattr(original, field) for field in immutable_fields):
                raise ValidationError("已发送消息不可修改。")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("已发送消息不可删除。")


class PhysicalExamRelease(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        SimulationSession,
        on_delete=models.CASCADE,
        related_name="physical_exam_release",
    )
    trigger_message = models.OneToOneField(
        Message,
        on_delete=models.PROTECT,
        related_name="triggered_physical_exam",
    )
    consent_message = models.OneToOneField(
        Message,
        on_delete=models.PROTECT,
        related_name="physical_exam_consent_release",
    )
    result_message = models.OneToOneField(
        Message,
        on_delete=models.PROTECT,
        related_name="physical_exam_result_release",
    )
    released_at = models.DateTimeField(auto_now_add=True)


class SubmissionType(models.TextChoices):
    CASE_RECORD = "case_record", "病例记录"


class StageSubmission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        SimulationSession,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    submission_type = models.CharField(max_length=32, choices=SubmissionType.choices)
    payload = models.JSONField()
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["submitted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "submission_type"],
                name="unique_session_submission_type",
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("病例记录不可修改。")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("病例记录不可删除。")


class ModelCallStatus(models.TextChoices):
    SUCCEEDED = "succeeded", "成功"
    FAILED = "failed", "失败"


class ModelCall(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        SimulationSession,
        on_delete=models.CASCADE,
        related_name="model_calls",
    )
    student_message = models.ForeignKey(
        Message,
        on_delete=models.PROTECT,
        related_name="model_calls",
    )
    patient_message = models.ForeignKey(
        Message,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="generated_by_calls",
    )
    provider = models.CharField(max_length=80)
    model = models.CharField(max_length=120)
    prompt_version = models.CharField(max_length=40, default="patient-v1")
    request_hash = models.CharField(max_length=64)
    matched_fact_codes = models.JSONField(default=list)
    routed_intent = models.CharField(max_length=40, blank=True)
    route_confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=16, choices=ModelCallStatus.choices)
    latency_ms = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class ScoreDecision(models.TextChoices):
    ACHIEVED = "achieved", "已完成"
    PARTIAL = "partial", "部分完成"
    MISSED = "missed", "未完成"
    PENDING = "pending", "待评价"


class SessionAssessment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        SimulationSession,
        on_delete=models.CASCADE,
        related_name="assessment",
    )
    automatic_score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    scored_maximum = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    maximum_score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    provisional = models.BooleanField(default=False)
    omissions = models.JSONField(default=list)
    errors = models.JSONField(default=list)
    feedback_summary = models.TextField(blank=True)
    ai_feedback = models.TextField(blank=True)
    scoring_version = models.CharField(max_length=40, default="rules-v1")
    generated_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("会话自动评分结果不可覆盖。")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("会话自动评分结果不可删除。")


class ScoreResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        SimulationSession,
        on_delete=models.CASCADE,
        related_name="score_results",
    )
    scoring_item = models.ForeignKey(
        "cases.ScoringItem",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="score_results",
    )
    code = models.CharField(max_length=160)
    label = models.CharField(max_length=240)
    dimension = models.CharField(max_length=40)
    evaluation_method = models.CharField(max_length=24)
    automatic_score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    max_score = models.DecimalField(max_digits=8, decimal_places=2)
    decision = models.CharField(max_length=16, choices=ScoreDecision.choices)
    confidence = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
    )
    evidence_message_ids = models.JSONField(default=list)
    evidence_submission_ids = models.JSONField(default=list)
    evidence_excerpt = models.TextField(blank=True)
    standard_answer = models.TextField(blank=True)
    reason = models.TextField()
    is_student_visible = models.BooleanField(default=True)
    rule_version = models.CharField(max_length=40, default="rules-v1")
    model_version = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["dimension", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "code"],
                name="unique_session_score_code",
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("自动评分证据不可覆盖。")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("自动评分证据不可删除。")


class TeacherReview(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        SimulationSession,
        on_delete=models.CASCADE,
        related_name="teacher_reviews",
    )
    revision = models.PositiveIntegerField()
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="simulation_reviews",
    )
    score_overrides = models.JSONField(default=dict)
    comment = models.TextField(blank=True)
    final_score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    scored_maximum = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    maximum_score = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    provisional = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "revision"],
                name="unique_session_review_revision",
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("教师复核记录不可覆盖，请创建新版本。")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("教师复核记录不可删除。")


class AIEvaluationStatus(models.TextChoices):
    RUNNING = "running", "评价中"
    SUCCEEDED = "succeeded", "成功"
    FAILED = "failed", "失败"


class AIEvaluationRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        SimulationSession,
        on_delete=models.CASCADE,
        related_name="ai_evaluation_runs",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_ai_evaluations",
    )
    status = models.CharField(
        max_length=16,
        choices=AIEvaluationStatus.choices,
        default=AIEvaluationStatus.RUNNING,
    )
    provider = models.CharField(max_length=80)
    model = models.CharField(max_length=120)
    resolved_model = models.CharField(max_length=120, blank=True)
    prompt_version = models.CharField(max_length=40, default="assessment-v1")
    request_hash = models.CharField(max_length=64)
    scoring_item_codes = models.JSONField(default=list)
    feedback_summary = models.TextField(blank=True)
    latency_ms = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session"],
                condition=Q(status=AIEvaluationStatus.RUNNING),
                name="one_running_ai_evaluation_per_session",
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            original = type(self).objects.get(pk=self.pk)
            immutable_fields = (
                "session_id",
                "requested_by_id",
                "provider",
                "model",
                "prompt_version",
                "request_hash",
                "scoring_item_codes",
                "created_at",
            )
            if any(getattr(self, field) != getattr(original, field) for field in immutable_fields):
                raise ValidationError("AI 评价运行的请求信息不可覆盖。")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("AI 评价运行记录不可删除。")


class AIScoreResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(
        AIEvaluationRun,
        on_delete=models.CASCADE,
        related_name="results",
    )
    score_result = models.ForeignKey(
        ScoreResult,
        on_delete=models.PROTECT,
        related_name="ai_evaluations",
    )
    score = models.DecimalField(max_digits=8, decimal_places=2)
    decision = models.CharField(max_length=16, choices=ScoreDecision.choices)
    confidence = models.DecimalField(max_digits=5, decimal_places=4)
    evidence_message_ids = models.JSONField(default=list)
    evidence_submission_ids = models.JSONField(default=list)
    evidence_excerpt = models.TextField(blank=True)
    reason = models.TextField()
    feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["score_result__dimension", "score_result__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "score_result"],
                name="unique_ai_result_per_run_item",
            )
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("AI 评价结果不可覆盖。")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("AI 评价结果不可删除。")
