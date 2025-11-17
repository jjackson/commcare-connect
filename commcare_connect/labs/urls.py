from django.urls import path

from . import ai_views, oauth_views

app_name = "labs"

urlpatterns = [
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
    # Pydantic AI Demo
    path("ai-demo/", ai_views.ai_demo_view, name="ai_demo"),
    path("ai-demo/submit/", ai_views.ai_demo_submit, name="ai_demo_submit"),
    path("ai-demo/status/", ai_views.ai_demo_status, name="ai_demo_status"),
]
