from django.urls import path

from .views import (
    DeliveryTypeDetailView,
    DeliveryTypesListView,
    LabsHomeView,
    ManageSolicitationsListView,
    MyResponsesListView,
    SolicitationCreateOrUpdate,
    SolicitationDetailView,
    SolicitationListView,
    SolicitationResponseCreateOrUpdate,
    SolicitationResponseDetailView,
    SolicitationResponseReviewCreateOrUpdate,
    SolicitationResponsesListView,
)

app_name = "solicitations"

urlpatterns = [
    # Labs Home
    path("", LabsHomeView.as_view(), name="home"),
    # Delivery Types (Public - any authenticated user)
    path("delivery-types/", DeliveryTypesListView.as_view(), name="delivery_types"),
    path("delivery-types/<slug:slug>/", DeliveryTypeDetailView.as_view(), name="delivery_type_detail"),
    # Program Manager URLs
    path("manage/", ManageSolicitationsListView.as_view(), name="manage_list"),
    path("create/", SolicitationCreateOrUpdate.as_view(), name="create"),
    path("solicitation/<int:pk>/edit/", SolicitationCreateOrUpdate.as_view(), name="edit"),
    path(
        "solicitation/<int:solicitation_pk>/responses/",
        SolicitationResponsesListView.as_view(),
        name="solicitation_responses",
    ),
    # Public browsing URLs (no /opportunities/ prefix - these are solicitations)
    path("browse/", SolicitationListView.as_view(), name="list"),
    path("browse/eoi/", SolicitationListView.as_view(), {"type": "eoi"}, name="eoi_list"),
    path("browse/rfp/", SolicitationListView.as_view(), {"type": "rfp"}, name="rfp_list"),
    path("<int:pk>/", SolicitationDetailView.as_view(), name="detail"),
    # Organization response URLs
    path("responses/", MyResponsesListView.as_view(), name="my_responses"),
    path("<int:solicitation_pk>/respond/", SolicitationResponseCreateOrUpdate.as_view(), name="respond"),
    path("response/<int:pk>/", SolicitationResponseDetailView.as_view(), name="response_detail"),
    path("response/<int:pk>/edit/", SolicitationResponseCreateOrUpdate.as_view(), name="response_edit"),
    # Review URLs
    path(
        "response/<int:response_pk>/review/", SolicitationResponseReviewCreateOrUpdate.as_view(), name="review_create"
    ),
]
