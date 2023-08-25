from django.urls import path

from commcare_connect.opportunity.views import (
    OpportunityCreate,
    OpportunityDetail,
    OpportunityEdit,
    OpportunityList,
    OpportunityUserLearnProgress,
    OpportunityUserTableView,
    OpportunityUserVisitTableView,
    export_user_visits,
    update_visit_status_import,
)

app_name = "opportunity"
urlpatterns = [
    path("", view=OpportunityList.as_view(), name="list"),
    path("create/", view=OpportunityCreate.as_view(), name="create"),
    path("<int:pk>/edit", view=OpportunityEdit.as_view(), name="edit"),
    path("<int:pk>/", view=OpportunityDetail.as_view(), name="detail"),
    path("<int:pk>/user_table/", view=OpportunityUserTableView.as_view(), name="user_table"),
    path("<int:pk>/visit_table/", view=OpportunityUserVisitTableView.as_view(), name="visit_table"),
    path("<int:pk>/visit_export/", view=export_user_visits, name="visit_export"),
    path("<int:pk>/visit_import/", view=update_visit_status_import, name="visit_import"),
    path(
        "<int:opp_id>/learn_progress/<int:pk>",
        view=OpportunityUserLearnProgress.as_view(),
        name="user_learn_progress",
    ),
]
