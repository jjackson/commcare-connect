"""
Labs environment settings.

Session-based OAuth authentication with no user database storage.
"""

from .staging import *  # noqa

# Labs environment flags
IS_LABS_ENVIRONMENT = True
DEPLOY_ENVIRONMENT = "labs"

# OAuth configuration
LABS_OAUTH_SCOPES = ["export"]  # Expandable: ["export", "labs_data_storage"]
# Disable local registration
ACCOUNT_ALLOW_REGISTRATION = False

# Override login URL to labs OAuth
LOGIN_URL = "/labs/login/"

# Custom authentication (session-based, no DB)
AUTHENTICATION_BACKENDS = [
    "commcare_connect.labs.auth_backend.LabsOAuthBackend",
]

# Add labs app and custom_analysis
INSTALLED_APPS = list(INSTALLED_APPS)  # noqa: F405
INSTALLED_APPS.append("commcare_connect.labs")
INSTALLED_APPS.append("commcare_connect.custom_analysis.chc_nutrition")

# Replace default AuthenticationMiddleware with labs version
# Remove production OrganizationMiddleware and add labs-specific middlewares
MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405
_auth_idx = MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware")
MIDDLEWARE[_auth_idx] = "commcare_connect.labs.middleware.LabsAuthenticationMiddleware"
MIDDLEWARE.remove("commcare_connect.users.middleware.OrganizationMiddleware")  # Remove production middleware
MIDDLEWARE.insert(_auth_idx + 1, "commcare_connect.labs.middleware.LabsURLWhitelistMiddleware")
MIDDLEWARE.insert(_auth_idx + 2, "commcare_connect.labs.context.LabsContextMiddleware")

# CommCare OAuth configuration (for accessing CommCare HQ APIs)
# These should be set via environment variables
COMMCARE_HQ_URL = env("COMMCARE_HQ_URL", default="https://www.commcarehq.org")  # noqa: F405
COMMCARE_OAUTH_CLIENT_ID = env("COMMCARE_OAUTH_CLIENT_ID", default="")  # noqa: F405
COMMCARE_OAUTH_CLIENT_SECRET = env("COMMCARE_OAUTH_CLIENT_SECRET", default="")  # noqa: F405
COMMCARE_OAUTH_CLI_CLIENT_ID = env("COMMCARE_OAUTH_CLI_CLIENT_ID", default="")  # noqa: F405

# Open Chat Studio OAuth configuration (for accessing OCS APIs)
OCS_URL = env("OCS_URL", default="https://www.openchatstudio.com")  # noqa: F405
OCS_OAUTH_CLIENT_ID = env("OCS_OAUTH_CLIENT_ID", default="")  # noqa: F405
OCS_OAUTH_CLIENT_SECRET = env("OCS_OAUTH_CLIENT_SECRET", default="")  # noqa: F405

# Labs apps configuration
# No longer need hardcoded opportunity_id - API now supports organization_id/program_id

# Analysis backend: "python_redis" (default) or "sql"
# python_redis: Redis/file caching with pandas computation
# sql: PostgreSQL table caching with SQL computation
LABS_ANALYSIS_BACKEND = env("LABS_ANALYSIS_BACKEND", default="python_redis")  # noqa: F405
