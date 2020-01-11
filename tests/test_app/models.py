from uuid import uuid4
from django.db import models

from django_elasticsearch_model_binder import (
    ESModelBinderMixin, ExtraModelFieldBase,
)

from .managers import ESEnabledQuerySet


class UniqueIdentiferField(ExtraModelFieldBase):

    field_name = 'unique_identifer'

    @classmethod
    def generate_model_map(cls, model_pks):
        """
        Custom Elasticsearch field attached to model document, attributes each
        document with a unique_identifer uuid in Elasticsearch.
        """
        return {pk: uuid4().hex for pk in model_pks}


class User(ESModelBinderMixin, models.Model):
    email = models.EmailField(max_length=254)
    es_cached_extra_fields = (UniqueIdentiferField,)


class Author(ESModelBinderMixin, models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    publishing_name = models.CharField(max_length=25, blank=True, null=True)
    age = models.IntegerField()

    es_cached_model_fields = ['publishing_name', 'user']

    objects = ESEnabledQuerySet.as_manager()
