from django.urls import path

from commcare_connect.data_export import views

app_name = "data_export"
urlpatterns = [
    path("opp-org-program-list/", views.ProgramOpportunityOrganizationDataView.as_view(), name="opp_org_program_list"),
    path("opportunity/<int:opp_id>/", views.SingleOpportunityDataView.as_view(), name="opportunity_data"),
    path("opportunity/<int:opp_id>/user-data/", views.OpportunityUserDataView.as_view(), name="opportunity_user_data"),
]
