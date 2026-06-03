from django.db import migrations

EVENT_MODEL = "WorkAreaExpectedVisitCountWorkAreaGroupStatusOpportunityAccessExcludedReasonEvent"
INDEX_NAME = "wae_obj_status_created_idx"


def create_index(apps, schema_editor):
    table = apps.get_model("microplanning", EVENT_MODEL)._meta.db_table
    schema_editor.execute(
        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAME} " f'ON "{table}" (pgh_obj_id, status, pgh_created_at)'
    )


def drop_index(apps, schema_editor):
    schema_editor.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {INDEX_NAME}")


class Migration(migrations.Migration):
    atomic = False  # required for CREATE INDEX CONCURRENTLY

    dependencies = [
        ("microplanning", "0013_alter_workarea_case_id"),
    ]

    operations = [
        migrations.RunPython(create_index, drop_index, hints={"run_on_secondary": False}),
    ]
