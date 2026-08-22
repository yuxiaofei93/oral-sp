from django.db import migrations, models
from django.core.validators import MaxLengthValidator


OLD_DEFAULT_PATIENT_PROMPT = (
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

DEFAULT_PATIENT_STYLE = (
    "使用第一人称、自然的日常汉语和简短句子回答。直接回应学生的问题，像真人说话；"
    "可以自然使用“大概”“好像”“我记得”等词，不使用病历书写口吻。"
)


def migrate_default_prompt_to_style(apps, schema_editor):
    PatientPromptTemplate = apps.get_model("cases", "PatientPromptTemplate")
    CaseVersion = apps.get_model("cases", "CaseVersion")

    template = PatientPromptTemplate.objects.filter(pk=1).first()
    if template:
        template.name = "默认患者表达风格"
        if template.content.strip() == OLD_DEFAULT_PATIENT_PROMPT:
            template.content = DEFAULT_PATIENT_STYLE
        template.save(update_fields=["name", "content"])

    CaseVersion.objects.filter(
        patient_prompt_mode="default",
        patient_prompt=OLD_DEFAULT_PATIENT_PROMPT,
    ).update(patient_prompt=DEFAULT_PATIENT_STYLE)


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0011_remove_ai_evaluation_method"),
    ]

    operations = [
        migrations.RunPython(migrate_default_prompt_to_style, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="patientprompttemplate",
            name="name",
            field=models.CharField(default="默认患者表达风格", max_length=80),
        ),
        migrations.AlterField(
            model_name="patientprompttemplate",
            name="content",
            field=models.TextField(
                default=DEFAULT_PATIENT_STYLE,
                validators=[MaxLengthValidator(8000)],
            ),
        ),
        migrations.AlterField(
            model_name="caseversion",
            name="patient_prompt_mode",
            field=models.CharField(
                choices=[("default", "默认风格"), ("custom", "自定义表达风格")],
                default="default",
                max_length=16,
            ),
        ),
    ]
