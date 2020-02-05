from django.db import models

from django_elasticsearch_model_binder import ESBoundModel

from tests.test_app.managers import ESEnabledQuerySet
from tests.test_app.utils import UniqueIdentiferField


class User(ESBoundModel):
    email = models.EmailField(max_length=254)

    es_cached_extra_fields = (UniqueIdentiferField,)

    objects = ESEnabledQuerySet.as_manager()


class Author(ESBoundModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    publishing_name = models.CharField(max_length=25, blank=True, null=True)
    age = models.IntegerField()

    es_cached_model_fields = ['publishing_name', 'user']

    objects = ESEnabledQuerySet.as_manager()
