from rest_framework.permissions import BasePermission

from .models import RoleCode


class HasAnyRole(BasePermission):
    allowed_roles: tuple[str, ...] = ()

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.is_superuser or user.roles.filter(code__in=self.allowed_roles).exists()


class IsStudent(HasAnyRole):
    allowed_roles = (RoleCode.STUDENT,)


class IsTeacher(HasAnyRole):
    allowed_roles = (RoleCode.TEACHER,)


class IsAdministrator(HasAnyRole):
    allowed_roles = (RoleCode.ADMINISTRATOR,)


class IsTeacherOrAdministrator(HasAnyRole):
    allowed_roles = (RoleCode.TEACHER, RoleCode.ADMINISTRATOR)

