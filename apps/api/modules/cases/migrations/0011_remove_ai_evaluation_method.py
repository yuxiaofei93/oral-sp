from django.db import migrations, models


def convert_ai_items_to_teacher(apps, schema_editor):
    ScoringItem = apps.get_model("cases", "ScoringItem")
    ScoringItem.objects.filter(evaluation_method="ai").update(evaluation_method="teacher")


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0010_physical_exam_and_assets"),
    ]

    operations = [
        migrations.RunPython(convert_ai_items_to_teacher, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="scoringitem",
            name="evaluation_method",
            field=models.CharField(
                choices=[("rule", "规则评分"), ("teacher", "教师评价")],
                default="rule",
                max_length=16,
            ),
        ),
    ]
