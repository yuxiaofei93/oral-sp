from django.urls import path

from .views import (
    TeacherClassCreateView,
    TeacherClassRosterMemberView,
    TeacherClassRosterView,
    TeacherCourseListCreateView,
)

urlpatterns = [
    path("courses/", TeacherCourseListCreateView.as_view(), name="teacher-course-list"),
    path("classes/", TeacherClassCreateView.as_view(), name="teacher-class-create"),
    path(
        "classes/<uuid:class_id>/students/",
        TeacherClassRosterView.as_view(),
        name="teacher-class-roster",
    ),
    path(
        "classes/<uuid:class_id>/students/<uuid:student_id>/",
        TeacherClassRosterMemberView.as_view(),
        name="teacher-class-roster-member",
    ),
]
