# Generated migration to remove old Django ORM models
# These models have been replaced by ExperimentRecord-based implementation
# See: experiment_models.py, experiment_views.py, data_access.py

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        # Delete models in reverse dependency order
        migrations.DeleteModel(
            name="Assessment",
        ),
        migrations.DeleteModel(
            name="AuditResult",
        ),
        migrations.DeleteModel(
            name="Audit",
        ),
        migrations.DeleteModel(
            name="AuditTemplate",
        ),
    ]



