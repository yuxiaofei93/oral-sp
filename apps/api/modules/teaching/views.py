from django.db.models import Count, Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from modules.accounts.models import RoleCode, User
from modules.accounts.permissions import IsAdministrator, IsTeacherOrAdministrator

from .models import ClassGroup, ClassMembership
from .serializers import (
    ClassGroupCreateSerializer,
    ClassGroupSerializer,
    ClassGroupStatusSerializer,
    ManagedStudentClassUpdateSerializer,
    ManagedStudentFilterSerializer,
    ManagedStudentSerializer,
    StudentTransferSerializer,
)
from .services import (
    TeachingError,
    archive_class_group,
    create_class_group,
    remove_student,
    set_class_group_active,
    set_student_class,
    transfer_student,
)


def teacher_class_queryset(user, *, active_only=False):
    memberships = ClassMembership.objects.select_related("student").order_by(
        "student__display_name",
        "student__email",
    )
    queryset = (
        ClassGroup.objects.all()
        .select_related("created_by")
        .annotate(student_count=Count("memberships", distinct=True))
        .prefetch_related(Prefetch("memberships", queryset=memberships))
        .order_by("-is_active", "name", "created_at")
    )
    if active_only:
        queryset = queryset.filter(is_active=True)
    if user.is_superuser or user.has_role(RoleCode.ADMINISTRATOR):
        return queryset
    return queryset.filter(created_by=user)


def teaching_error_response(error: TeachingError) -> Response:
    return Response(
        {"detail": str(error), "code": error.code},
        status=getattr(error, "status_code", status.HTTP_400_BAD_REQUEST),
    )


def managed_student_queryset():
    memberships = ClassMembership.objects.select_related("class_group").order_by(
        "class_group__name",
    )
    return (
        User.objects.filter(roles__code=RoleCode.STUDENT)
        .prefetch_related(Prefetch("class_memberships", queryset=memberships))
        .distinct()
        .order_by("display_name", "email")
    )


class TeacherClassListCreateView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def get(self, request):
        return Response(ClassGroupSerializer(teacher_class_queryset(request.user), many=True).data)

    def post(self, request):
        serializer = ClassGroupCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        class_group = create_class_group(user=request.user, **serializer.validated_data)
        class_group = teacher_class_queryset(request.user).get(pk=class_group.pk)
        return Response(ClassGroupSerializer(class_group).data, status=status.HTTP_201_CREATED)


class TeacherClassDetailView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def patch(self, request, class_id):
        class_group = get_object_or_404(teacher_class_queryset(request.user), pk=class_id)
        serializer = ClassGroupStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            set_class_group_active(
                class_group=class_group,
                is_active=serializer.validated_data["is_active"],
                user=request.user,
            )
        except TeachingError as error:
            return teaching_error_response(error)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request, class_id):
        class_group = get_object_or_404(teacher_class_queryset(request.user), pk=class_id)
        try:
            archive_class_group(class_group=class_group, user=request.user)
        except TeachingError as error:
            return teaching_error_response(error)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TeacherClassRosterMemberView(APIView):
    permission_classes = [IsTeacherOrAdministrator]

    def patch(self, request, class_id, student_id):
        class_group = get_object_or_404(teacher_class_queryset(request.user), pk=class_id)
        membership = get_object_or_404(
            ClassMembership.objects.select_related("class_group"),
            class_group=class_group,
            student_id=student_id,
        )
        serializer = StudentTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_class = get_object_or_404(
            teacher_class_queryset(request.user, active_only=True),
            pk=serializer.validated_data["target_class"].pk,
        )
        try:
            transfer_student(
                membership=membership,
                target_class=target_class,
                user=request.user,
            )
        except TeachingError as error:
            return teaching_error_response(error)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def delete(self, request, class_id, student_id):
        class_group = get_object_or_404(teacher_class_queryset(request.user), pk=class_id)
        membership = get_object_or_404(
            ClassMembership.objects.select_related("class_group"),
            class_group=class_group,
            student_id=student_id,
        )
        try:
            remove_student(membership=membership, user=request.user)
        except TeachingError as error:
            return teaching_error_response(error)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ManagedStudentListView(APIView):
    permission_classes = [IsAdministrator]

    def get(self, request):
        filters = ManagedStudentFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        queryset = managed_student_queryset()
        name = filters.validated_data.get("name", "").strip()
        email = filters.validated_data.get("email", "").strip()
        class_group_id = filters.validated_data.get("class_group_id")
        if name:
            queryset = queryset.filter(display_name__icontains=name)
        if email:
            queryset = queryset.filter(email__icontains=email)
        if class_group_id:
            queryset = queryset.filter(class_memberships__class_group_id=class_group_id)
        return Response(ManagedStudentSerializer(queryset.distinct(), many=True).data)


class ManagedStudentDetailView(APIView):
    permission_classes = [IsAdministrator]

    def get(self, request, student_id):
        student = get_object_or_404(managed_student_queryset(), pk=student_id)
        return Response(ManagedStudentSerializer(student).data)

    def patch(self, request, student_id):
        student = get_object_or_404(managed_student_queryset(), pk=student_id)
        serializer = ManagedStudentClassUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            set_student_class(
                student=student,
                target_class=serializer.validated_data["class_group"],
                user=request.user,
            )
        except TeachingError as error:
            return teaching_error_response(error)
        student = managed_student_queryset().get(pk=student.pk)
        return Response(ManagedStudentSerializer(student).data)
