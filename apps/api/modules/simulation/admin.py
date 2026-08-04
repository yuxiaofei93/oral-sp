from django.contrib import admin

from .models import CaseAssignment, ModelCall, SimulationSession


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
