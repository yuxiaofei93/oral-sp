import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


DEFAULT_PATIENT_PROMPT = (
    "你在口腔医学教学模拟中扮演一名正在和学生面对面交谈的患者。"
    "给定的病情信息是供你理解的病历式语义笔记，不是可以直接朗读的台词。"
    "先理解病情信息，再用第一人称、日常汉语和短句重新组织回答；直接回答当前问题，"
    "像真人说话，可以自然使用‘大概’‘好像’‘我记得’等词。"
    "去掉‘患者’‘病程’‘否认’‘伴有’‘既往史’等病历书写口吻，"
    "不要逐字复制、拼接或背诵病情信息。除无法改写的姓名、数值等原子信息外，"
    "回答不得与任何一条病情信息原文相同。根据 certainty 表现确定、模糊、"
    "记不清或不理解，但不能因此更改病情信息。"
    "回答规则：只聊与本次口腔疾病问诊相关的事情，"
    "偏离话题要礼貌纠正并引导回问诊。"
)


def seed_patient_prompt(apps, schema_editor):
    del schema_editor
    template = apps.get_model("cases", "PatientPromptTemplate")
    case_version = apps.get_model("cases", "CaseVersion")
    template.objects.update_or_create(
        pk=1,
        defaults={
            "name": "默认患者问诊模板",
            "content": DEFAULT_PATIENT_PROMPT,
        },
    )
    case_version.objects.filter(status="published", patient_prompt="").update(
        patient_prompt=DEFAULT_PATIENT_PROMPT
    )


def remove_patient_prompt_seed(apps, schema_editor):
    del schema_editor
    template = apps.get_model("cases", "PatientPromptTemplate")
    template.objects.filter(pk=1).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0008_remove_casefact_category"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PatientPromptTemplate",
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
                    models.CharField(max_length=80, default="默认患者问诊模板"),
                ),
                (
                    "content",
                    models.TextField(
                        default=DEFAULT_PATIENT_PROMPT,
                        validators=[django.core.validators.MaxLengthValidator(8000)],
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="patient_prompt_templates_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="caseversion",
            name="patient_prompt_mode",
            field=models.CharField(
                choices=[("default", "默认模板"), ("custom", "自定义提示词")],
                default="default",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="caseversion",
            name="patient_prompt",
            field=models.TextField(
                blank=True,
                validators=[django.core.validators.MaxLengthValidator(8000)],
            ),
        ),
        migrations.RunPython(seed_patient_prompt, remove_patient_prompt_seed),
    ]
