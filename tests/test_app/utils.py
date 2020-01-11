from uuid import uuid4

from django_elasticsearch_model_binder import ExtraModelFieldBase


class UniqueIdentiferField(ExtraModelFieldBase):

    field_name = 'unique_identifer'

    @classmethod
    def custom_model_field_map(cls, model_pks):
        """
        Custom Elasticsearch field attached to model document, attributes each
        document with a unique_identifer uuid in Elasticsearch.
        """
        return {pk: uuid4().hex for pk in model_pks}
