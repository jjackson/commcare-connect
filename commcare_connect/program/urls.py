from django.urls import path

from commcare_connect.program.views import (  # Phase 3: Solicitation Management Views
    ManagedOpportunityInit,
    ManagedOpportunityList,
    ProgramCreateOrUpdate,
    ProgramSolicitationDashboard,
    SolicitationResponseReview,
    apply_or_decline_application,
    invite_organization,
    manage_application,
    program_home,
)
from commcare_connect.solicitations.ajax_views import (
    solicitation_question_create,
    solicitation_question_delete,
    solicitation_question_reorder,
    solicitation_question_update,
)
from commcare_connect.solicitations.views import (
    SolicitationCreateView,
    SolicitationResponseTableView,
    SolicitationUpdateView,
)

app_name = "program"
urlpatterns = [
    path("", view=program_home, name="home"),
    path("init/", view=ProgramCreateOrUpdate.as_view(), name="init"),
    path("<int:pk>/edit", view=ProgramCreateOrUpdate.as_view(), name="edit"),
    path("<int:pk>/view", view=ManagedOpportunityList.as_view(), name="opportunity_list"),
    path("<int:pk>/opportunity-init", view=ManagedOpportunityInit.as_view(), name="opportunity_init"),
    path("<int:pk>/invite", view=invite_organization, name="invite_organization"),
    path("application/<int:application_id>/<str:action>", manage_application, name="manage_application"),
    path(
        "<int:pk>/application/<int:application_id>/<str:action>/",
        view=apply_or_decline_application,
        name="apply_or_decline_application",
    ),
    # Phase 3: Solicitation Management URLs
    path("<int:pk>/solicitations/", view=ProgramSolicitationDashboard.as_view(), name="solicitation_dashboard"),
    path(
        "<int:pk>/solicitations/<int:solicitation_pk>/responses/",
        view=SolicitationResponseTableView.as_view(),
        name="response_list",
    ),
    path(
        "<int:pk>/solicitations/response/<int:response_pk>/review/",
        view=SolicitationResponseReview.as_view(),
        name="response_review",
    ),
    # Phase 4: Solicitation Authoring URLs
    path(
        "<int:program_pk>/solicitations/create/",
        view=SolicitationCreateView.as_view(),
        name="solicitation_create",
    ),
    path(
        "<int:program_pk>/solicitations/<int:pk>/edit/",
        view=SolicitationUpdateView.as_view(),
        name="solicitation_edit",
    ),
    # AJAX endpoints for question management
    path(
        "<int:program_pk>/solicitations/<int:solicitation_pk>/questions/create/",
        view=solicitation_question_create,
        name="solicitation_question_create",
    ),
    path(
        "<int:program_pk>/solicitations/<int:solicitation_pk>/questions/<int:question_pk>/update/",
        view=solicitation_question_update,
        name="solicitation_question_update",
    ),
    path(
        "<int:program_pk>/solicitations/<int:solicitation_pk>/questions/<int:question_pk>/delete/",
        view=solicitation_question_delete,
        name="solicitation_question_delete",
    ),
    path(
        "<int:program_pk>/solicitations/<int:solicitation_pk>/questions/reorder/",
        view=solicitation_question_reorder,
        name="solicitation_question_reorder",
    ),
]
