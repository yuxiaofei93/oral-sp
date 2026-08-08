from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0006_remove_casefact_unknown_response"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="casefact",
            name="is_required",
        ),
        migrations.RemoveField(
            model_name="casefact",
            name="score",
        ),
    ]
