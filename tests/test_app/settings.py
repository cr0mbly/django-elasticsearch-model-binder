SECRET_KEY = 'super-secret-key'

INSTALLED_APPS = (
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sites',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.admin.apps.SimpleAdminConfig',
    'django.contrib.staticfiles',
    'tests.test_app',
)

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'sqlite3.db',
        'USER': '',
        'PASSWORD': '',
        'HOST': '',
        'PORT': '',
    }
}


DJANGO_ES_MODEL_CONFIG = {
    'hosts': [
        {'host': 'localhost', 'port': 9200}
    ]
}
