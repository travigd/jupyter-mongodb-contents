
from notebook.services.contents.tests.test_contents_api import APITest
from traitlets.config import Config
from mongocontents.mongocontents import MongoContents


def mongocontents_config():
    """
    Shared setup code for MongoContents
    """
    config = Config()
    config.NotebookApp.contents_manager_class = MongoContents
    return config


class MongoContentsTest(APITest):

    notebook_dir = '/nonexistant'

