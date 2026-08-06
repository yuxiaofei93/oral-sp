from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.accounts.models import RoleCode
from modules.accounts.permissions import IsTeacherOrAdministrator

from .models import ClassGroup, ClassMembership, Course
from .serializers import (
    ClassGroupCreateSerializer,
    ClassGroupSerializer,
    CourseCreateSerializer,
    CourseSerializer,
)
from .services import (
    TeachingError,
    archive_course,
    create_class_group,
    create_course,
    remove_student,
)


def teacher_course_queryset(user):
    queryset = Course.objects.filter(is_active=True).annotate(
        class_count=Count("classes", filter=Q(classes__is_active=True), distinct=True)
    )
    if user.is_superuser or user.has_role(RoleCode.ADMINISTRATOR):
        return queryset
    return queryset.filter(teacher_links__teacher=user).distinct()


def teacher_class_queryset(user):
    memberships = ClassMembership.objects.select_related("student").order_by(
        "student__display_name",
        "student__email",
    )
    queryset = (
        ClassGroup.objects.filter(is_active=True, course__is_active=True)
        .select_related("course")
        .annotate(student_count=Count("memberships", distinct=True))
        .prefetch_related(Prefetch("memberships", queryset=memberships))
        .order_by("course__code", "code")
    )
    if user.is_superuser or user.has_role(RoleCode.ADMINISTRATOR):
        return queryset
    return queryset.filter(course__teacher_links__teacher=user).distinct()


def teaching_error_response(error: TeachingError) -> Response:
    data = {"detail": str(error), "code": error.code}
    return Response(data, status=status.HTTP_403_FORBIDDEN)


class TeacherCourseListCreateView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def get(self, request):
        return Response(CourseSerializer(teacher_course_queryset(request.user), many=True).data)

    def post(self, request):
        serializer = CourseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = create_course(user=request.user, **serializer.validated_data)
        course = teacher_course_queryset(request.user).get(pk=course.pk)
        return Response(CourseSerializer(course).data, status=status.HTTP_201_CREATED)


class TeacherCourseDetailView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def delete(self, request, course_id):
        course = get_object_or_404(teacher_course_queryset(request.user), pk=course_id)
        try:
            archive_course(course=course, user=request.user)
        except TeachingError as error:
            return teaching_error_response(error)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeacherClassCreateView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def get(self, request):
        return Response(ClassGroupSerializer(teacher_class_queryset(request.user), many=True).data)

    def post(self, request):
        serializer = ClassGroupCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            class_group = create_class_group(user=request.user, **serializer.validated_data)
        except TeachingError as error:
            return teaching_error_response(error)
        class_group = teacher_class_queryset(request.user).get(pk=class_group.pk)
        return Response(ClassGroupSerializer(class_group).data, status=status.HTTP_201_CREATED)


class TeacherClassRosterMemberView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def delete(self, request, class_id, student_id):
        class_group = get_object_or_404(teacher_class_queryset(request.user), pk=class_id)
        membership = get_object_or_404(
            ClassMembership.objects.select_related("class_group__course"),
            class_group=class_group,
            student_id=student_id,
        )
        try:
            remove_student(membership=membership, user=request.user)
        except TeachingError as error:
            return teaching_error_response(error)
        return Response(status=status.HTTP_204_NO_CONTENT)
