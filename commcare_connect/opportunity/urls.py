from django.urls import path

from commcare_connect.opportunity.views import OpportunityCreate, OpportunityEdit

app_name = "opportunity"
urlpatterns = [
    path("create/", view=OpportunityCreate.as_view(), name="opportunity_create"),
    path("<int:pk>/", view=OpportunityEdit.as_view(), name="opportunity_edit"),
]
