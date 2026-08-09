import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


DEFAULT_CONSENT = "可以，麻烦您检查吧。"


def create_physical_exams(apps, schema_editor):
    CaseVersion = apps.get_model("cases", "CaseVersion")
    PhysicalExam = apps.get_model("cases", "PhysicalExam")
    PhysicalExam.objects.bulk_create(
        [
            PhysicalExam(version_id=version_id, consent_text=DEFAULT_CONSENT)
            for version_id in CaseVersion.objects.values_list("id", flat=True)
        ],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("cases", "0009_patient_prompt_configuration"),
    ]

    operations = [
        migrations.CreateModel(
            name="PhysicalExam",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("findings_text", models.TextField(blank=True)),
                ("consent_text", models.CharField(default=DEFAULT_CONSENT, max_length=500)),
                (
                    "version",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="physical_exam",
                        to="cases.caseversion",
                    ),
                ),
            ],
            options={"abstract": False},
        ),
        migrations.CreateModel(
            name="StoredAsset",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("object_key", models.CharField(max_length=240, unique=True)),
                ("original_name", models.CharField(max_length=255)),
                ("content_type", models.CharField(blank=True, max_length=160)),
                ("size_bytes", models.PositiveBigIntegerField()),
                ("sha256", models.CharField(max_length=64)),
                ("deidentified_confirmed", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="case_assets_uploaded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.CreateModel(
            name="PhysicalExamAsset",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[("image", "图片"), ("attachment", "附件")],
                        max_length=16,
                    ),
                ),
                ("display_order", models.PositiveIntegerField(default=0)),
                (
                    "physical_exam",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assets",
                        to="cases.physicalexam",
                    ),
                ),
                (
                    "stored_asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="physical_exam_links",
                        to="cases.storedasset",
                    ),
                ),
                (
                    "version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="physical_exam_assets",
                        to="cases.caseversion",
                    ),
                ),
            ],
            options={"ordering": ["kind", "display_order", "id"]},
        ),
        migrations.AddConstraint(
            model_name="physicalexamasset",
            constraint=models.UniqueConstraint(
                fields=("physical_exam", "stored_asset"),
                name="unique_physical_exam_asset",
            ),
        ),
        migrations.RunPython(create_physical_exams, migrations.RunPython.noop),
    ]
