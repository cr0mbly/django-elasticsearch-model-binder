from unittest.mock import patch

from django.test import TestCase

from .test_app.models import Author, User

class TestModelMaintainsStateAcrossDBandES(TestCase):

    def test_nominated_fields_are_saved_in_es(self):
        publishing_name = 'Bill Fakeington'
        user = User.objects.create(email='test@gmail.com')
        author = Author.objects.create(
            publishing_name=publishing_name,
            age=3, user=user,
        )

        es_data = Author.get_es_client().get(
            id=author.pk,
            index=Author.get_index_name(),
            doc_type=Author.__name__,
        )

        self.assertEqual(author.pk, es_data['_id'])
        self.assertEqual(user.pk, es_data['_source']['user'])
        self.assertEqual(publishing_name, es_data['_source']['publishing_name'])
        self.assertTrue(es_data['found'])
