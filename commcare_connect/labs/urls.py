from django.urls import include, path

from . import oauth_views, views

app_name = "labs"

urlpatterns = [
    # Context management
    path("clear-context/", views.clear_context, name="clear_context"),
    # Connect OAuth (for labs authentication)
    path("login/", oauth_views.labs_login_page, name="login"),
    path("initiate/", oauth_views.labs_oauth_login, name="oauth_initiate"),
    path("callback/", oauth_views.labs_oauth_callback, name="oauth_callback"),
    path("logout/", oauth_views.labs_logout, name="logout"),
    path("status/", oauth_views.labs_status, name="status"),
    path("dashboard/", oauth_views.labs_dashboard, name="dashboard"),
    # CommCare OAuth (for API access)
    path("commcare/initiate/", oauth_views.labs_commcare_initiate, name="commcare_initiate"),
    path("commcare/callback/", oauth_views.labs_commcare_callback, name="commcare_callback"),
    # Dashboard Prototypes
    path("", include("commcare_connect.labs.dashboards.urls")),
]
