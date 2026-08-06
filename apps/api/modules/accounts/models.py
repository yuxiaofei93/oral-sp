import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager
from .phone import normalize_phone, validate_phone


class RoleCode(models.TextChoices):
    STUDENT = "student", "学生"
    TEACHER = "teacher", "教师"
    ADMINISTRATOR = "administrator", "系统管理员"


class Role(models.Model):
    code = models.CharField(max_length=32, choices=RoleCode.choices, unique=True)
    name = models.CharField(max_length=64)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return self.name


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    phone = models.CharField(max_length=16, unique=True, validators=[validate_phone])
    display_name = models.CharField(max_length=80)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    roles = models.ManyToManyField(
        Role,
        through="UserRole",
        through_fields=("user", "role"),
        related_name="users",
    )

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["display_name"]

    objects = UserManager()

    def save(self, *args, **kwargs):
        self.phone = normalize_phone(self.phone)
        return super().save(*args, **kwargs)

    def has_role(self, role_code: str) -> bool:
        return self.is_superuser or self.roles.filter(code=role_code).exists()

    def __str__(self) -> str:
        return self.display_name or self.phone


class UserRole(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="assignments")
    assigned_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="roles_assigned",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="unique_user_role"),
        ]
