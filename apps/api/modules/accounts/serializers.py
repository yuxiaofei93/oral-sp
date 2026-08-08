from django.contrib.auth import password_validation
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from modules.teaching.models import ClassGroup, ClassMembership

from .identifiers import normalize_email_identifier
from .models import Role, RoleCode, User, UserRole, VerificationPurpose
from .verification import VerificationCodeError, consume_verification_code


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    class_names = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "display_name", "roles", "class_names"]

    def get_roles(self, user: User) -> list[str]:
        roles = list(user.roles.values_list("code", flat=True))
        if user.is_superuser and RoleCode.ADMINISTRATOR not in roles:
            roles.append(RoleCode.ADMINISTRATOR)
        return sorted(roles)

    def get_class_names(self, user: User) -> list[str]:
        return list(
            user.class_memberships.filter(class_group__is_active=True)
            .order_by("class_group__name")
            .values_list("class_group__name", flat=True)
        )


class NormalizedEmailField(serializers.EmailField):
    def to_internal_value(self, data):
        return normalize_email_identifier(super().to_internal_value(data))


class RegisterSerializer(serializers.Serializer):
    email = NormalizedEmailField(max_length=254)
    verification_code = serializers.RegexField(r"^\d{6}$", write_only=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    display_name = serializers.CharField(max_length=80)
    class_group_id = serializers.PrimaryKeyRelatedField(
        source="class_group",
        queryset=ClassGroup.objects.filter(is_active=True),
    )

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("该邮箱已经注册。")
        return value

    def validate(self, attrs):
        candidate = User(email=attrs["email"], display_name=attrs["display_name"])
        password_validation.validate_password(attrs["password"], user=candidate)
        return attrs

    def create(self, validated_data):
        class_group = validated_data.pop("class_group")
        verification_code = validated_data.pop("verification_code")
        try:
            consume_verification_code(
                email=validated_data["email"],
                purpose=VerificationPurpose.REGISTRATION,
                code=verification_code,
            )
        except VerificationCodeError as error:
            raise serializers.ValidationError({"verification_code": str(error)}) from error
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    **validated_data,
                    email_verified_at=timezone.now(),
                )
                role, _ = Role.objects.get_or_create(
                    code=RoleCode.STUDENT,
                    defaults={"name": RoleCode.STUDENT.label},
                )
                UserRole.objects.create(user=user, role=role)
                ClassMembership.objects.create(class_group=class_group, student=user)
                return user
        except IntegrityError as error:
            raise serializers.ValidationError({"email": "该邮箱已经注册。"}) from error


class RegistrationClassSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="created_by.display_name", read_only=True)

    class Meta:
        model = ClassGroup
        fields = ["id", "code", "name", "teacher_name"]


class LoginSerializer(serializers.Serializer):
    email = NormalizedEmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class VerificationCodeRequestSerializer(serializers.Serializer):
    email = NormalizedEmailField(max_length=254)


class PasswordResetSerializer(serializers.Serializer):
    email = NormalizedEmailField(max_length=254)
    verification_code = serializers.RegexField(r"^\d{6}$", write_only=True)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = User.objects.filter(email=attrs["email"], is_active=True).first()
        if user is None:
            raise serializers.ValidationError({"verification_code": "验证码无效或已过期。"})
        password_validation.validate_password(attrs["new_password"], user=user)
        attrs["user"] = user
        return attrs

    def save(self):
        user = self.validated_data["user"]
        try:
            consume_verification_code(
                email=user.email,
                purpose=VerificationPurpose.PASSWORD_RESET,
                code=self.validated_data["verification_code"],
            )
        except VerificationCodeError as error:
            raise serializers.ValidationError({"verification_code": str(error)}) from error
        with transaction.atomic():
            user.set_password(self.validated_data["new_password"])
            user.save(update_fields=["password"])
        return user
