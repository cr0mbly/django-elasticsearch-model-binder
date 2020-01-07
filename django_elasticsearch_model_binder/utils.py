from gc import collect

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ObjectDoesNotExist
from elasticsearch import Elasticsearch


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
    Taken from https://gist.github.com/syrusakbary/7982653#gistcomment-2038879
    """
    try:
        last_pk = queryset.order_by('-pk')[:1].get().pk
    except ObjectDoesNotExist:
        return

    pk = 0
    queryset = queryset.order_by('pk')
    while pk < last_pk:
        for row in queryset.filter(pk__gt=pk)[:chunk_size]:
            pk = row.pk
            yield row
        collect()


def initialize_es_model_index(model):
    """
    Taking a model utilizing the ESModelBinderMixin mixin, generate the
    default index and aliases into Elasticsearch, this is useful on first
    bootup of a new environment so a model has everything it needs to begin
    piping data to Elasticsearch.

    NOTE: This will just create the corresponging index/aliases there will be
    no data present in these indexes, call rebuild_index on the model to begin
    setting up the models data in Elasticsearch.
    """
    new_indicy = model.generate_index()
    model.bind_alias(new_indicy, model.get_write_alias_name())
    model.bind_alias(new_indicy, model.get_read_alias_name())
