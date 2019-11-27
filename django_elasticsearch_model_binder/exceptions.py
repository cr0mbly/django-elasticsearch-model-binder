class NominatedFieldDoesNotExistForESIndexingException(Exception):
    pass

class UnableToCastESNominatedFieldToStringException(Exception):
    pass

class ElasticSearchFailure(Exception):
    pass

class UnableToDeleteModelFromElasticSearch(ElasticSearchFailure):
    pass

class UnableToSaveModelToElasticSearch(ElasticSearchFailure):
    pass

class UnableToBulkIndexModelsToElasticSearch(ElasticSearchFailure):
    pass
