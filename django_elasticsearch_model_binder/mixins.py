from uuid import uuid4
from datetime import datetime

from django.db.models.manager import Manager
from django.db import models
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

from django_elasticsearch_model_binder.exceptions import (
    NominatedFieldDoesNotExistForESIndexingException,
    UnableToBulkIndexModelsToElasticSearch,
    UnableToCastESNominatedFieldException,
    UnableToDeleteModelFromElasticSearch,
    UnableToSaveModelToElasticSearch,
)
from django_elasticsearch_model_binder.utils import queryset_iterator


class ESContollerMixin:
    """
    Handles logic for connection to ES instance. breaks out API connection
    for use in Mixins making use of this class.
    """

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




class ESModelBinderMixin(ESContollerMixin, models.Model):
    """
    Mixin that binds a models nominated field to an Elasticsearch index.
    Nominated fields will maintain persistency with the models existence
    and configuration within the database.
    """

    index_name = None
    es_cached_fields = []

    class Meta:
        abstract = True

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

    @classmethod
    def convert_to_indexable_format(cls, value):
        """
        Helper method to cast an incoming value into a format that
        is indexable within ElasticSearch. extend with your own super
        implentation if there are custom types you'd like handled differently.
        """
        if isinstance(value, models.Model):
            return value.pk
        elif isinstance(value, datetime):
            return value.strftime('%Y-%M-%d %H:%M:%S')
        else:
            # Catch all try to cast value to string raising
            # an exception explicitly if that fails.
            try:
                return str(value)
            except Exception:
                raise UnableToCastESNominatedFieldException()

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

        try:
            self.get_es_client().index(
                index=self.get_index_name(),
                doc_type=self.__class__.__name__,
                id=self.pk,
                body=document
            )
        except Exception:
            raise UnableToSaveModelToElasticSearch()

    def delete(self, *args, **kwargs):
        """
        Same as save but in reverse, remove the model instances cached
        fields in Elasticsearch.
        """
        try:
            self.get_es_client().delete(
                index=self.get_index_name(), id=self.pk,
            )
        except Exception:
            # Catch failure and reraise with specific exception.
            raise UnableToDeleteModelFromElasticSearch()

        super().save(*args, **kwargs)


class ESModelAliasMixin(ESModelBinderMixin):
    """
    Mixin binding models to ESIndexes breaks out support for aliasing models.
    This implementation will setup an Elasticsearch index with two aliases
    that support zero downtime rebuilds. As defined in the API below these will
    point to a defined index for the model that itself will contain a mapping
    of how the nominated models fields should be indexed.
    """

    es_index_alias_read_postfix = 'read'
    es_index_alias_write_postfix = 'write'

    class Meta:
        abstract = True

    @staticmethod
    def get_index_mapping():
        """
        Stub mapping of how the index should be created, override this with
        the specific implementation of what fields should be searchable
        and how.
        """
        return {'settings': {}, 'mappings': {}}

    @classmethod
    def get_read_alias(cls):
        """
        Generates a unique alias name using either set explicitly by
        overridding this method or in the default format of a
        combination of {index_name}-read-{uuid}.
        """
        return (
            cls.get_index_name() + '-' + cls.es_index_alias_read_postfix
            + '-' + uuid4().hex
        )

    @classmethod
    def get_write_alias(cls):
        """
        Generates a unique alias name using either set explicitly by
        overridding this method or in the default format of a
        combination of {index_name}-write-{uuid}.
        """
        return (
            cls.get_index_name()
            + '-' + cls.es_index_alias_write_postfix
            + '-' + uuid4().hex
        )

    @classmethod
    def generate_index(cls):
        """
        Generates a uniques base index containing how the index should be
        indexed into elasticsearch this index will be pointed at from the
        aliases post build.
        """
        index = cls.get_index_name() + '-' + uuid4().hex
        cls.get_es_client().indices.create(
            index=index, body=cls.get_index_mapping()
        )
        return index

    @classmethod
    def bind_alias(cls, index, alias, remove_existing_aliases=True):
        """
        Connect an alias to a specified index by default removes alias
        from any other indices if present, set remove_existing_aliases to
        disabled this.
        """
        es_client = cls.get_es_client()

        old_indicy_names = []
        if (
            remove_existing_aliases
            and es_client.indices.exists_alias(name=alias)
        ):
            old_indicy_names = es_client.indices.get_alias(name=alias).keys()

        alias_updates = [
            {'remove': {'index': indicy, 'alias': alias}}
            for indicy in old_indicy_names
        ]
        alias_updates.append({'add': {'index': index, 'alias': alias}})

        es_client.indices.update_aliases(body=alias_updates)

    @classmethod
    def rebuild_index(
        cls, qs_to_rebuild=None, drop_index=False, verbose=False
    ):
        """
        Rebuilds the entire ESIndex for the model, utilizes Aliases to
        preserve access to the old index while the new is being built.

         - drop_index optionally deletes the index rendering it
           unreadable until the index has been rebuilt and the alias
           switched over.
         - verbose provides a timestamped output on the estimated runtime
           of the alias rebuild, useful when rebuilding the index on shell.
        """
        new_indicy = cls.generate_index()

        cls.bind_alias(new_indicy, cls.get_write_alias())

        chunked_qs = queryset_iterator(qs_to_rebuild or cls.objects.all())

        for qs_chunk in chunked_qs:
            qs_chunk.objects.reindex_into_es()

        cls.bind_alias(new_indicy, cls.get_read_alias())



class ESQuerySetMixin:
    """
    Mixin for providing Elasticsearch bulk indexing
    implementation to querysets.
    """

    def reindex_into_es(self):
        """
        Bulk reindex all nominated fields into elasticsearch
        """
        queryset_values = self.values(
            *list(set(['pk', *self.model.es_cached_fields]))
        )

        documents = []
        for model_values in queryset_values:
            doc = {'_id': model_values['pk']}
            if 'pk' not in self.model.es_cached_fields:
                doc['_source'] = model_values
            documents.append(doc)

        try:
            bulk(
                self.model.get_es_client(), documents,
                index=self.model.get_index_name(),
                doc_type=self.model.__name__
            )
        except Exception:
            raise UnableToBulkIndexModelsToElasticSearch()

    def delete_from_es(self):
        """
        Bulk remove models in queryset that exist within ES.
        """
        model_documents_to_remove = [
            {'_id': pk, '_op_type': 'delete'}
            for pk in self.values_list('pk', flat=True)
        ]
        bulk(
            self.model.get_es_client(), model_documents_to_remove,
            index=self.model.get_index_name(),
            doc_type=self.model.__name__,
        )
