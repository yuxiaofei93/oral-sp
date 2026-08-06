from django.contrib.auth import password_validation
from django.db import IntegrityError, transaction
from rest_framework import serializers

from modules.teaching.models import ClassGroup, ClassMembership

from .models import Role, RoleCode, User, UserRole
from .phone import normalize_phone


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "phone", "display_name", "roles"]

    def get_roles(self, user: User) -> list[str]:
        roles = list(user.roles.values_list("code", flat=True))
        if user.is_superuser and RoleCode.ADMINISTRATOR not in roles:
            roles.append(RoleCode.ADMINISTRATOR)
        return sorted(roles)


class RegisterSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    display_name = serializers.CharField(max_length=80)
    class_group_id = serializers.PrimaryKeyRelatedField(
        source="class_group",
        queryset=ClassGroup.objects.filter(is_active=True, course__is_active=True),
    )

    def validate_phone(self, value: str) -> str:
        phone = normalize_phone(value)
        if User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError("该手机号已经注册。")
        return phone

    def validate(self, attrs):
        candidate = User(phone=attrs["phone"], display_name=attrs["display_name"])
        password_validation.validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        class_group = validated_data.pop("class_group")
        try:
            with transaction.atomic():
                user = User.objects.create_user(**validated_data)
                role, _ = Role.objects.get_or_create(
                    code=RoleCode.STUDENT,
                    defaults={"name": RoleCode.STUDENT.label},
                )
                UserRole.objects.create(user=user, role=role)
                ClassMembership.objects.create(class_group=class_group, student=user)
                return user
        except IntegrityError as error:
            raise serializers.ValidationError({"phone": "该手机号已经注册。"}) from error


class RegistrationClassSerializer(serializers.ModelSerializer):
    course_id = serializers.UUIDField(source="course.id", read_only=True)
    course_code = serializers.CharField(source="course.code", read_only=True)
    course_name = serializers.CharField(source="course.name", read_only=True)

    class Meta:
        model = ClassGroup
        fields = ["id", "code", "name", "course_id", "course_code", "course_name"]


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=32)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_phone(self, value: str) -> str:
        return normalize_phone(value)
