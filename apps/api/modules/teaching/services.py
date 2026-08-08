from django.db import transaction

from modules.accounts.models import RoleCode

from .models import ClassGroup, ClassMembership


class TeachingError(Exception):
    code = "teaching_error"


class TeachingPermissionError(TeachingError):
    code = "teaching_permission_denied"
    status_code = 403


class InvalidStudentTransferError(TeachingError):
    code = "invalid_student_transfer"
    status_code = 400


def can_manage_class(*, class_group: ClassGroup, user) -> bool:
    return (
        user.is_superuser
        or user.has_role(RoleCode.ADMINISTRATOR)
        or class_group.created_by_id == user.id
    )


def create_class_group(*, code: str, name: str, user) -> ClassGroup:
    return ClassGroup.objects.create(code=code, name=name, created_by=user)


def archive_class_group(*, class_group: ClassGroup, user) -> None:
    if not can_manage_class(class_group=class_group, user=user):
        raise TeachingPermissionError("你没有该班级的管理权限。")
    ClassGroup.objects.filter(pk=class_group.pk).update(is_active=False)


def remove_student(*, membership: ClassMembership, user) -> None:
    if not can_manage_class(class_group=membership.class_group, user=user):
        raise TeachingPermissionError("你没有该班级的学生名单管理权限。")
    membership.delete()


@transaction.atomic
def transfer_student(
    *,
    membership: ClassMembership,
    target_class: ClassGroup,
    user,
) -> None:
    membership = ClassMembership.objects.select_for_update().select_related(
        "class_group",
    ).get(pk=membership.pk)
    if not can_manage_class(class_group=membership.class_group, user=user):
        raise TeachingPermissionError("你没有该班级的学生名单管理权限。")
    if not can_manage_class(class_group=target_class, user=user):
        raise TeachingPermissionError("你没有目标班级的管理权限。")
    if membership.class_group_id == target_class.id:
        raise InvalidStudentTransferError("目标班级不能与当前班级相同。")
    if not target_class.is_active:
        raise InvalidStudentTransferError("只能将学生转入有效班级。")

    existing_target_membership = ClassMembership.objects.filter(
        class_group=target_class,
        student_id=membership.student_id,
    ).first()
    if existing_target_membership is not None:
        membership.delete()
        return

    membership.class_group = target_class
    membership.save(update_fields=["class_group"])
