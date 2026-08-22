import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


DEFAULT_QUESTIONS = [
    "医生，我这个是什么病啊？",
    "那接下来要怎么治疗呢？",
    "我还需要做什么化验或者检查吗？",
]
DEFAULT_CLOSING = "好的，我明白了，谢谢医生。"


def seed_follow_up_configuration(apps, schema_editor):
    PatientFollowUpTemplate = apps.get_model("cases", "PatientFollowUpTemplate")
    CaseVersion = apps.get_model("cases", "CaseVersion")
    PatientFollowUpTemplate.objects.get_or_create(
        pk=1,
        defaults={
            "name": "默认体格检查后患者主动询问",
            "questions": DEFAULT_QUESTIONS,
            "closing_text": DEFAULT_CLOSING,
        },
    )
    CaseVersion.objects.filter(status="draft").update(patient_follow_up_mode="default")


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0012_split_patient_policy_and_style"),
    ]

    operations = [
        migrations.CreateModel(
            name="PatientFollowUpTemplate",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        default="默认体格检查后患者主动询问",
                        max_length=80,
                    ),
                ),
                ("questions", models.JSONField(default=list)),
                ("closing_text", models.CharField(default=DEFAULT_CLOSING, max_length=500)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="patient_follow_up_templates_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="caseversion",
            name="patient_follow_up_closing_text",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="caseversion",
            name="patient_follow_up_mode",
            field=models.CharField(
                choices=[
                    ("default", "跟随系统默认"),
                    ("custom", "病例自定义"),
                    ("disabled", "关闭"),
                ],
                default="disabled",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="caseversion",
            name="patient_follow_up_questions",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(seed_follow_up_configuration, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="caseversion",
            name="patient_follow_up_mode",
            field=models.CharField(
                choices=[
                    ("default", "跟随系统默认"),
                    ("custom", "病例自定义"),
                    ("disabled", "关闭"),
                ],
                default="default",
                max_length=16,
            ),
        ),
    ]
