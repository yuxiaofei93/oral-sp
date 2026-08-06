import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models

from .identifiers import normalize_email_identifier
from .managers import UserManager


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
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=80)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    roles = models.ManyToManyField(
        Role,
        through="UserRole",
        through_fields=("user", "role"),
        related_name="users",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]

    objects = UserManager()

    def save(self, *args, **kwargs):
        self.email = normalize_email_identifier(self.email)
        return super().save(*args, **kwargs)

    def has_role(self, role_code: str) -> bool:
        return self.is_superuser or self.roles.filter(code=role_code).exists()

    def __str__(self) -> str:
        return self.display_name or self.email


class VerificationPurpose(models.TextChoices):
    REGISTRATION = "registration", "注册"
    PASSWORD_RESET = "password_reset", "重置密码"


class EmailVerificationCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    purpose = models.CharField(max_length=24, choices=VerificationPurpose.choices)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["email", "purpose", "-created_at"],
                name="email_code_lookup_idx",
            )
        ]


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
