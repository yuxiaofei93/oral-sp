from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("simulation", "0006_physical_exam_release_and_message_kind"),
    ]

    operations = [
        migrations.AddField(
            model_name="simulationsession",
            name="case_draft",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="simulationsession",
            name="case_draft_revision",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="simulationsession",
            name="stage",
            field=models.CharField(
                choices=[("interview", "问诊"), ("completed", "已完成")],
                default="interview",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="sessionstageevent",
            name="to_stage",
            field=models.CharField(
                choices=[("interview", "问诊"), ("completed", "已完成")],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="stagesubmission",
            name="submission_type",
            field=models.CharField(
                choices=[("case_record", "病例记录")],
                max_length=32,
            ),
        ),
    ]
