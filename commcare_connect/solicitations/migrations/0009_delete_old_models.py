# Generated migration to remove old Django ORM models
# These models have been replaced by ExperimentRecord-based implementation
# See: experiment_models.py, experiment_helpers.py, data_access.py

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("solicitations", "0008_simplify_response_status"),
    ]

    operations = [
        # Delete models in reverse dependency order
        migrations.DeleteModel(
            name="SolicitationReview",
        ),
        migrations.DeleteModel(
            name="ResponseAttachment",
        ),
        migrations.DeleteModel(
            name="SolicitationResponse",
        ),
        migrations.DeleteModel(
            name="SolicitationQuestion",
        ),
        migrations.DeleteModel(
            name="Solicitation",
        ),
    ]



