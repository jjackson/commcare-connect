"""
Configuration for solicitations app.
"""

from django.conf import settings

# TEMPORARY: Hardcoded opportunity_id for Labs API calls.
# This is required by the current production API.
# Configure this in your settings file with LABS_DEFAULT_OPPORTUNITY_ID.
SOLICITATION_DEFAULT_OPPORTUNITY_ID = getattr(settings, "LABS_DEFAULT_OPPORTUNITY_ID", 1)
