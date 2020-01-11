from django.db.models import QuerySet

from django_elasticsearch_model_binder.mixins import ESQuerySetMixin


class ESEnabledQuerySet(ESQuerySetMixin, QuerySet):
    """
    Stub manager with Elasticsearch enhanced operations.
    """
    pass
