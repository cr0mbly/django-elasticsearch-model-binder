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
from django_elasticsearch_model_binder.utils import (
    get_es_client, queryset_iterator,
)


class ESModelBinderMixin(models.Model):
    """
    Mixin that binds a models nominated field to an Elasticsearch index.
    Nominated fields will maintain persistency with the models existence
    and configuration within the database.
    """

    # Fields to be cached in ES
    es_cached_fields = []

    # Alias postfix values, used to decern write aliases from read.
    es_index_alias_read_postfix = 'read'
    es_index_alias_write_postfix = 'write'

    class Meta:
        abstract = True

    @classmethod
    def get_index_base_name(cls):
        """
        Retrieve the model defined index name from self.index_name defaulting
        to generated name based on app module directory and model name.
        """
        if hasattr(cls, 'index_name'):
            return cls.index_name
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
            get_es_client().index(
                id=self.pk,
                index=self.get_write_alias_name(),
                body=document,
            )
        except Exception:
            raise UnableToSaveModelToElasticSearch()

    def delete(self, *args, **kwargs):
        """
        Same as save but in reverse, remove the model instances cached
        fields in Elasticsearch.
        """
        try:
            get_es_client().delete(
                index=self.get_write_alias_name(), id=self.pk,
            )
        except Exception:
            # Catch failure and reraise with specific exception.
            raise UnableToDeleteModelFromElasticSearch()

        super().save(*args, **kwargs)


    @staticmethod
    def get_index_mapping():
        """
        Stub mapping of how the index should be created, override this with
        the specific implementation of what fields should be searchable
        and how.
        """
        return {'settings': {}, 'mappings': {}}

    @classmethod
    def get_read_alias_name(cls):
        """
        Generates a unique alias name using either set explicitly by
        overridding this method or in the default format of a
        combination of {index_name}-read.
        """
        return cls.get_index_base_name() + '-' + cls.es_index_alias_read_postfix

    @classmethod
    def get_write_alias_name(cls):
        """
        Generates a unique alias name using either set explicitly by
        overridding this method or in the default format of a
        combination of {index_name}-write.
        """
        return cls.get_index_base_name() + '-' + cls.es_index_alias_write_postfix

    @classmethod
    def generate_index(cls):
        """
        Generates a new index in Elasticsearch for the
        model returning the index name.
        """
        index = cls.get_index_base_name() + '-' + uuid4().hex
        get_es_client().indices.create(
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
        old_indicy_names = []
        if (
            remove_existing_aliases
            and get_es_client().indices.exists_alias(name=alias)
        ):
            old_indicy_names = (
                get_es_client()
                .indices.get_alias(name=alias)
                .keys()
            )

        alias_updates = [
            {'remove': {'index': indicy, 'alias': alias}}
            for indicy in old_indicy_names
        ]
        alias_updates.append({'add': {'index': index, 'alias': alias}})

        get_es_client().indices.update_aliases(body={'actions': alias_updates})

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

        cls.bind_alias(new_indicy, cls.get_write_alias_name())

        chunked_qs = queryset_iterator(qs_to_rebuild or cls.objects.all())

        for qs_chunk in chunked_qs:
            qs_chunk.objects.reindex_into_es()

        cls.bind_alias(new_indicy, cls.get_read_alias_name())


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
                get_es_client(), documents,
                index=self.model.get_write_alias_name(),
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
            get_es_client(), model_documents_to_remove,
            index=self.model.get_write_alias_name(),
        )
