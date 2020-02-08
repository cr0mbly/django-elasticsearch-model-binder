from django.db.models import Case, When
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

    def filter_by_es_search(self, query, sort_query={}):
        """
        Taking an ES search query return the models that are
        resolved by the search.

        Queryset ordering can be denoted by setting sort_query, otherwise
        sorting will be determined by set model ordering.
        """
        results = get_es_client().search(
            _source=False,
            index=self.model.get_read_alias_name(),
            body={
                'query': query,
                'sort': sort_query,
            }
        )

        model_pks = [d['_id'] for d in results['hits']['hits']]

        # Force query to return in the order set by the sort_query
        if sort_query:
            preserved_pk_order = Case(
                *[When(pk=pk, then=pos) for pos, pk in enumerate(model_pks)]
            )
            return self.filter(pk__in=model_pks).order_by(preserved_pk_order)

        return self.filter(pk__in=model_pks)

    def retrieve_es_docs(self, only_include_fields=True):
        """
        Retrieve all ES Cached fields for the queryset. Set
        only_include_source=False to return verbose response
        from ElasticSearch.
        """
        results = get_es_client().search(
            index=self.model.get_read_alias_name(),
            body={
                'query': {
                    'ids': {'values': list(self.values_list('pk', flat=True))}
                }
            }
        )

        if only_include_fields:
            return [
                doc['_source']
                for doc in results['hits']['hits']
            ]

        return results
