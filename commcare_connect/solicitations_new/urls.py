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
    # Placeholder for respond view (replaced in Task 7)
    path("<int:pk>/respond/", views.RespondPlaceholderView.as_view(), name="respond"),
    # Placeholder URL names for forward references (replaced in Tasks 7-8)
    path(
        "<int:pk>/response-detail/",
        views.RespondPlaceholderView.as_view(),
        name="response_detail",
    ),
    path(
        "<int:response_pk>/review/",
        views.RespondPlaceholderView.as_view(),
        name="review",
    ),
]
