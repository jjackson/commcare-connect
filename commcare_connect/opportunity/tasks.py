from commcare_connect.opportunity.app_xml import get_connect_blocks_for_app
from commcare_connect.opportunity.models import LearnModule, Opportunity
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
def add_connect_users(data_file, opportunity):
    numbers = [line.strip() for line in f]
    result = request.get(f"{CONNECT_ID}/users/fetch_users", auth=(settings.CONNECTID_CLIENT_ID, settings.CONNECTID_CLIENT_SECRET), params={"phone_numbers": numbers})
    data = result.json()
    for user in data["found_users"]:
        u = User.objects.get_or_create(username=user["username"])
        OpportunityAccess.get_or_create(user=user, opportunity=oppportunity)
