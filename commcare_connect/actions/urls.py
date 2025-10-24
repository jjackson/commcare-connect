from django.urls import path

from . import views

app_name = "actions"

urlpatterns = [
    path("", views.actions_list, name="list"),
    path("<int:action_id>/", views.action_detail_streamlined, name="detail"),
]
