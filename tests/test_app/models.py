from django.db import models

from django_elasticsearch_model_binder.mixins import ESModelBinderMixin

class User(models.Model):
    email = models.EmailField(max_length=254)

class Author(ESModelBinderMixin, models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    publishing_name = models.CharField(max_length=25, blank=True, null=True)
    age = models.IntegerField()

    es_cached_fields = ['publishing_name', 'user']
