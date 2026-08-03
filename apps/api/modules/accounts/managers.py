from django.contrib.auth.base_user import BaseUserManager

from .phone import normalize_phone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, phone: str, password: str | None, **extra_fields):
        if not phone:
            raise ValueError("必须提供手机号。")
        user = self.model(phone=normalize_phone(phone), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone, password, **extra_fields)

    def create_superuser(self, phone: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("超级管理员必须设置 is_staff=True。")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("超级管理员必须设置 is_superuser=True。")

        return self._create_user(phone, password, **extra_fields)

