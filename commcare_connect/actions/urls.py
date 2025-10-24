from django.urls import path

from . import views

app_name = "actions"

urlpatterns = [
    path("", views.actions_list, name="list"),
    path("<int:action_id>/", views.action_detail_streamlined, name="detail"),
    path("<int:action_id>/v2/", views.action_detail_simplified, name="detail_v2"),
    path("<int:action_id>/enhanced/", views.action_detail_enhanced, name="detail_enhanced"),
    path("<int:action_id>/timeline/", views.action_detail_timeline, name="detail_timeline"),
    path("<int:action_id>/cards/", views.action_detail_cards, name="detail_cards"),
    path("<int:action_id>/split/", views.action_detail_split, name="detail_split"),
]
