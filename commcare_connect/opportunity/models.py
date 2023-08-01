from django.db import models

from commcare_connect.users.models import Organization, User
from commcare_connect.utils.db import BaseModel


class CommCareApp(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="apps",
        related_query_name="app",
    )
    cc_domain = models.CharField(max_length=255)
    cc_app_id = models.CharField(max_length=50)
    name = models.CharField(max_length=255)
    description = models.TextField()
    passing_score = models.IntegerField(null=True)

    def __str__(self):
        return self.name


class Opportunity(BaseModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="opportunities",
        related_query_name="opportunity",
    )
    name = models.CharField(max_length=255)
    description = models.TextField()
    active = models.BooleanField(default=True)
    learn_app = models.ForeignKey(
        CommCareApp,
        on_delete=models.CASCADE,
        related_name="learn_app_opportunities",
        null=True,
    )
    deliver_app = models.ForeignKey(
        CommCareApp,
        on_delete=models.CASCADE,
        null=True,
    )
    max_visits_per_user = models.IntegerField(null=True)
    daily_max_visits_per_user = models.IntegerField(null=True)
    end_date = models.DateField(null=True)
    budget_per_visit = models.IntegerField(null=True)
    total_budget = models.IntegerField(null=True)

    def __str__(self):
        return self.name


class DeliverForm(models.Model):
    app = models.ForeignKey(
        CommCareApp,
        on_delete=models.CASCADE,
        related_name="deliver_form",
        related_query_name="deliver_form",
    )
    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.CASCADE,
        related_name="deliver_form",
        related_query_name="deliver_form",
    )
    name = models.CharField(max_length=255)
    xmlns = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class LearnModule(models.Model):
    app = models.ForeignKey(
        CommCareApp,
        on_delete=models.CASCADE,
        related_name="learn_module",
        related_query_name="learn_module",
    )
    slug = models.SlugField()
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=255)
    time_estimate = models.IntegerField()


class UserModule(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_modules",
        related_query_name="user_module",
    )
    module = models.ForeignKey(
        LearnModule,
        on_delete=models.PROTECT,
        related_name="user_modules",
        related_query_name="user_module",
    )
    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.PROTECT,
        related_name="user_modules",
        related_query_name="user_module",
    )
    date_completed = models.DateTimeField(blank=True, null=True)
    duration = models.TimeField()
    cc_form_id = models.CharField(max_length=25)
    app_build_id = models.CharField(max_length=25)
    app_build_version = models.IntegerField()


class Assessment(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="assessments",
        related_query_name="assessment",
    )
    app = models.ForeignKey(
        CommCareApp,
        on_delete=models.PROTECT,
        related_name="assessments",
        related_query_name="assessment",
    )
    opportunity = models.ForeignKey(
        Opportunity,
        on_delete=models.PROTECT,
        related_name="assessments",
        related_query_name="assessment",
    )
    date_accomplished = models.DateTimeField(blank=True, null=True)
    score = models.IntegerField()
    passing_score = models.IntegerField()
    passed = models.BooleanField()
    cc_form_id = models.CharField(max_length=25)
    app_build_id = models.CharField(max_length=25)
    app_build_version = models.IntegerField()
