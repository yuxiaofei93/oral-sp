import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0010_physical_exam_and_assets"),
        ("simulation", "0005_alter_caseassignment_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="kind",
            field=models.CharField(
                choices=[
                    ("chat", "普通消息"),
                    ("physical_exam_consent", "体格检查同意"),
                    ("physical_exam_result", "体格检查结果"),
                ],
                default="chat",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="modelcall",
            name="route_confidence",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=5,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="modelcall",
            name="routed_intent",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.CreateModel(
            name="PhysicalExamRelease",
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
                ("released_at", models.DateTimeField(auto_now_add=True)),
                (
                    "consent_message",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="physical_exam_consent_release",
                        to="simulation.message",
                    ),
                ),
                (
                    "result_message",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="physical_exam_result_release",
                        to="simulation.message",
                    ),
                ),
                (
                    "session",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="physical_exam_release",
                        to="simulation.simulationsession",
                    ),
                ),
                (
                    "trigger_message",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="triggered_physical_exam",
                        to="simulation.message",
                    ),
                ),
            ],
        ),
    ]
