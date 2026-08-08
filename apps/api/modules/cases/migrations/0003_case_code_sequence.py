import re

import django.core.validators
from django.db import migrations, models


def seed_case_code_sequence(apps, schema_editor):
    case_model = apps.get_model("cases", "Case")
    sequence_model = apps.get_model("cases", "CaseCodeSequence")
    last_value = 0
    for code in case_model.objects.values_list("code", flat=True):
        match = re.fullmatch(r"CASE-(\d+)", code)
        if match:
            last_value = max(last_value, int(match.group(1)))
    sequence_model.objects.create(id=1, last_value=last_value)


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0002_remove_caseversion_title_student"),
    ]

    operations = [
        migrations.CreateModel(
            name="CaseCodeSequence",
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
                ("last_value", models.PositiveBigIntegerField(default=0)),
            ],
        ),
        migrations.AlterField(
            model_name="case",
            name="code",
            field=models.CharField(
                editable=False,
                max_length=40,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        "^[A-Z0-9][A-Z0-9_-]*$",
                        "病例编号只能使用大写字母、数字、_ 和 -。",
                    )
                ],
            ),
        ),
        migrations.RunPython(seed_case_code_sequence, migrations.RunPython.noop),
    ]
