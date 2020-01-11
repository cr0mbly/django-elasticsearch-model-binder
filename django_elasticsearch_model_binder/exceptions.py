class NominatedFieldDoesNotExistForESIndexingException(Exception):
    pass


class ElasticSearchFailure(Exception):
    pass


class UnableToDeleteModelFromElasticSearch(ElasticSearchFailure):
    pass


class UnableToSaveModelToElasticSearch(ElasticSearchFailure):
    pass


class UnableToCastESNominatedFieldException(ElasticSearchFailure):
    pass


class UnableToBulkIndexModelsToElasticSearch(Exception):
    pass
