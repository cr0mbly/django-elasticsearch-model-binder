from unittest.mock import patch

from elasticsearch.exceptions import NotFoundError
from django.test import TestCase

from .test_app.models import Author, User

class TestModelMaintainsStateAcrossDBandES(TestCase):

    def setUp(self):
        self.publishing_name = 'Bill Fakeington'
        self.user = User.objects.create(email='test@gmail.com')
        self.author = Author.objects.create(
            publishing_name=self.publishing_name,
            age=3, user=self.user,
        )

    def test_nominated_fields_are_saved_in_es(self):
        es_data = Author.get_es_client().get(
            id=self.author.pk,
            index=Author.get_index_name(),
            doc_type=Author.__name__,
        )

        self.assertEqual(str(self.author.pk), es_data['_id'])
        self.assertEqual(self.user.pk, es_data['_source']['user'])
        self.assertEqual(self.publishing_name, es_data['_source']['publishing_name'])
        self.assertTrue(es_data['found'])

    def test_es_instance_is_removed_on_model_delete(self):
        self.author.delete()
        with self.assertRaises(NotFoundError):
            es_data = Author.get_es_client().get(
                id=self.author.pk,
                index=Author.get_index_name(),
                doc_type=Author.__name__,
            )

    def test_model_manager_bulk_reindexer(self):
        new_publishing_name = 'Bill Fakeington 2'
        filtered_queryset = Author.objects.filter(pk=1)
        filtered_queryset.update(publishing_name=new_publishing_name)

        es_data = Author.get_es_client().get(
            id=self.author.pk,
            index=Author.get_index_name(),
            doc_type=Author.__name__,
        )
        self.assertEqual(
            self.publishing_name, es_data['_source']['publishing_name'],
        )

        filtered_queryset.reindex_into_es()

        updated_es = Author.get_es_client().get(
            id=self.author.pk,
            index=Author.get_index_name(),
            doc_type=Author.__name__,
        )
        self.assertEqual(
            new_publishing_name, updated_es['_source']['publishing_name'],
        )


    def test_model_manager_bulk_deletion(self):
        new_publishing_name = 'Bill Fakeington 2'
        filtered_queryset = Author.objects.filter(pk=1)

        es_data = Author.get_es_client().get(
            id=self.author.pk,
            index=Author.get_index_name(),
            doc_type=Author.__name__,
        )
        self.assertEqual(
            self.publishing_name, es_data['_source']['publishing_name'],
        )

        filtered_queryset.delete_from_es()

        with self.assertRaises(NotFoundError):
            Author.get_es_client().get(
                id=self.author.pk,
                index=Author.get_index_name(),
                doc_type=Author.__name__,
            )
