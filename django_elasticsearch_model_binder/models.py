from datetime import datetime, date
from uuid import uuid4

from django.db.models import Model
from elasticsearch.exceptions import NotFoundError

from django_elasticsearch_model_binder.exceptions import (
    ElasticSearchFailure,
    UnableToCastESNominatedFieldException,
    UnableToDeleteModelFromElasticSearch,
    UnableToSaveModelToElasticSearch,
)
from django_elasticsearch_model_binder.utils import (
    build_document_from_model, get_es_client,
    get_index_names_from_alias, queryset_iterator,
)


class ESBoundModel(Model):
    """
    Mixin that binds a models nominated field to an Elasticsearch index.
    Nominated fields will maintain persistency with the models existence
    and configuration within the database.
    """

    class Meta:
        abstract = True

    # Fields to be cached in ES.
    es_cached_model_fields = []

    # nonfields containing methods for custom field insertion.
    es_cached_extra_fields = []

    # Alias postfix values, used to decern write aliases from read.
    es_index_alias_read_postfix = 'read'
    es_index_alias_write_postfix = 'write'

    @classmethod
    def get_index_base_name(cls) -> str:
        """
        Retrieve the model defined index name from self.index_name defaulting
        to generated name based on app module directory and model name.
        """
        if hasattr(cls, 'index_name'):
            return cls.index_name
        else:
            return '-'.join(
                cls.__module__.lower().split('.')
                + [cls.__name__.lower()]
            )

    @classmethod
    def convert_model_field_to_es_format(cls, value):
        """
        Helper method to cast an incoming value into a format that
        is indexable within ElasticSearch. extend with your own super
        implentation if there are custom types you'd like handled differently.
        """
        if isinstance(value, Model):
            return value.pk
        elif isinstance(value, datetime) or isinstance(value, date):
            return value.strftime('%d-%M-%Y %H:%M:%S')
        elif isinstance(value, int) or isinstance(value, float):
            return value
        else:
            # Catch all try to cast value to string raising
            # an exception explicitly if that fails.
            try:
                return str(value)
            except Exception as e:
                raise UnableToCastESNominatedFieldException(e)

    def save(self, *args, **kwargs):
        """
        Override model save to index those fields nominated by
        es_cached_model_fields storring them in elasticsearch.
        """
        super().save(*args, **kwargs)

        try:
            get_es_client().index(
                id=self.pk,
                index=self.get_write_alias_name(),
                body=build_document_from_model(self),
            )
        except Exception:
            raise UnableToSaveModelToElasticSearch(
                'Attempted to save/update the {} related es document '
                'from index {}, please check your '
                'connection and status of your ES cluster.'.format(
                    str(self), self.get_index_base_name()
                )
            )

    def delete(self, *args, **kwargs):
        """
        Same as save but in reverse, remove the model instances cached
        fields in Elasticsearch.
        """
        # We temporarily cache the model pk here so we can delete the model
        # instance first before we remove from Elasticsearch.
        author_document_id = self.pk

        super().delete(*args, **kwargs)

        try:
            get_es_client().delete(
                index=self.get_write_alias_name(), id=author_document_id,
            )
        except Exception:
            # Catch failure and reraise with specific exception.
            raise UnableToDeleteModelFromElasticSearch(
                'Attempted to remove {} related es document '
                'from index {}, please check your '
                'connection and status of your ES cluster.'.format(
                    str(self), self.get_index_base_name()
                )
            )

    @staticmethod
    def get_index_mapping() -> dict:
        """
        Stub mapping of how the index should be created, override this with
        the specific implementation of what fields should be searchable
        and how.
        """
        return {'settings': {}, 'mappings': {}}

    @classmethod
    def get_read_alias_name(cls) -> str:
        """
        Generates a unique alias name using either set explicitly by
        overridding this method or in the default format of a
        combination of {index_name}-read.
        """
        return (
            cls.get_index_base_name()
            + '-' + cls.es_index_alias_read_postfix
        )

    @classmethod
    def get_write_alias_name(cls) -> str:
        """
        Generates a unique alias name using either set explicitly by
        overridding this method or in the default format of a
        combination of {index_name}-write.
        """
        return (
            cls.get_index_base_name()
            + '-' + cls.es_index_alias_write_postfix
        )

    @classmethod
    def generate_index(cls) -> str:
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
    def bind_alias(cls, index: str, alias: str):
        """
        Connect an alias to a specified index by default removes alias
        from any other indices if present.
        """
        old_indicy_names = []
        if get_es_client().indices.exists_alias(name=alias):
            old_indicy_names = get_index_names_from_alias(alias)

        alias_updates = [
            {'remove': {'index': indicy, 'alias': alias}}
            for indicy in old_indicy_names
        ]
        alias_updates.append({'add': {'index': index, 'alias': alias}})

        get_es_client().indices.update_aliases(body={'actions': alias_updates})

    @classmethod
    def rebuild_es_index(cls, queryset=None, drop_old_index=True):
        """
        Rebuilds the entire ESIndex for the model, utilizes Aliases to
        preserve access to the old index while the new is being built.

        By default will rebuild the entire database table in Elasticsearch,
        define a queryset to only rebuild a slice of this.

        Set drop_old_index to False if you want to preserve the old index for
        future use, this will no longer have the aliases tied to it but will
        still be accessable through the Elasticsearch API.
        """
        old_indicy = get_index_names_from_alias(cls.get_read_alias_name())[0]
        new_indicy = cls.generate_index()

        cls.bind_alias(new_indicy, cls.get_write_alias_name())

        chunked_qs_generator = queryset_iterator(queryset or cls.objects.all())

        for qs_chunk in chunked_qs_generator:
            qs_chunk.reindex_into_es()

        cls.bind_alias(new_indicy, cls.get_read_alias_name())

        if drop_old_index:
            get_es_client().indices.delete(old_indicy)

    def retrive_es_fields(self, only_include_fields=True):
        """
        Returns the currently indexed fields within ES for the model.
        """
        try:
            results = get_es_client().get(
                id=self.pk, index=self.get_read_alias_name(),
            )
        except NotFoundError:
            raise ElasticSearchFailure(
                f'Model {repr(self)} is not found in '
                f'{self.get_index_base_name()}, model requires '
                f'indexing to retrieve fields back.'
            )

        if only_include_fields:
            return results['_source']

        return results
