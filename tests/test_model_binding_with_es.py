from time import sleep

from django.test import TestCase
from elasticsearch.exceptions import NotFoundError

from django_elasticsearch_model_binder.utils import (
    get_es_client, initialize_es_model_index, get_index_names_from_alias,
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


class TestElasticSearchAliasAndIndexGeneration(ElasticSearchBaseTest):
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

    def test_rebuild_optionally_drops_old_index(self):
        Author.rebuild_es_index()

        old_index = get_index_names_from_alias(
            Author.get_read_alias_name()
        )[0]

        Author.rebuild_es_index()

        # Assert that rebuilding the full index wipes
        # the old index on completion.
        with self.assertRaises(NotFoundError):
            get_es_client().indices.get(old_index)

        updated_old_index = get_index_names_from_alias(
            Author.get_read_alias_name()
        )[0]

        Author.rebuild_es_index(drop_old_index=False)

        updated_old_es_index_data = get_es_client().indices.get(
            updated_old_index
        )
        latest_index = get_index_names_from_alias(
            Author.get_read_alias_name()
        )[0]

        # Assert that a full index rebuild with drop_old_index disabled keeps
        # the original index, while transfering over the aliases.
        self.assertIsNotNone(updated_old_es_index_data)
        self.assertNotEqual(updated_old_index, latest_index)


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

    def test_custom_fields_can_be_indexed(self):
        es_data = get_es_client().get(
            id=self.user.pk, index=User.get_read_alias_name(),
        )
        unique_identifer = es_data['_source']['unique_identifer']
        # Assert a save event includes custom field values
        self.assertIsNotNone(unique_identifer)

        User.objects.filter(pk=self.user.pk).reindex_into_es()
        updated_es_data = get_es_client().get(
            id=self.user.pk, index=User.get_read_alias_name(),
        )

        # Assert a full queryset rebuild will re-index custom fields.
        self.assertIsNotNone(updated_es_data['_source']['unique_identifer'])
        self.assertNotEqual(
            unique_identifer, updated_es_data['_source']['unique_identifer'],
        )

    def test_retrieving_values_for_model(self):
        author = Author.objects.create(
            publishing_name=self.publishing_name,
            age=4, user=self.user,
        )

        document = author.retrive_es_fields()

        self.assertDictEqual(
            {'publishing_name': self.publishing_name, 'user': author.user.pk},
            document
        )


class TestModelESQuerySetMixin(ElasticSearchBaseTest):
    def setUp(self):
        super().setUp()

        # Generate shared data.
        self.publishing_name = 'Bill Fakeington'
        self.user = User.objects.create(email='test@gmail.com')

    def test_model_manager_bulk_reindexer(self):
        author = Author.objects.create(
            publishing_name=self.publishing_name,
            age=3, user=self.user,
        )
        new_publishing_name = 'Bill Fakeington 2'
        filtered_queryset = Author.objects.filter(pk=author.pk)
        filtered_queryset.update(publishing_name=new_publishing_name)

        es_data = get_es_client().get(
            id=author.pk, index=Author.get_read_alias_name(),
        )
        self.assertEqual(
            self.publishing_name, es_data['_source']['publishing_name'],
        )

        filtered_queryset.reindex_into_es()

        updated_es = get_es_client().get(
            id=author.pk, index=Author.get_read_alias_name(),
        )

        self.assertEqual(
            new_publishing_name, updated_es['_source']['publishing_name'],
        )

    def test_filter_by_es_search(self):
        author_1 = Author.objects.create(
            publishing_name='Billy Fakington',
            age=4, user=self.user,
        )

        author_2 = Author.objects.create(
            publishing_name='Bobby Fakington',
            age=4, user=self.user,
        )

        author_3 = Author.objects.create(
            publishing_name='Billy not-realington',
            age=4, user=self.user,
        )

        # We impose a sleep in here as Elasticsearch doesn't have
        # enough time in the test to index by the time the query
        # is preformed.
        sleep(1)

        queryset = Author.objects.filter_by_es_search(
            query={
                'match': {
                    'publishing_name': 'Bobby*'
                }
            }
        )

        self.assertNotIn(author_1, queryset)
        self.assertIn(author_2, queryset)
        self.assertNotIn(author_3, queryset)

    def test_model_manager_bulk_deletion(self):
        author = Author.objects.create(
            publishing_name=self.publishing_name,
            age=4, user=self.user,
        )

        filtered_queryset = Author.objects.filter(pk=author.pk)

        es_data = get_es_client().get(
            id=author.pk, index=Author.get_read_alias_name(),
        )
        self.assertEqual(
            self.publishing_name, es_data['_source']['publishing_name'],
        )

        filtered_queryset.delete_from_es()

        with self.assertRaises(NotFoundError):
            get_es_client().get(
                id=author.pk, index=Author.get_read_alias_name(),
            )

    def test_full_index_rebuild(self):
        author = Author.objects.create(
            publishing_name='Billy Fakington',
            age=4, user=self.user,
        )

        # Clear and preform a full ES rebuild. Ignores setUp
        # so we can start fresh.
        Author.rebuild_es_index()

        alternative_author = Author.objects.create(
            publishing_name=self.publishing_name,
            age=4, user=self.user,
        )

        author_1_es_data = get_es_client().get(
            id=author.pk, index=Author.get_read_alias_name(),
        )

        author_2_es_data = get_es_client().get(
            id=alternative_author.pk, index=Author.get_read_alias_name(),
        )

        # Assert that full table is in the indexed
        # and all model data is available.
        self.assertEqual(author.pk, int(author_1_es_data['_id']))
        self.assertEqual(
            alternative_author.pk, int(author_2_es_data['_id']),
        )

    def test_filter_by_es_query_supports_sorting(self):
        author_1 = Author.objects.create(
            publishing_name='Billy Fakington',
            age=4, user=self.user,
        )

        author_2 = Author.objects.create(
            publishing_name='Billy Billyson',
            age=4, user=self.user,
        )

        author_3 = Author.objects.create(
            publishing_name='Bill not-realington',
            age=4, user=self.user,
        )

        sleep(1)

        queryset_pks = list(
            Author.objects
            .filter_by_es_search(
                query={'prefix': {'publishing_name.keyword': 'Bill'}},
                sort_query=[{
                    'publishing_name.keyword': {
                        'order': 'asc', 'missing': '_last'
                    }
                }]
            )
            .values_list('pk', flat=True)
        )

        self.assertEqual([author_3.pk, author_2.pk, author_1.pk], queryset_pks)

        queryset_pks = list(
            Author.objects
            .filter_by_es_search(
                query={'prefix': {'publishing_name.keyword': 'Bill'}},
                sort_query=[{
                    'publishing_name.keyword': {
                        'order': 'desc', 'missing': '_last'
                    }
                }]
            )
            .values_list('pk', flat=True)
        )

        self.assertEqual([author_1.pk, author_2.pk, author_3.pk], queryset_pks)

    def test_retrieve_multiple_model_fields(self):
        author_1 = Author.objects.create(
            publishing_name='Billy Fakington',
            age=4, user=self.user,
        )

        author_2 = Author.objects.create(
            publishing_name='Billy Billyson',
            age=4, user=self.user,
        )

        sleep(1)

        field_only_documents = Author.objects.retrieve_es_docs()

        self.assertEqual(
            [
                {
                    'pk': author_2.pk,
                    'publishing_name': author_2.publishing_name,
                    'user': author_2.user.pk
                },
                {
                    'pk': author_1.pk,
                    'publishing_name': author_1.publishing_name,
                    'user': author_1.user.pk
                }
            ],
            field_only_documents
        )
