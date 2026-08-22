import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0013_patient_follow_up_configuration"),
        ("simulation", "0008_remove_ai_evaluation"),
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
                    ("patient_follow_up_question", "患者主动询问"),
                    ("patient_follow_up_closing", "患者主动问答收尾"),
                ],
                default="chat",
                max_length=32,
            ),
        ),
        migrations.CreateModel(
            name="PatientFollowUpProgress",
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
                ("next_question_index", models.PositiveIntegerField(default=1)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("awaiting_answer", "等待学生回答"),
                            ("completed", "已完成"),
                        ],
                        default="awaiting_answer",
                        max_length=24,
                    ),
                ),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "session",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="patient_follow_up_progress",
                        to="simulation.simulationsession",
                    ),
                ),
            ],
        ),
    ]
