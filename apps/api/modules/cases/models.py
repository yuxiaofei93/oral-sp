import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q


def default_enabled_stages() -> list[str]:
    return [
        "interview",
        "history_summary",
        "initial_reasoning",
        "test_selection",
        "final_reasoning",
    ]


class Case(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        editable=False,
        max_length=40,
        unique=True,
        validators=[
            RegexValidator(
                r"^[A-Z0-9][A-Z0-9_-]*$",
                "病例编号只能使用大写字母、数字、_ 和 -。",
            )
        ],
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cases_created",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.code


class CaseCodeSequence(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    last_value = models.PositiveBigIntegerField(default=0)


class VersionStatus(models.TextChoices):
    DRAFT = "draft", "草稿"
    PUBLISHED = "published", "已发布"


class Difficulty(models.TextChoices):
    BASIC = "basic", "基础"
    INTERMEDIATE = "intermediate", "中级"
    ADVANCED = "advanced", "高级"


class CaseVersion(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.ForeignKey(Case, on_delete=models.PROTECT, related_name="versions")
    status = models.CharField(max_length=16, choices=VersionStatus.choices)
    version_number = models.PositiveIntegerField(null=True, blank=True)
    title_internal = models.CharField(max_length=160)
    difficulty = models.CharField(
        max_length=16,
        choices=Difficulty.choices,
        default=Difficulty.INTERMEDIATE,
    )
    is_exam_mode = models.BooleanField(default=True)
    time_limit_minutes = models.PositiveSmallIntegerField(
        default=20,
        validators=[MinValueValidator(1), MaxValueValidator(240)],
    )
    enabled_stages = models.JSONField(default=default_enabled_stages)
    based_on = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="derived_versions",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="case_versions_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["case_id", "status", "version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["case"],
                condition=Q(status=VersionStatus.DRAFT),
                name="unique_draft_per_case",
            ),
            models.UniqueConstraint(
                fields=["case", "version_number"],
                condition=Q(version_number__isnull=False),
                name="unique_case_version_number",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=VersionStatus.DRAFT, version_number__isnull=True)
                    | Q(status=VersionStatus.PUBLISHED, version_number__isnull=False)
                ),
                name="case_version_status_number_consistent",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            current_status = (
                type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            )
            if current_status == VersionStatus.PUBLISHED:
                raise ValidationError("已发布病例版本不可修改。")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status == VersionStatus.PUBLISHED:
            raise ValidationError("已发布病例版本不可删除。")
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        suffix = "草稿" if self.status == VersionStatus.DRAFT else f"v{self.version_number}"
        return f"{self.case.code} {suffix}"


class VersionOwnedModel(models.Model):
    version = models.ForeignKey(CaseVersion, on_delete=models.CASCADE)

    class Meta:
        abstract = True

    def ensure_draft(self) -> None:
        status = (
            CaseVersion.objects.filter(pk=self.version_id).values_list("status", flat=True).get()
        )
        if status != VersionStatus.DRAFT:
            raise ValidationError("已发布病例版本的内容不可修改。")

    def save(self, *args, **kwargs):
        self.ensure_draft()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self.ensure_draft()
        return super().delete(*args, **kwargs)


class PatientProfile(VersionOwnedModel):
    class Sex(models.TextChoices):
        FEMALE = "female", "女"
        MALE = "male", "男"
        OTHER = "other", "其他"
        UNSPECIFIED = "unspecified", "未说明"

    version = models.OneToOneField(
        CaseVersion,
        on_delete=models.CASCADE,
        related_name="patient_profile",
    )
    display_name = models.CharField(max_length=80, blank=True)
    age = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MaxValueValidator(120)],
    )
    sex = models.CharField(max_length=16, choices=Sex.choices, default=Sex.UNSPECIFIED)
    occupation = models.CharField(max_length=120, blank=True)
    education = models.CharField(max_length=80, blank=True)
    personality = models.CharField(max_length=160, blank=True)
    emotion = models.CharField(max_length=120, blank=True)
    cooperation = models.CharField(max_length=120, blank=True)
    medical_literacy = models.CharField(max_length=120, blank=True)
    opening_statement = models.TextField(blank=True)
    avatar_asset_id = models.CharField(max_length=120, blank=True)
    voice_id = models.CharField(max_length=120, blank=True)


