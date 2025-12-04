from django.urls import path

from . import views

app_name = "ai"

urlpatterns = [
    path("demo/submit/", views.ai_demo_submit, name="ai_demo_submit"),
    path("demo/status/", views.ai_demo_status, name="ai_demo_status"),
    path("demo/history/", views.ai_demo_history, name="ai_demo_history"),
    path("vibes/", views.vibes, name="vibes"),
]
