from django.contrib import admin

from .models import (
    CaseAssignment,
    ModelCall,
    ScoreResult,
    SessionAssessment,
    SimulationSession,
    TeacherReview,
)


@admin.register(CaseAssignment)
class CaseAssignmentAdmin(admin.ModelAdmin):
    list_display = ("title", "class_group", "status", "opens_at", "deadline_at")
    list_filter = ("status",)
    search_fields = ("title",)


@admin.register(SimulationSession)
class SimulationSessionAdmin(admin.ModelAdmin):
    list_display = ("assignment", "student", "status", "stage", "started_at", "completed_at")
    list_filter = ("status", "stage")
    search_fields = ("assignment__title", "student__phone", "student__display_name")
    readonly_fields = (
        "assignment",
        "student",
        "case_version",
        "status",
        "stage",
        "started_at",
        "deadline_at",
        "completed_at",
        "retention_expires_at",
        "last_message_sequence",
        "created_at",
        "updated_at",
    )


@admin.register(ModelCall)
class ModelCallAdmin(admin.ModelAdmin):
    list_display = ("session", "provider", "model", "status", "latency_ms", "created_at")
    list_filter = ("status", "provider")
    readonly_fields = [field.name for field in ModelCall._meta.fields]


@admin.register(SessionAssessment)
class SessionAssessmentAdmin(admin.ModelAdmin):
    list_display = ("session", "automatic_score", "scored_maximum", "provisional", "generated_at")
    readonly_fields = [field.name for field in SessionAssessment._meta.fields]


@admin.register(ScoreResult)
class ScoreResultAdmin(admin.ModelAdmin):
    list_display = ("session", "code", "decision", "automatic_score", "max_score")
    list_filter = ("decision", "dimension", "evaluation_method")
    readonly_fields = [field.name for field in ScoreResult._meta.fields]


@admin.register(TeacherReview)
class TeacherReviewAdmin(admin.ModelAdmin):
    list_display = ("session", "revision", "reviewer", "final_score", "created_at")
    readonly_fields = [field.name for field in TeacherReview._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
