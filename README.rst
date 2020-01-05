=================================
Django Elasticsearch Model Binder
=================================

Plugin for a Django/Elasticsearch environment that tries to align CRUD
operations within Django with the related indexes that are tied to the models
that they build.


**Setup**

This intro assumes you have a installed version of both Django and
Elasticsearch on your machine. The expected configuration for setup within
django-elasticsearch-model-builder is within your settings for example:

*setup.py*

.. code-block:: python

    DJANGO_ES_MODEL_CONFIG = {
        'hosts': [{'host': 'localhost', 'port': 9200}]
    }

This is example is fairly basic but follows the expected format for inclusion
into the Elasticsearch libraries instantiated kwargs so anything you place in
these settings will be fed straight in, this helps with more complicated
Elasticsearch setups with encryption and multiple clusters running off
different hosts.


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
        es_cached_fields = ['publishing_name', 'user']

**Setting index name.**

This example is fairly basic it will create an Elasticsearch index generated
with an index name comprised of the model class name and
its module path directory. this can be overridden by setting the
`index_name` field in the model:

.. code-block:: python

    class Author(ESModelBinderMixin, models.Model):
        index_name ='my-custom-index-name'

**Saving db model into Elasticsearch**

This plugin works with a principle that fields should ready to be serialized
into Elasticsearch things like *sets* for instance will fail if you try return
them and index them into Elasticsearch. By default this plugin casts the
following base types to Elasticsearch compatible values.

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

**Removing db model into Elasticsearch**

Removing a model in ElasticSearch happens automatically on model deletion
these are bound events. This plugin keeps a reference to the current index and
model pk as identifer and on `.save()` executes a request to ElasticSearch to
purge it of that models data.
