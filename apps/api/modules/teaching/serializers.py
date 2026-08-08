from rest_framework import serializers

from modules.accounts.models import User

from .models import ClassGroup, ClassMembership


class StudentRosterSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="student.id", read_only=True)
    email = serializers.EmailField(source="student.email", read_only=True)
    display_name = serializers.CharField(source="student.display_name", read_only=True)

    class Meta:
        model = ClassMembership
        fields = ["id", "email", "display_name", "created_at"]


class ClassGroupSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.display_name", read_only=True)
    students = StudentRosterSerializer(source="memberships", many=True, read_only=True)
    student_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ClassGroup
        fields = [
            "id",
            "code",
            "name",
            "created_by_name",
            "is_active",
            "student_count",
            "students",
            "created_at",
        ]


class ClassGroupCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)


class ClassGroupStatusSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()


class StudentTransferSerializer(serializers.Serializer):
    target_class_id = serializers.PrimaryKeyRelatedField(
        source="target_class",
        queryset=ClassGroup.objects.filter(is_active=True),
    )


class ManagedStudentClassSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="class_group.id", read_only=True)
    code = serializers.CharField(source="class_group.code", read_only=True)
    name = serializers.CharField(source="class_group.name", read_only=True)
    is_active = serializers.BooleanField(source="class_group.is_active", read_only=True)

    class Meta:
        model = ClassMembership
        fields = ["id", "code", "name", "is_active"]


class ManagedStudentSerializer(serializers.ModelSerializer):
    classes = ManagedStudentClassSerializer(
        source="class_memberships",
        many=True,
        read_only=True,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "display_name",
            "email",
            "classes",
            "is_active",
            "date_joined",
        ]


class ManagedStudentFilterSerializer(serializers.Serializer):
    name = serializers.CharField(required=False, allow_blank=True, max_length=80)
    email = serializers.CharField(required=False, allow_blank=True, max_length=254)
    class_group_id = serializers.UUIDField(required=False)


class ManagedStudentClassUpdateSerializer(serializers.Serializer):
    class_group_id = serializers.PrimaryKeyRelatedField(
        source="class_group",
        queryset=ClassGroup.objects.filter(is_active=True),
    )
