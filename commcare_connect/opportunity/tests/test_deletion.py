import pytest

from commcare_connect.opportunity.deletion import OPPORTUNITY_DELETIONS, delete_opportunity_data
from commcare_connect.opportunity.models import LabsRecord
from commcare_connect.opportunity.tests import factories
from commcare_connect.program.tests.factories import ManagedOpportunityFactory


@pytest.mark.django_db
@pytest.mark.parametrize("opportunity_factory", [factories.OpportunityFactory, ManagedOpportunityFactory])
def test_delete_opportunity_data_clears_registered_models(opportunity_factory):
    opportunity = opportunity_factory()
    access = factories.OpportunityAccessFactory(opportunity=opportunity)
    payment_unit = factories.PaymentUnitFactory(opportunity=opportunity)
    deliver_unit = factories.DeliverUnitFactory(payment_unit=payment_unit)

    factories.CompletedModuleFactory(opportunity=opportunity, opportunity_access=access)
    factories.AssessmentFactory(opportunity=opportunity, opportunity_access=access)
    factories.PaymentFactory(opportunity_access=access, payment_unit=payment_unit)
    factories.CatchmentAreaFactory(opportunity=opportunity, opportunity_access=None)
    factories.CatchmentAreaFactory(opportunity=opportunity, opportunity_access=access)
    factories.PaymentInvoiceFactory(opportunity=opportunity)
    factories.OpportunityVerificationFlagsFactory(opportunity=opportunity)
    factories.UserInviteFactory(opportunity=opportunity, opportunity_access=access)
    factories.FormJsonValidationRulesFactory(opportunity=opportunity)
    factories.DeliverUnitFlagRulesFactory(opportunity=opportunity, deliver_unit=deliver_unit)
    factories.CredentialConfigurationFactory(opportunity=opportunity)
    factories.UserCredentialFactory(opportunity=opportunity)
    LabsRecord.objects.create(
        opportunity=opportunity,
        organization=opportunity.organization,
        experiment="cleanup",
        type="note",
        data={},
    )

    delete_opportunity_data(opportunity)

    for deletion in OPPORTUNITY_DELETIONS:
        assert not deletion.model.objects.filter(**{deletion._opp_id_filter: opportunity.id}).exists()
