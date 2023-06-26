from django.db import models
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
