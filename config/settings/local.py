from .base import *  # noqa
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
DEBUG = True
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="5xpjGRDKKXRiO2u1AiwUT6fbl5iM89JkQ9lnMCJEhvW1JQvXdNroF2OMSe60KEcR",
)
ALLOWED_HOSTS = ["localhost", "0.0.0.0", "127.0.0.1"] + env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = ["https://*.127.0.0.1", "https://*.loca.lt"] + env.list("CSRF_TRUSTED_ORIGINS", default=[])

# django-debug-toolbar
# ------------------------------------------------------------------------------
INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]  # noqa: F405
DEBUG_TOOLBAR_CONFIG = {
    "DISABLE_PANELS": ["debug_toolbar.panels.redirects.RedirectsPanel"],
    "SHOW_TEMPLATE_CONTEXT": True,
}
INTERNAL_IPS = ["127.0.0.1", "10.0.2.2"]

# Celery
# ------------------------------------------------------------------------------
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# CommCareConnect
# ------------------------------------------------------------------------------

# allow running the deid-scripts in development
INSTALLED_APPS += ["commcare_connect.deid"]

# Labs Mode Configuration
# ------------------------------------------------------------------------------
IS_LABS_ENVIRONMENT = True

# OAuth configuration
LABS_OAUTH_SCOPES = ["export"]

# CLI OAuth Configuration (for get_cli_token management command)
# Register a "Public" OAuth application at your production instance with:
# - Redirect URI: http://localhost:8765/callback
# - Authorization grant type: Authorization code
# - Client type: Public
CLI_OAUTH_CLIENT_ID = env("CLI_OAUTH_CLIENT_ID", default="")
CLI_OAUTH_CLIENT_SECRET = env("CLI_OAUTH_CLIENT_SECRET", default="")  # Not needed for public clients

# Disable local registration
ACCOUNT_ALLOW_REGISTRATION = False

# Override login URL to labs OAuth
LOGIN_URL = "/labs/login/"

# Custom authentication (session-based, no DB)
AUTHENTICATION_BACKENDS = [
    "commcare_connect.labs.auth_backend.LabsOAuthBackend",
]

# Add labs app to installed apps
INSTALLED_APPS = INSTALLED_APPS + ["commcare_connect.labs"]  # noqa: F405

# Add labs middleware after standard auth (keep both for local dev/admin)
# Remove production OrganizationMiddleware and add labs-specific version
MIDDLEWARE = list(MIDDLEWARE)  # noqa: F405
_auth_idx = MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware")
MIDDLEWARE.remove("commcare_connect.users.middleware.OrganizationMiddleware")  # Remove production middleware
MIDDLEWARE.insert(_auth_idx + 1, "commcare_connect.labs.middleware.LabsAuthenticationMiddleware")
MIDDLEWARE.insert(_auth_idx + 2, "commcare_connect.labs.middleware.LabsURLWhitelistMiddleware")
MIDDLEWARE.insert(_auth_idx + 3, "commcare_connect.labs.organization_middleware.LabsOrganizationMiddleware")
