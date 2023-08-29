import requests
from django.conf import settings

from commcare_connect.opportunity.app_xml import get_connect_blocks_for_app
from commcare_connect.opportunity.models import LearnModule, Opportunity, OpportunityAccess
from commcare_connect.users.models import User
from config import celery_app


@celery_app.task()
def create_learn_modules_assessments(opportunity_id):
    opportunity = Opportunity.objects.filter(id=opportunity_id).first()
    learn_app = opportunity.learn_app
    connect_blocks = get_connect_blocks_for_app(learn_app.cc_domain, learn_app.cc_app_id)

    for block in connect_blocks:
        LearnModule.objects.update_or_create(
            app=learn_app,
            name=block.name,
            defaults={
                "description": block.description,
                "time_estimate": block.time_estimate,
            },
        )


@celery_app.task()
def add_connect_users(user_list: list[str], opportunity_id: str):
    result = requests.get(
        f"{settings.CONNECTID_URL}/users/fetch_users",
        auth=(settings.CONNECTID_CLIENT_ID, settings.CONNECTID_CLIENT_SECRET),
        params={"phone_numbers": user_list},
    )
    data = result.json()
    for user in data["found_users"]:
        u = User.objects.get_or_create(username=user["username"])
        OpportunityAccess.objects.get_or_create(user=u, opportunity_id=opportunity_id)
