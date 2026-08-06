from django.urls import path

from .views import (
    TeacherClassCreateView,
    TeacherClassRosterMemberView,
    TeacherCourseDetailView,
    TeacherCourseListCreateView,
)

urlpatterns = [
    path("courses/", TeacherCourseListCreateView.as_view(), name="teacher-course-list"),
    path(
        "courses/<uuid:course_id>/",
        TeacherCourseDetailView.as_view(),
        name="teacher-course-detail",
    ),
    path("classes/", TeacherClassCreateView.as_view(), name="teacher-class-create"),
    path(
        "classes/<uuid:class_id>/students/<uuid:student_id>/",
        TeacherClassRosterMemberView.as_view(),
        name="teacher-class-roster-member",
    ),
]
