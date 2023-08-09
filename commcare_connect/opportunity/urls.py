from django.urls import path

from commcare_connect.opportunity.views import (
    OpportunityCreate,
    OpportunityEdit,
    OpportunityLearnProgressList,
    OpportunityList,
    OpportunityUserLearnProgress,
)

app_name = "opportunity"
urlpatterns = [
    path("", view=OpportunityList.as_view(), name="list"),
    path("create/", view=OpportunityCreate.as_view(), name="create"),
    path("<int:pk>/", view=OpportunityEdit.as_view(), name="edit"),
    path("<int:pk>/learn_progress/", view=OpportunityLearnProgressList.as_view(), name="learn_progress"),
    path(
        "<int:opp_id>/learn_progress/<int:pk>",
        view=OpportunityUserLearnProgress.as_view(),
        name="user_learn_progress",
    ),
]
