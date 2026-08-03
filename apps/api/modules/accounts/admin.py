from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Role, User, UserRole


class UserRoleInline(admin.TabularInline):
    model = UserRole
    extra = 0
    fk_name = "user"


@admin.register(User)
class PhoneUserAdmin(UserAdmin):
    model = User
    ordering = ["phone"]
    list_display = ["phone", "display_name", "is_active", "is_staff", "last_login"]
    search_fields = ["phone", "display_name"]
    inlines = [UserRoleInline]
    fieldsets = (
        (None, {"fields": ("phone", "password")}),
        ("个人信息", {"fields": ("display_name", "phone_verified_at")}),
        ("权限", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        ("时间", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("phone", "display_name", "password1", "password2"),
            },
        ),
    )


admin.site.register(Role)

