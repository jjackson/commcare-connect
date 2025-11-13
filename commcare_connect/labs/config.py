"""
Configuration for Labs apps.
"""

import sys

from django.conf import settings

# TEMPORARY: Hardcoded opportunity_id for Labs API calls.
# All Labs apps (audit, tasks, solicitations) use this for their API client.
# Configure this in your settings file with LABS_DEFAULT_OPP_ID.
LABS_DEFAULT_OPP_ID = getattr(settings, "LABS_DEFAULT_OPP_ID", 1)

# Debug: Print the loaded value on import
print(f"[LABS CONFIG DEBUG] LABS_DEFAULT_OPP_ID = {LABS_DEFAULT_OPP_ID}", file=sys.stderr)
print(f"[LABS CONFIG DEBUG] Settings module = {settings.SETTINGS_MODULE}", file=sys.stderr)
