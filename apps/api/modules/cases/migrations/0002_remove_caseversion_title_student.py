from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="caseversion",
            name="title_student",
        ),
    ]
