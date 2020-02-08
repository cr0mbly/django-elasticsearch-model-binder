import os
from setuptools import setup, find_packages

README = open(os.path.join(os.path.dirname(__file__), 'README.rst')).read()

setup(
    name='django-elasticsearch-model-binder',
    version='0.1.1',
    packages=find_packages(
        include=('django_elasticsearch_model_binder',), exclude=('tests',)
    ),
    license='MIT License',
    long_description=README,
    description=(),
    install_requires=[
        'django',
        'elasticsearch',
    ],
    url='https://github.com/cr0mbly/django-elasticsearch-model-binder',
    author='Aidan Houlihan',
    author_email='aidandhoulihan@gmail.com',
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content'
    ]
)
