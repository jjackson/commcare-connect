from django.urls import path

from commcare_connect.organization import views

app_name = "organization"

urlpatterns = [
    path("organization/", views.organization_home, name="home"),
    path("organization/invite/<slug:invite_id>/", views.accept_invite, name="accept_invite"),
]
