from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0004_remove_case_teaching_metadata"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="casefact",
            name="semantic_tags",
        ),
        migrations.RemoveField(
            model_name="casefact",
            name="synonyms",
        ),
    ]
