from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction

from modules.accounts.models import RoleCode
from modules.accounts.phone import normalize_phone

from .models import ClassGroup, ClassMembership, Course, CourseTeacher

User = get_user_model()


class TeachingError(Exception):
    code = "teaching_error"


class TeachingPermissionError(TeachingError):
    code = "teaching_permission_denied"


class StudentLookupError(TeachingError):
    code = "student_lookup_failed"

    def __init__(self, message: str, *, missing: list[str], not_students: list[str]):
        super().__init__(message)
        self.missing = missing
        self.not_students = not_students


@dataclass(frozen=True)
class RosterAddResult:
    created_count: int
    existing_count: int


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


def add_students_by_phone(
    *,
    class_group: ClassGroup,
    phones: list[str],
    user,
) -> RosterAddResult:
    if not can_manage_course(course=class_group.course, user=user):
        raise TeachingPermissionError("你没有该班级的学生名单管理权限。")

    normalized = list(dict.fromkeys(normalize_phone(phone) for phone in phones))
    users = {account.phone: account for account in User.objects.filter(phone__in=normalized)}
    student_phones = set(
        User.objects.filter(
            phone__in=normalized,
            roles__code=RoleCode.STUDENT,
        ).values_list("phone", flat=True)
    )
    missing = [phone for phone in normalized if phone not in users]
    not_students = [
        phone
        for phone in users
        if phone not in student_phones
    ]
    if missing or not_students:
        raise StudentLookupError(
            "名单中存在未注册手机号或非学生账号，本次没有导入任何人。",
            missing=missing,
            not_students=not_students,
        )

    existing_ids = set(
        ClassMembership.objects.filter(
            class_group=class_group,
            student__phone__in=normalized,
        ).values_list("student_id", flat=True)
    )
    additions = [
        ClassMembership(class_group=class_group, student=account)
        for account in users.values()
        if account.id not in existing_ids
    ]
    ClassMembership.objects.bulk_create(additions, ignore_conflicts=True)
    return RosterAddResult(
        created_count=len(additions),
        existing_count=len(normalized) - len(additions),
    )


def remove_student(*, membership: ClassMembership, user) -> None:
    if not can_manage_course(course=membership.class_group.course, user=user):
        raise TeachingPermissionError("你没有该班级的学生名单管理权限。")
    membership.delete()
