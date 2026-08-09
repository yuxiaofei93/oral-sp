from django.urls import path

from .views import (
    TeacherCaseDraftView,
    TeacherCaseListCreateView,
    TeacherCasePublishView,
    TeacherPatientPromptTemplateView,
    TeacherPatientQuestionTemplateView,
    TeacherPhysicalExamAssetContentView,
    TeacherPhysicalExamAssetDeleteView,
    TeacherPhysicalExamAssetUploadView,
)

urlpatterns = [
    path("", TeacherCaseListCreateView.as_view(), name="teacher-case-list"),
    path(
        "patient-prompt-template/",
        TeacherPatientPromptTemplateView.as_view(),
        name="teacher-patient-prompt-template",
    ),
    path(
        "patient-question-template/",
        TeacherPatientQuestionTemplateView.as_view(),
        name="teacher-patient-question-template",
    ),
    path("<uuid:case_id>/draft/", TeacherCaseDraftView.as_view(), name="teacher-case-draft"),
    path(
        "<uuid:case_id>/draft/physical-exam/assets/",
        TeacherPhysicalExamAssetUploadView.as_view(),
        name="teacher-physical-exam-asset-upload",
    ),
    path(
        "<uuid:case_id>/draft/physical-exam/assets/<int:asset_id>/",
        TeacherPhysicalExamAssetDeleteView.as_view(),
        name="teacher-physical-exam-asset-delete",
    ),
    path(
        "<uuid:case_id>/draft/physical-exam/assets/<int:asset_id>/content/",
        TeacherPhysicalExamAssetContentView.as_view(),
        name="teacher-physical-exam-asset-content",
    ),
    path("<uuid:case_id>/publish/", TeacherCasePublishView.as_view(), name="teacher-case-publish"),
]
