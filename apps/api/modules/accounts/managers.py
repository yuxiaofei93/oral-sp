from django.contrib.auth.base_user import BaseUserManager

from .identifiers import normalize_email_identifier


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError("必须提供邮箱。")
        user = self.model(email=normalize_email_identifier(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        display_name = str(extra_fields.get("display_name", "")).strip()

        if extra_fields.get("is_staff") is not True:
            raise ValueError("超级管理员必须设置 is_staff=True。")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("超级管理员必须设置 is_superuser=True。")
        if not display_name:
            raise ValueError("超级管理员必须提供姓名。")

        extra_fields["display_name"] = display_name
        return self._create_user(email, password, **extra_fields)
