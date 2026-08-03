from django.db import migrations


def seed_roles(apps, schema_editor):
    role = apps.get_model("accounts", "Role")
    for code, name in (
        ("student", "学生"),
        ("teacher", "教师"),
        ("administrator", "系统管理员"),
    ):
        role.objects.update_or_create(code=code, defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]

    operations = [migrations.RunPython(seed_roles, migrations.RunPython.noop)]

