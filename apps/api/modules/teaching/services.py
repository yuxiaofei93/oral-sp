from django.db import transaction

from modules.accounts.models import RoleCode

from .models import ClassGroup, ClassMembership, Course, CourseTeacher


class TeachingError(Exception):
    code = "teaching_error"


class TeachingPermissionError(TeachingError):
    code = "teaching_permission_denied"


def can_manage_course(*, course: Course, user) -> bool:
    return (
        user.is_superuser
        or user.has_role(RoleCode.ADMINISTRATOR)
        or CourseTeacher.objects.filter(course=course, teacher=user).exists()
    )


def create_course(*, code: str, name: str, user) -> Course:
    with transaction.atomic():
        course = Course.objects.create(
            code=code,
            name=name,
            created_by=user,
        )
        CourseTeacher.objects.create(course=course, teacher=user)
        return course


def create_class_group(*, course: Course, code: str, name: str, user) -> ClassGroup:
    if not can_manage_course(course=course, user=user):
        raise TeachingPermissionError("你没有该课程的班级管理权限。")
    return ClassGroup.objects.create(course=course, code=code, name=name)


def archive_course(*, course: Course, user) -> None:
    if not can_manage_course(course=course, user=user):
        raise TeachingPermissionError("你没有该课程的管理权限。")
    with transaction.atomic():
        Course.objects.filter(pk=course.pk).update(is_active=False)
        ClassGroup.objects.filter(course=course).update(is_active=False)


def remove_student(*, membership: ClassMembership, user) -> None:
    if not can_manage_course(course=membership.class_group.course, user=user):
        raise TeachingPermissionError("你没有该班级的学生名单管理权限。")
    membership.delete()
