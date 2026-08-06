from rest_framework import serializers

from .models import ClassGroup, ClassMembership, Course


class StudentRosterSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source="student.id", read_only=True)
    email = serializers.EmailField(source="student.email", read_only=True)
    display_name = serializers.CharField(source="student.display_name", read_only=True)

    class Meta:
        model = ClassMembership
        fields = ["id", "email", "display_name", "created_at"]


class ClassGroupSerializer(serializers.ModelSerializer):
    course_id = serializers.UUIDField(source="course.id", read_only=True)
    course_code = serializers.CharField(source="course.code", read_only=True)
    course_name = serializers.CharField(source="course.name", read_only=True)
    students = StudentRosterSerializer(source="memberships", many=True, read_only=True)
    student_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ClassGroup
        fields = [
            "id",
            "code",
            "name",
            "course_id",
            "course_code",
            "course_name",
            "is_active",
            "student_count",
            "students",
            "created_at",
        ]


class CourseSerializer(serializers.ModelSerializer):
    class_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Course
        fields = ["id", "code", "name", "is_active", "class_count", "created_at", "updated_at"]


class CourseCreateSerializer(serializers.Serializer):
    code = serializers.RegexField(r"^[A-Z0-9][A-Z0-9_-]*$", max_length=40)
    name = serializers.CharField(max_length=120)

    def validate_code(self, value):
        if Course.objects.filter(code=value).exists():
            raise serializers.ValidationError("课程编号已经存在。")
        return value


class ClassGroupCreateSerializer(serializers.Serializer):
    course_id = serializers.PrimaryKeyRelatedField(
        source="course",
        queryset=Course.objects.filter(is_active=True),
    )
    code = serializers.RegexField(r"^[A-Z0-9][A-Z0-9_-]*$", max_length=40)
    name = serializers.CharField(max_length=120)

    def validate(self, attrs):
        if ClassGroup.objects.filter(course=attrs["course"], code=attrs["code"]).exists():
            raise serializers.ValidationError({"code": "该课程下的班级编号已经存在。"})
        return attrs
