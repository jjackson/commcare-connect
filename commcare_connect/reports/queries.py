from django.db.models import Case, DateTimeField, ExpressionWrapper, F, FloatField, Value, When
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Extract

from commcare_connect.opportunity.models import UserVisit


def get_visit_map_queryset_base():
    return (
        UserVisit.objects.annotate(
            username_connectid=F("form_json__metadata__username"),
            deliver_unit_name=F("deliver_unit__name"),
            days_since_opp_start=ExpressionWrapper(
                Extract(F("visit_date") - F("opportunity__start_date"), "day"), output_field=FloatField()
            ),
            timestart_str=KeyTextTransform("timeStart", KeyTextTransform("metadata", F("form_json"))),
            timeend_str=KeyTextTransform("timeEnd", KeyTextTransform("metadata", F("form_json"))),
            visit_duration=ExpressionWrapper(
                Extract(Cast("timeend_str", DateTimeField()) - Cast("timestart_str", DateTimeField()), "epoch") / 60,
                output_field=FloatField(),
            ),
            gps_location_lat=Case(
                When(
                    form_json__metadata__location__isnull=False,
                    then=ExpressionWrapper(F("form_json__metadata__location__0"), output_field=FloatField()),
                ),
                default=Value(None),
                output_field=FloatField(),
            ),
            gps_location_long=Case(
                When(
                    form_json__metadata__location__isnull=False,
                    then=ExpressionWrapper(F("form_json__metadata__location__1"), output_field=FloatField()),
                ),
                default=Value(None),
                output_field=FloatField(),
            ),
        )
        .select_related("deliver_unit", "opportunity")
        .values(
            "opportunity_id",
            "xform_id",
            "visit_date",
            "username_connectid",
            "deliver_unit_name",
            "days_since_opp_start",
            "entity_id",
            "status",
            "flagged",
            "flag_reason",
            "reason",
            "timestart_str",
            "timeend_str",
            "visit_duration",
            "gps_location_lat",
            "gps_location_long",
        )
    )
