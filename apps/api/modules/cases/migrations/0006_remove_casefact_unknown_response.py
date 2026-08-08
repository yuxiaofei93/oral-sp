from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0005_remove_casefact_routing_hints"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="casefact",
            name="unknown_response",
        ),
    ]
