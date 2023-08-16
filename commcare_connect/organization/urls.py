from django.urls import path

from commcare_connect.organization import views

app_name = "organization"

urlpatterns = [
    path("organization/", views.organization_home, name="home"),
]
