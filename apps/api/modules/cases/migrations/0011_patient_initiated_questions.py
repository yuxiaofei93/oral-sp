import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import modules.cases.prompts


DEFAULT_QUESTIONS = [
    {
        "id": "diagnosis",
        "base_question": "医生，我这是个什么病？",
        "answer_criteria": "给出可能、初步或明确诊断；或说明暂不能确定，同时提供理由和下一步判断动作。",
        "enabled": True,
    },
    {
        "id": "treatment",
        "base_question": "接下来要怎么治疗？",
        "answer_criteria": "给出治疗或处置方向；或说明需等待结果，同时提供明确下一步。",
        "enabled": True,
    },
    {
        "id": "examinations",
        "base_question": "我需要做什么检查化验吗？",
        "answer_criteria": "给出具体检查、化验方向；或明确无需检查并说明理由。",
        "enabled": True,
    },
]


def seed_patient_questions(apps, schema_editor):
    del schema_editor
    template = apps.get_model("cases", "PatientQuestionTemplate")
    case_version = apps.get_model("cases", "CaseVersion")
    template.objects.update_or_create(
        pk=1,
        defaults={
            "name": "默认患者主动提问",
            "questions": DEFAULT_QUESTIONS,
        },
    )
    case_version.objects.filter(status="published").update(
        patient_questions=DEFAULT_QUESTIONS,
    )


def remove_patient_question_seed(apps, schema_editor):
    del schema_editor
    apps.get_model("cases", "PatientQuestionTemplate").objects.filter(pk=1).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0010_physical_exam_and_assets"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PatientQuestionTemplate",
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
                ("name", models.CharField(default="默认患者主动提问", max_length=80)),
                (
                    "questions",
                    models.JSONField(default=modules.cases.prompts.default_patient_questions),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="patient_question_templates_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="caseversion",
            name="patient_questions_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="caseversion",
            name="patient_questions_mode",
            field=models.CharField(
                choices=[("default", "默认模板"), ("custom", "自定义提示词")],
                default="default",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="caseversion",
            name="patient_questions",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(seed_patient_questions, remove_patient_question_seed),
    ]
