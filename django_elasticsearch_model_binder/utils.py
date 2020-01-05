from gc import collect

from django.core.exceptions import ObjectDoesNotExist


def queryset_iterator(queryset, chunk_size=1000):
    """
    Break passed in queryset down to an iterator containing
    subquerysets ordered by pk. useful when needing to load a full table
    into memory sequentially, note because of the ordering via pk any defined
    ordering will be ignored.
    Taken from https://gist.github.com/syrusakbary/7982653#gistcomment-2038879
    """
    try:
        last_pk = queryset.order_by('-pk')[:1].get().pk
    except ObjectDoesNotExist:
        return

    pk = 0
    queryset = queryset.order_by('pk')
    while pk < last_pk:
        for row in queryset.filter(pk__gt=pk)[:chunk_size]:
            pk = row.pk
            yield row
        collect()
