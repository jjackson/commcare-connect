from django.db import models

from commcare_connect.opportunity.models import DeliveryType
from commcare_connect.utils.db import BaseModel, slugify_uniquely


class Program(BaseModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.CharField()
    delivery_type = models.ForeignKey(DeliveryType, null=True, blank=True, on_delete=models.DO_NOTHING)

    def save(self, *args, **kwargs):
        if not self.id:
            self.slug = slugify_uniquely(self.name, self.__class__)
        super().save(*args, **kwargs)
