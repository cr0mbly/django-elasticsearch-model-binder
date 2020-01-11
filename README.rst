=================================
Django Elasticsearch Model Binder
=================================

Plugin for a Django/Elasticsearch paired environment that aligns CRUD
operations within Django with the related indexes that are tied to the models
that they build.


**Setup**

This intro assumes you have an installed version of both Django and
Elasticsearch on your machine. The expected configuration for setup within
django-elasticsearch-model-builder is within your settings for example:

*setup.py*

.. code-block:: python

    DJANGO_ES_MODEL_CONFIG = {
        'hosts': [{'host': 'localhost', 'port': 9200}]
    }

This example is fairly basic but follows the expected format for configuration
of the Elasticsearch client built into this plugin  so anything you place in
this settings dictionary will be fed straight in, this helps with more
complicated Elasticsearch setups with encryption and multiple clusters
running off different hosts.


**Tieing models to indexes.**

Tieing a model to an elasticsearch index can be done on the fly by adding
the mixin

.. code-block:: python

    class Author(ESModelBinderMixin, models.Model):
        user = models.ForeignKey(
            User, on_delete=models.CASCADE
        )
        publishing_name = models.CharField(
            max_length=25, blank=True, null=True
        )

        # Fields to be picked up and cached in model
        es_cached_model_fields = ['publishing_name', 'user']

**Setting index name.**

This example is fairly basic it will create an Elasticsearch index generated
with an index name comprised of the model class name and
its module path directory. this can be overridden by setting the
`index_name` field in the model:

.. code-block:: python

    class Author(ESModelBinderMixin, models.Model):
        index_name ='my-custom-index-name'

or overriding the `get_index_base_name` method, by default the index will be
generated with a name reflecting the modules path and model name e.g.

.. code-block:: python

  <module-path>-<model-name>-<unique-uuid>

**Default Aliases**

By default this plugin generates the index on first start of the app if it
hasn't been defined. It also generates a default read/write alias that
allows indexes to be rebuilt on the fly with no downtime for your app.

Aliases utilise the same index name as their parent but are postfixed by
default with a `-read`/`-write` to help differentiate from the main index. you
can override this on the model by defining your own postfix, e.g.

.. code-block:: python

    class Author(ESModelBinderMixin, models.Model):
        index_name ='my-custom-index-name'

        es_index_alias_read_postfix = 'read-only-access'
        es_index_alias_write_postfix = 'write-only-access'


Will generate aliases in the format of:

- my-custom-index-name-read-only-access
- my-custom-index-name-write-only-access

Or define your own way by overriding the default
`get_read_alias_name`/`get_write_alias_name`

**Casting db model fields into Elasticsearch format**

This plugin works with a principle that fields should be ready to be serialized
into Elasticsearch data structures like `sets` for instance will fail if you
try to index them into Elasticsearch. By default this plugin casts
the following base types to Elasticsearch compatible values.

- models.Model -> integer containing the models pk
- datetime.datetime ->  string in the format 'YYYY-MM-DD HH:MM:SS'
- all other values -> str(value) (attempt to cast all other values)


If this mapping doesn't suit you or you wish to extend it you can do so
by overriding the `convert_to_indexable_format` method on the mixin.

.. code-block:: python

    class Author(ESModelBinderMixin, models.Model):

        def convert_to_indexable_format(self, value):
            if isinstance(value, float):
                # Round value for uniform integer value
                return round(value)

            # ... any further field rules

**Saving/Removing db model in Elasticsearch**

Saving and removing a model in ElasticSearch happens automatically on
`.save`/ `.delete` operations. This should be noted as any
`bulk_create`/`bulk_update` will ignore this and you'll need to manage these
cases within your business logic of the app. See below for how to do these
operations in bulk where this is a requirement of the business case.


**Preforming bulk operations**

This plugin also supports a handy set of calls that can be tied into a
query manager to bulk create/update/delete these models in Elasticsearch.

To enable this you'll need to add the plugins query manager mixin to your
model, for example.

.. code-block:: python

    from django.db.models import QuerySet

    from django_elasticsearch_model_binder.mixins import ESQuerySetMixin


    class ESEnabledQuerySet(ESQuerySetMixin, QuerySet):
        pass

    class Author(ESModelBinderMixin, models.Model):
        index_name ='my-custom-index-name'

        es_index_alias_read_postfix = 'read-only-access'
        es_index_alias_write_postfix = 'write-only-access'

        objects = ESEnabledQuerySet.as_manager()


You can then define a query via the manager targeting the models you want
to update, delete from Elasticsearch e.g.


.. code-block:: python

    # Re-save models with selected fields into Elasticsearch
    Author.objects.filter(pk__lt=100).reindex_into_es()

    # Delete models with selected fields into Elasticsearch
    Author.objects.filter(pk__lt=100).delete_from_es()


**Rebuilding an entire table in Elasticsearch**

At times you may want to throw away your current index and replace
it with a new one. For larger data-sets this can be problematic as downtime
while this rebuilds is unacceptable. This plugin exposes a simple method to
preform a complete refresh of the index from either the entire models table or
from a slice of the table defined by a queryset. This will automatically create
a new index and point the write alias to it while allowing the old index to be
used with the read alias for your app until the rebuild is finished,
resulting in no index downtime.

This can be run from shell or any kind of automated task by running:

.. code-block:: python

    # Full table rebuild of the Author model.
    >>> Author.rebuild_es_index()

    # Full table rebuild of the Author model.
    >>> sliced_queryset = Author.objects.filter(pk__lt=100)
    >>> Author.rebuild_es_index(queryset=sliced_queryset)
