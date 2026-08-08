from django.urls import path

from .views import (
    TeacherCaseDraftView,
    TeacherCaseListCreateView,
    TeacherCasePublishView,
    TeacherPatientPromptTemplateView,
)

urlpatterns = [
    path("", TeacherCaseListCreateView.as_view(), name="teacher-case-list"),
    path(
        "patient-prompt-template/",
        TeacherPatientPromptTemplateView.as_view(),
        name="teacher-patient-prompt-template",
    ),
    path("<uuid:case_id>/draft/", TeacherCaseDraftView.as_view(), name="teacher-case-draft"),
    path("<uuid:case_id>/publish/", TeacherCasePublishView.as_view(), name="teacher-case-publish"),
]
