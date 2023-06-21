from django.urls import path

from commcare_connect.opportunity.views import OpportunityCreate, OpportunityEdit, OpportunityList

app_name = "opportunity"
urlpatterns = [
    path("", view=OpportunityList.as_view(), name="list"),
    path("create/", view=OpportunityCreate.as_view(), name="create"),
    path("<int:pk>/", view=OpportunityEdit.as_view(), name="edit"),
]
