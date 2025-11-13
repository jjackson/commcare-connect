"""
Configuration for Labs apps.
"""

from django.conf import settings

# TEMPORARY: Hardcoded opportunity_id for Labs API calls.
# All Labs apps (audit, tasks, solicitations) use this for their API client.
# Configure this in your settings file with LABS_DEFAULT_OPPORTUNITY_ID.
LABS_DEFAULT_OPPORTUNITY_ID = getattr(settings, "LABS_DEFAULT_OPPORTUNITY_ID", 1)
