from django.urls import path

from .views import TeacherCaseDraftView, TeacherCaseListCreateView, TeacherCasePublishView

urlpatterns = [
    path("", TeacherCaseListCreateView.as_view(), name="teacher-case-list"),
    path("<uuid:case_id>/draft/", TeacherCaseDraftView.as_view(), name="teacher-case-draft"),
    path("<uuid:case_id>/publish/", TeacherCasePublishView.as_view(), name="teacher-case-publish"),
]

