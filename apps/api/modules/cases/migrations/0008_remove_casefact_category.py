from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0007_remove_casefact_scoring_fields"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="casefact",
            name="category",
        ),
    ]
