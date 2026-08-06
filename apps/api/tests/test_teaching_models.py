import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from modules.teaching.models import ClassGroup, ClassMembership, Course

User = get_user_model()


@pytest.mark.django_db
def test_student_can_only_join_a_class_once():
    teacher = User.objects.create_user(
        email="teacher@example.com",
        password="MolarTraining!2026",
        display_name="测试教师",
    )
    student = User.objects.create_user(
        email="student@example.com",
        password="MolarTraining!2026",
        display_name="测试学生",
    )
    course = Course.objects.create(code="ORAL-001", name="口腔问诊基础", created_by=teacher)
    class_group = ClassGroup.objects.create(course=course, code="2026-A", name="2026 A 班")
    ClassMembership.objects.create(class_group=class_group, student=student)

    with pytest.raises(IntegrityError), transaction.atomic():
        ClassMembership.objects.create(class_group=class_group, student=student)
