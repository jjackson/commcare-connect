# Generated manually for chat widget integration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('opportunity', '0082_opportunityaccess_opportunity_opportu_94eae8_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='opportunity',
            name='chat_widget_enabled',
            field=models.BooleanField(default=False, help_text='Enable OpenChatStudio chat widget for this opportunity'),
        ),
        migrations.AddField(
            model_name='opportunity',
            name='chatbot_id',
            field=models.CharField(blank=True, help_text='OpenChatStudio chatbot ID', max_length=255, null=True),
        ),
    ]