from django.urls import path

from . import views

app_name = "solicitations_new"

urlpatterns = [
    # Public (no login required)
    path("", views.PublicSolicitationListView.as_view(), name="public_list"),
    path("<int:pk>/", views.PublicSolicitationDetailView.as_view(), name="public_detail"),
    # Placeholder for respond view (replaced in Task 7)
    path("<int:pk>/respond/", views.RespondPlaceholderView.as_view(), name="respond"),
]
