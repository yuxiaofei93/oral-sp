import uuid

from django.conf import settings
from django.db import models


class Course(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="courses_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} {self.name}"


class ClassGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="classes")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["course_id", "code"]
        constraints = [
            models.UniqueConstraint(fields=["course", "code"], name="unique_class_code_course"),
        ]

    def __str__(self) -> str:
        return f"{self.course.code} / {self.name}"


class CourseTeacher(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="teacher_links")
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="course_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course", "teacher"],
                name="unique_course_teacher",
            ),
        ]


class ClassMembership(models.Model):
    class_group = models.ForeignKey(
        ClassGroup,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="class_memberships",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["class_group", "student"],
                name="unique_class_student",
            ),
        ]

