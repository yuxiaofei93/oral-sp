from django.urls import path

from .views import (
    TeacherClassDetailView,
    TeacherClassListCreateView,
    TeacherClassRosterMemberView,
)

urlpatterns = [
    path("classes/", TeacherClassListCreateView.as_view(), name="teacher-class-list"),
    path(
        "classes/<uuid:class_id>/",
        TeacherClassDetailView.as_view(),
        name="teacher-class-detail",
    ),
    path(
        "classes/<uuid:class_id>/students/<uuid:student_id>/",
        TeacherClassRosterMemberView.as_view(),
        name="teacher-class-roster-member",
    ),
]