class DisclosureMode(models.TextChoices):
    ACTIVE = "active", "主动披露"
    ON_QUESTION = "on_question", "被问到后披露"
    NEVER = "never", "患者角色禁止披露"


class FactCertainty(models.TextChoices):
    CERTAIN = "certain", "确定"
    VAGUE = "vague", "模糊"
    FORGOTTEN = "forgotten", "记不清"
    NOT_UNDERSTOOD = "not_understood", "不理解"


class CaseFact(VersionOwnedModel):
    version = models.ForeignKey(CaseVersion, on_delete=models.CASCADE, related_name="facts")
    code = models.CharField(max_length=80)
    standard_fact = models.TextField()
    patient_expression = models.TextField()
    disclosure_mode = models.CharField(
        max_length=24,
        choices=DisclosureMode.choices,
        default=DisclosureMode.ON_QUESTION,
    )
    certainty = models.CharField(
        max_length=24,
        choices=FactCertainty.choices,
        default=FactCertainty.CERTAIN,
    )
    teacher_notes = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["version", "code"], name="unique_fact_code_version"),
        ]


class ReleaseStage(models.TextChoices):
    CLINICAL_EXAM = "clinical_exam", "临床检查"
    TEST_RESULTS = "test_results", "辅助检查结果"


class TestDefinition(VersionOwnedModel):
    version = models.ForeignKey(CaseVersion, on_delete=models.CASCADE, related_name="tests")
    code = models.CharField(max_length=80)
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=80, blank=True)
    student_description = models.TextField(blank=True)
    result_text = models.TextField(blank=True)
    teacher_interpretation = models.TextField(blank=True)
    release_stage = models.CharField(
        max_length=24,
        choices=ReleaseStage.choices,
        default=ReleaseStage.TEST_RESULTS,
    )
    requires_request = models.BooleanField(default=True)
    prerequisite_code = models.CharField(max_length=80, blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["display_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["version", "code"], name="unique_test_code_version"),
        ]


class DiagnosisType(models.TextChoices):
    INITIAL = "initial", "初步诊断"
    DIFFERENTIAL = "differential", "鉴别诊断"
    FINAL = "final", "最终诊断"


class DiagnosisRule(VersionOwnedModel):
    version = models.ForeignKey(
        CaseVersion,
        on_delete=models.CASCADE,
        related_name="diagnosis_rules",
    )
    diagnosis_type = models.CharField(max_length=24, choices=DiagnosisType.choices)
    name = models.CharField(max_length=160)
    aliases = models.JSONField(default=list, blank=True)
    supporting_evidence = models.JSONField(default=list, blank=True)
    opposing_evidence = models.JSONField(default=list, blank=True)
    is_required = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["diagnosis_type", "display_order", "id"]


class ScoringDimension(models.TextChoices):
    HISTORY = "history", "病史采集"
    COMMUNICATION = "communication", "问诊逻辑与沟通"
    SUMMARY = "summary", "病史摘要"
    CLINICAL = "clinical", "临床表现描述"
    DIFFERENTIAL = "differential", "鉴别诊断"
    TEST_PLAN = "test_plan", "检查计划"
    FINAL_REASONING = "final_reasoning", "最终诊断与依据"


class EvaluationMethod(models.TextChoices):
    RULE = "rule", "规则评分"
    AI = "ai", "AI 辅助评价"
    TEACHER = "teacher", "教师评价"


class ScoringItem(VersionOwnedModel):
    version = models.ForeignKey(
        CaseVersion,
        on_delete=models.CASCADE,
        related_name="scoring_items",
    )
    code = models.CharField(max_length=80)
    dimension = models.CharField(max_length=32, choices=ScoringDimension.choices)
    label = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    max_score = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    evaluation_method = models.CharField(
        max_length=16,
        choices=EvaluationMethod.choices,
        default=EvaluationMethod.RULE,
    )
    matching_config = models.JSONField(default=dict, blank=True)
    student_feedback = models.TextField(blank=True)
    teacher_notes = models.TextField(blank=True)
    is_student_visible = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["dimension", "display_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["version", "code"],
                name="unique_scoring_code_version",
            ),
        ]
