from django.test import TestCase
from elasticsearch.exceptions import NotFoundError

from django_elasticsearch_model_binder.utils import (
    get_es_client, initialize_es_model_index
)
from tests.test_app.models import Author, User


class ElasticSearchBaseTest(TestCase):
    def setUp(self):
        """
        Instantiate base ES config, generates model index and aliases.
        """
        initialize_es_model_index(Author)
        initialize_es_model_index(User)

    def tearDown(self):
        """
        Clear build indices between tests, allows for
        side affect free testing.
        """
        get_es_client().indices.delete('*')


class TestElasticSearchAliasGeneration(ElasticSearchBaseTest):
    def test_alias_binding_to_model(self):
        # Override setUp ES setup.
        get_es_client().indices.delete('*')

        new_index = Author.generate_index()
        read_alias_name = Author.get_read_alias_name()

        self.assertFalse(
            get_es_client().indices
            .exists_alias(index=new_index, name=read_alias_name)
        )

        Author.bind_alias(index=new_index, alias=read_alias_name)

        self.assertTrue(
            get_es_client().indices
            .exists_alias(index=new_index, name=read_alias_name)
        )


class TestModelMaintainsStateAcrossDBandES(ElasticSearchBaseTest):
    def setUp(self):
        super().setUp()

        # Generate shared data.
        self.publishing_name = 'Bill Fakeington'
        self.user = User.objects.create(email='test@gmail.com')
        self.author = Author.objects.create(
            publishing_name=self.publishing_name,
            age=3, user=self.user,
        )

    def test_nominated_fields_are_saved_in_es(self):
        es_data = get_es_client().get(
            id=self.author.pk, index=Author.get_read_alias_name(),
        )

        self.assertEqual(str(self.author.pk), es_data['_id'])
        self.assertEqual(self.user.pk, es_data['_source']['user'])
        self.assertEqual(
            self.publishing_name, es_data['_source']['publishing_name'],
        )
        self.assertTrue(es_data['found'])

    def test_es_instance_is_removed_on_model_delete(self):
        author_doc_id = self.author.pk

        es_data = get_es_client().get(
            id=self.author.pk, index=Author.get_read_alias_name(),
        )

        self.assertEqual(str(author_doc_id), es_data['_id'])

        self.author.delete()
        with self.assertRaises(NotFoundError):
            get_es_client().get(
                id=author_doc_id, index=Author.get_read_alias_name(),
            )

    def test_model_manager_bulk_reindexer(self):
        new_publishing_name = 'Bill Fakeington 2'
        filtered_queryset = Author.objects.filter(pk=1)
        filtered_queryset.update(publishing_name=new_publishing_name)

        es_data = get_es_client().get(
            id=self.author.pk, index=Author.get_read_alias_name(),
        )
        self.assertEqual(
            self.publishing_name, es_data['_source']['publishing_name'],
        )

        filtered_queryset.reindex_into_es()

        updated_es = get_es_client().get(
            id=self.author.pk, index=Author.get_read_alias_name(),
        )

        self.assertEqual(
            new_publishing_name, updated_es['_source']['publishing_name'],
        )

    def test_model_manager_bulk_deletion(self):
        filtered_queryset = Author.objects.filter(pk=1)

        es_data = get_es_client().get(
            id=self.author.pk, index=Author.get_read_alias_name(),
        )
        self.assertEqual(
            self.publishing_name, es_data['_source']['publishing_name'],
        )

        filtered_queryset.delete_from_es()

        with self.assertRaises(NotFoundError):
            get_es_client().get(
                id=self.author.pk, index=Author.get_read_alias_name(),
            )

    def test_full_index_rebuild(self):
        alternative_author = Author.objects.create(
            publishing_name=self.publishing_name,
            age=4, user=self.user,
        )

        # Clear and preform a full ES rebuild. Ignores setUp
        # so we can start fresh.
        get_es_client().indices.delete('*')
        Author.rebuild_es_index()

        author_1_es_data = get_es_client().get(
            id=self.author.pk, index=Author.get_read_alias_name(),
        )

        author_2_es_data = get_es_client().get(
            id=alternative_author.pk, index=Author.get_read_alias_name(),
        )

        # Assert that full table is in the indexed
        # and all model data is available.
        self.assertEqual(self.author.pk, int(author_1_es_data['_id']))
        self.assertEqual(
            alternative_author.pk, int(author_2_es_data['_id']),
        )

    def test_custom_fields_can_be_indexed(self):
        es_data = get_es_client().get(
            id=self.user.pk, index=User.get_read_alias_name(),
        )
        self.assertIsNotNone(es_data['_source']['unique_identifer'])
