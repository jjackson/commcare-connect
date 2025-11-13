"""
Configuration for solicitations app.
"""

from django.conf import settings

# TEMPORARY: Hardcoded opportunity_id for solicitations API calls.
# This is required by the current production API but will be removed once
# the API is updated to tie solicitations to programs instead of opportunities.
# Configure this in your settings file with SOLICITATION_DEFAULT_OPPORTUNITY_ID.
SOLICITATION_DEFAULT_OPPORTUNITY_ID = getattr(settings, "SOLICITATION_DEFAULT_OPPORTUNITY_ID", 1)
