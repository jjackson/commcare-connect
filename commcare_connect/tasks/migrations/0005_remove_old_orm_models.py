# Generated migration to remove old Django ORM models after ExperimentRecord migration

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0004_taskevent_ai_session'),
    ]

    operations = [
        # Remove foreign key relationships first
        migrations.RemoveField(
            model_name='taskcomment',
            name='task',
        ),
        migrations.RemoveField(
            model_name='taskcomment',
            name='author',
        ),
        migrations.RemoveField(
            model_name='taskaisession',
            name='task',
        ),
        migrations.RemoveField(
            model_name='taskevent',
            name='task',
        ),
        migrations.RemoveField(
            model_name='taskevent',
            name='ai_session',
        ),
        migrations.RemoveField(
            model_name='task',
            name='user',
        ),
        migrations.RemoveField(
            model_name='task',
            name='opportunity',
        ),
        migrations.RemoveField(
            model_name='task',
            name='assigned_to',
        ),
        migrations.RemoveField(
            model_name='task',
            name='created_by_user',
        ),
        migrations.RemoveField(
            model_name='opportunitybotconfiguration',
            name='opportunity',
        ),
        # Delete models in correct order (children first)
        migrations.DeleteModel(
            name='TaskComment',
        ),
        migrations.DeleteModel(
            name='TaskAISession',
        ),
        migrations.DeleteModel(
            name='TaskEvent',
        ),
        migrations.DeleteModel(
            name='Task',
        ),
        migrations.DeleteModel(
            name='OpportunityBotConfiguration',
        ),
    ]

