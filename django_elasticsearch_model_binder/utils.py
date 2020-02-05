from typing import Dict, List, Any

from django.conf import settings
from django.core.exceptions import (
    ImproperlyConfigured, ObjectDoesNotExist, FieldError,
)
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import NotFoundError

from django_elasticsearch_model_binder.exceptions import (
    NominatedFieldDoesNotExistForESIndexingException,
)


def get_es_client():
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


def queryset_iterator(queryset, chunk_size=1000):
    """
    Break passed in queryset down to an iterator containing
    subquerysets ordered by pk. useful when needing to load a full table
    into memory sequentially, note because of the ordering via pk any defined
    ordering will be ignored.
    """
    try:
        last_pk = queryset.order_by('-pk')[:1].get().pk
    except ObjectDoesNotExist:
        return

    pk = 0
    queryset = queryset.order_by('pk')
    while pk < last_pk:
        queryset_chunk = queryset.filter(pk__gt=pk)[:chunk_size]
        pk = queryset_chunk[len(queryset_chunk) - 1].pk
        yield queryset_chunk


def initialize_es_model_index(model):
    """
    Taking a model utilizing the ESBoundModel, generate the
    default index and aliases into Elasticsearch, this is useful on first
    bootup of a new environment so a model has everything it needs to begin
    piping data to Elasticsearch.

    NOTE: This will just create the corresponging index/aliases there will be
    no data present in these indexes, call rebuild_index on the model to begin
    setting up the models data in Elasticsearch.
    """
    try:
        get_index_names_from_alias(model.get_write_alias_name())
    except NotFoundError:
        # Only create a new index when we can't find a alias -> index
        # relationship for this model.
        new_indicy = model.generate_index()
        model.bind_alias(new_indicy, model.get_write_alias_name())
        model.bind_alias(new_indicy, model.get_read_alias_name())


def build_documents_from_queryset(queryset) -> Dict[int, dict]:
    """
    Generate a dictionary map of ES fields representing the
    nominated model fields to be cached in the model index.
    """
    try:
        field_list = queryset.model.es_cached_model_fields
        if 'pk' not in field_list:
            field_list.append('pk')
        queryset_values = queryset.values(*field_list)
    except FieldError:
        raise NominatedFieldDoesNotExistForESIndexingException(
            'One of the fields defined in es_cached_model_fields does '
            'not exist on the model {} only '
            'valid fields can be indexed with es_cached_model_fields, for any '
            'extra fields look at es_cached_extra_fields for inclusion into '
            'this index'.format(queryset.model.__class__.__name__)
        )

    documents = {
        model_values['pk']: {'_id': model_values['pk'], '_source': {}}
        for model_values in queryset_values
    }

    # Generate nominated fields for document inclusion off model.
    for model_values in queryset_values:
        documents[model_values['pk']]['_source'] = {
            k: queryset.model.convert_model_field_to_es_format(v)
            for k, v in model_values.items()
        }

    # Generate and bulk resolve custom fields for document.
    for field_class in queryset.model.es_cached_extra_fields:
        extra_field_class = field_class(queryset.model)
        custom_field_values = (
            extra_field_class.custom_model_field_map(documents.keys())
        )

        for pk in documents.keys():
            field_name = extra_field_class.get_custom_field_name()
            documents[pk]['_source'].update({
                field_name: custom_field_values[pk]
            })

    return documents


def build_document_from_model(model) -> dict:
    """
    Build ES cached fields for individual model
    returning built document for indexing.
    """
    document = {}
    model_fields = [f.name for f in model._meta.fields]

    # Generate index fields based on defined model fields.
    for field in model.es_cached_model_fields:
        if field not in model_fields and field != 'pk':
            raise NominatedFieldDoesNotExistForESIndexingException(
                'field {} does not exist on model '
                '{} only valid model fields can be '
                'indexed. For any extra fields look at es_cached_extra_fields '
                'for inclusion into this index'.format(
                    field, model.__class__.__name__
                )
            )

        document[field] = model.convert_model_field_to_es_format(
            getattr(model, field)
        )

    # Generate any custom fields not present on the model,
    # combining with those nominated on the model.
    for field_class in model.es_cached_extra_fields:
        extra_field_class = field_class(model)
        custom_field_value = (
            extra_field_class.custom_model_field_map([model.pk])[model.pk]
        )
        document[extra_field_class.get_custom_field_name()] = custom_field_value

    return document


def get_index_names_from_alias(alias: str) -> List[str]:
    """
    Return list of indices tied to a alias
    """
    old_indicy_names = (
        get_es_client()
        .indices.get_alias(name=alias)
        .keys()
    )

    return [indicy for indicy in old_indicy_names]


class ExtraModelFieldBase:
    """
    Base contract class to allow extra fields not present on the model to be
    indexed.
    """
    def __init__(self, model):
        self.model = model

    @classmethod
    def custom_model_field_map(cls, model_pks: List[int]) -> Dict[int, Any]:
        """
        Method to bulk generate custom field values for Elasticsearch model
        indexing. Taking a list of model pks override this method returning a
        dictionary containing the model pk as key and the value you want
        attributed per model, on model indexing this will be included in the
        index along with the other nominated model field values.
        """
        raise NotImplementedError(
            'Field requires implementation to include into '
            'related model index.'
        )

    @classmethod
    def get_custom_field_name(cls) -> str:
        if not hasattr(cls, 'field_name'):
            raise NotImplementedError(
                'Custom field_name must be set to map to map to model index.'
            )

        return cls.field_name
