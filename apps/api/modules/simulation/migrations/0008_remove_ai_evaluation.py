from django.db import migrations


def convert_ai_results_to_teacher(apps, schema_editor):
    ScoreResult = apps.get_model("simulation", "ScoreResult")
    ScoreResult.objects.filter(evaluation_method="ai").update(evaluation_method="teacher")


class Migration(migrations.Migration):
    dependencies = [
        ("cases", "0011_remove_ai_evaluation_method"),
        ("simulation", "0007_single_stage_case_draft"),
    ]

    operations = [
        migrations.RunPython(convert_ai_results_to_teacher, migrations.RunPython.noop),
        migrations.DeleteModel(name="AIScoreResult"),
        migrations.DeleteModel(name="AIEvaluationRun"),
        migrations.RemoveField(model_name="sessionassessment", name="ai_feedback"),
        migrations.RemoveField(model_name="scoreresult", name="model_version"),
    ]
