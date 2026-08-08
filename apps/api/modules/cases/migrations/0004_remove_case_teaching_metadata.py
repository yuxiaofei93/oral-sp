from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0003_case_code_sequence"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="caseversion",
            name="disease_tags",
        ),
        migrations.RemoveField(
            model_name="caseversion",
            name="estimated_minutes",
        ),
        migrations.RemoveField(
            model_name="caseversion",
            name="specialty",
        ),
        migrations.RemoveField(
            model_name="caseversion",
            name="target_grade",
        ),
        migrations.RemoveField(
            model_name="caseversion",
            name="teaching_objectives",
        ),
    ]
