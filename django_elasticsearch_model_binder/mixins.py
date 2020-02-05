from elasticsearch.helpers import bulk

from django_elasticsearch_model_binder.exceptions import (
    UnableToBulkIndexModelsToElasticSearch,
)
from django_elasticsearch_model_binder.utils import (
    build_documents_from_queryset, get_es_client,
)


class ESQuerySetMixin:
    """
    Mixin for providing Elasticsearch bulk indexing
    implementation to querysets.
    """

    def reindex_into_es(self):
        """
        Generate and bulk re-index all nominated fields into elasticsearch
        """
        try:
            bulk(
                get_es_client(), build_documents_from_queryset(self).values(),
                index=self.model.get_write_alias_name(),
                doc_type='_doc',
            )
        except Exception as e:
            raise UnableToBulkIndexModelsToElasticSearch(e)

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
            doc_type='_doc'
        )
