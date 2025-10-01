from django.urls import path

from commcare_connect.data_export import views

app_name = "data_export"
urlpatterns = [
    path("opp-org-program-list/", views.ProgramOpportunityOrganizationDataView.as_view(), name="opp_org_program_list"),
]
