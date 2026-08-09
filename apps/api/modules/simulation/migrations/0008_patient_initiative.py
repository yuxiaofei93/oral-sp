import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0011_patient_initiated_questions"),
        ("simulation", "0007_single_stage_case_draft"),
    ]

    operations = [
        migrations.AlterField(
            model_name="message",
            name="kind",
            field=models.CharField(
                choices=[
                    ("chat", "普通消息"),
                    ("physical_exam_consent", "体格检查同意"),
                    ("physical_exam_result", "体格检查结果"),
                    ("patient_initiated_question", "患者主动提问"),
                    ("patient_reaction", "患者反馈"),
                ],
                default="chat",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="modelcall",
            name="student_message",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="model_calls",
                to="simulation.message",
            ),
        ),
        migrations.CreateModel(
            name="PatientInitiativeSchedule",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("activated_at", models.DateTimeField()),
                ("next_due_at", models.DateTimeField(blank=True, null=True)),
                ("generation_token", models.CharField(blank=True, max_length=64)),
                ("generation_started_at", models.DateTimeField(blank=True, null=True)),
                ("generation_anchor_sequence", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "session",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="patient_initiative_schedule",
                        to="simulation.simulationsession",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PatientQuestionState",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("question_id", models.CharField(max_length=80)),
                ("base_question", models.CharField(max_length=300)),
                ("answer_criteria", models.TextField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("unasked", "未提问"),
                            ("pending", "等待回应"),
                            ("deferred", "暂缓"),
                            ("addressed", "已回应"),
                        ],
                        default="unasked",
                        max_length=16,
                    ),
                ),
                ("asked_count", models.PositiveSmallIntegerField(default=0)),
                ("reminder_count", models.PositiveSmallIntegerField(default=0)),
                ("eligible_at", models.DateTimeField(blank=True, null=True)),
                ("addressed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "last_decision_confidence",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        max_digits=5,
                        null=True,
                    ),
                ),
                ("last_decision_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "addressed_by_message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="addressed_patient_question_states",
                        to="simulation.message",
                    ),
                ),
                (
                    "current_question_message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="current_patient_question_states",
                        to="simulation.message",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="patient_question_states",
                        to="simulation.simulationsession",
                    ),
                ),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.AddConstraint(
            model_name="patientquestionstate",
            constraint=models.UniqueConstraint(
                fields=("session", "question_id"),
                name="unique_patient_question_session",
            ),
        ),
        migrations.CreateModel(
            name="PatientQuestionAttempt",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[("initial", "首次提问"), ("reminder", "提醒追问")],
                        max_length=16,
                    ),
                ),
                (
                    "outcome",
                    models.CharField(
                        choices=[
                            ("pending", "等待回应"),
                            ("addressed", "已正面回应"),
                            ("evaded", "未正面回应"),
                            ("silent", "未收到回应"),
                            ("canceled", "已取消"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                (
                    "confidence",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        max_digits=5,
                        null=True,
                    ),
                ),
                ("reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("evaluated_at", models.DateTimeField(blank=True, null=True)),
                (
                    "patient_message",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="patient_question_attempt",
                        to="simulation.message",
                    ),
                ),
                (
                    "reaction_message",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="patient_question_reaction_attempt",
                        to="simulation.message",
                    ),
                ),
                (
                    "state",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attempts",
                        to="simulation.patientquestionstate",
                    ),
                ),
                (
                    "student_message",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="answered_patient_question_attempt",
                        to="simulation.message",
                    ),
                ),
            ],
        ),
    ]
