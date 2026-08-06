from modules.accounts.models import RoleCode

from .models import ClassGroup, ClassMembership


class TeachingError(Exception):
    code = "teaching_error"


class TeachingPermissionError(TeachingError):
    code = "teaching_permission_denied"


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
