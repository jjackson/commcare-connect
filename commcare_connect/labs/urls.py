from django.urls import include, path

from commcare_connect.labs import views
from commcare_connect.labs.integrations.commcare import oauth_views as commcare_oauth_views
from commcare_connect.labs.integrations.connect import oauth_views as connect_oauth_views

app_name = "labs"

urlpatterns = [
    # Context management
    path("clear-context/", views.clear_context, name="clear_context"),
    path("refresh-org-data/", views.refresh_org_data, name="refresh_org_data"),
    # Connect OAuth (for labs authentication)
    path("login/", connect_oauth_views.labs_login_page, name="login"),
    path("initiate/", connect_oauth_views.labs_oauth_login, name="oauth_initiate"),
    path("callback/", connect_oauth_views.labs_oauth_callback, name="oauth_callback"),
    path("logout/", connect_oauth_views.labs_logout, name="logout"),
    path("status/", connect_oauth_views.labs_status, name="status"),
    path("dashboard/", connect_oauth_views.labs_dashboard, name="dashboard"),
    # CommCare OAuth (for API access)
    path("commcare/initiate/", commcare_oauth_views.labs_commcare_initiate, name="commcare_initiate"),
    path("commcare/callback/", commcare_oauth_views.labs_commcare_callback, name="commcare_callback"),
    # Dashboard Prototypes
    path("", include("commcare_connect.labs.dashboards.urls")),
]
