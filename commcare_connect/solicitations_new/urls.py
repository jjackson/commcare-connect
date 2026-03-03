from django.urls import path

from . import views

app_name = "solicitations_new"

urlpatterns = [
    # Public (no login required)
    path("", views.PublicSolicitationListView.as_view(), name="public_list"),
    path("<int:pk>/", views.PublicSolicitationDetailView.as_view(), name="public_detail"),
    # Manager views (login required)
    path("manage/", views.ManageSolicitationsView.as_view(), name="manage_list"),
    path("create/", views.SolicitationCreateView.as_view(), name="create"),
    path("<int:pk>/edit/", views.SolicitationEditView.as_view(), name="edit"),
    path("<int:pk>/responses/", views.ResponsesListView.as_view(), name="responses_list"),
    # Response (login required)
    path("<int:pk>/respond/", views.RespondView.as_view(), name="respond"),
    path("response/<int:pk>/", views.ResponseDetailView.as_view(), name="response_detail"),
    # Review (manager required)
    path("response/<int:pk>/review/", views.ReviewView.as_view(), name="review"),
]
