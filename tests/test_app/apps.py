from django.apps import AppConfig


class TestAppConfig(AppConfig):
    name = 'tests.testapp'
    verbose_name = 'TestApp'

    def ready(self):
        from tests.test_app.models import Author
        from django_elasticsearch_model_binder.utils import (
            initialize_es_model_index
        )
        initialize_es_model_index(Author)
