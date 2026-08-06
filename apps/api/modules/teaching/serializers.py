from rest_framework import serializers

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
    code = serializers.RegexField(r"^[A-Z0-9][A-Z0-9_-]*$", max_length=40)
    name = serializers.CharField(max_length=120)

    def validate_code(self, value):
        if ClassGroup.objects.filter(code=value).exists():
            raise serializers.ValidationError("班级编号已经存在。")
        return value
