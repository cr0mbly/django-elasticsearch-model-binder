from datetime import datetime

from django.db import models
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from elasticsearch import Elasticsearch

from .exceptions import (
    NominatedFieldDoesNotExistForESIndexingException,
    UnableToCastESNominatedFieldToStringException,
)


class ESModelBinderMixin:
    """
    Mixin that binds a models nominated field to an Elasticsearch index.
    Nominated fields will maintain persistency with the models existence
    and configuration within the database.
    """

    index_name = None
    es_cached_fields = []

    @classmethod
    def convert_to_indexable_format(cls, value):
        """
        Helper method to cast an incoming value into a format that
        is indexable format with ElasticSearch.
        """
        if isinstance(value, models.Model):
            return value.pk
        elif isinstance(value, datetime):
            return str(value)
        else:
            # Catch all try to cast value to string raising
            # an exception explicitly if that fails.
            try:
                return str(value)
            except Exception:
                raise UnableToCastESNominatedFieldToStringException()

    @classmethod
    def get_index_name(cls):
        """
        Retrieve the model defined index name from self.index_name defaulting
        to generated name based on app module directory and model name.
        """
        if cls.index_name:
            return index_name
        else:
            return '-'.join(
                cls.__module__.lower().split('.')
                + [cls.__class__.__name__.lower()]
            )

    def save(self, *args, **kwargs):
        """
        Override model save to index those fields nominated by es_cached_fields
        storring them in elasticsearch.
        """
        super().save(*args, **kwargs)

        document = {}
        for field in self.es_cached_fields:
            if not hasattr(self, field):
                raise NominatedFieldDoesNotExistForESIndexingException()

            document[field] = self.convert_to_indexable_format(
                getattr(self, field)
            )

        self.get_es_client().index(
            index=self.get_index_name(),
            doc_type=self.__class__.__name__,
            id=self.pk,
            body=document
        )

    @classmethod
    def get_es_client(cls):
        """
        Return the elasticsearch client instance, allows implementer to extend
        mixin here replacing this implementation with one more suited to
        their use case.
        """
        if not hasattr(settings, 'DJANGO_ES_MODEL_CONFIG'):
            raise ImproperlyConfigured(
                'DJANGO_ES_MODEL_CONFIG must be defined in app settings'
            )

        return Elasticsearch(**settings.DJANGO_ES_MODEL_CONFIG)
