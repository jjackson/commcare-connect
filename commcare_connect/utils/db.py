import uuid

from django.db import models
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.text import slugify


class BaseModel(models.Model):
    created_by = models.CharField(max_length=255)
    modified_by = models.CharField(max_length=255)
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def slugify_uniquely(value, model, slugfield="slug"):
    """Returns a slug on a name which is unique within a model's table
    Taken from https://code.djangoproject.com/wiki/SlugifyUniquely
    """
    suffix = 0
    potential = base = slugify(value)
    while True:
        if suffix:
            potential = "-".join([base, str(suffix)])

        if not model.objects.filter(**{slugfield: potential}).count():
            return potential
        # we hit a conflicting slug, so bump the suffix & try again
        suffix += 1


def get_object_by_uuid_or_int(queryset, lookup_value, uuid_field):
    lookup_str = str(lookup_value)

    if lookup_str.isdigit():
        return get_object_or_404(queryset, pk=int(lookup_str))

    try:
        uuid_val = uuid.UUID(lookup_str)
        return get_object_or_404(queryset, **{uuid_field: uuid_val})
    except ValueError:
        raise Http404(f"No {queryset.model._meta.object_name} matches the given query.")
