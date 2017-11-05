from pymongo import MongoClient
from pymongo.database import Database as MongoDatabase
from pymongo.collection import Collection as MongoCollection
from gridfs import GridFS
from traitlets.config import SingletonConfigurable


class Connection(SingletonConfigurable):
    """Connection instance."""

    client: MongoClient
    database: MongoDatabase
    directories: MongoCollection
    files: GridFS

    def __init__(self, parent=None, **kwargs):
        if parent is None:
            raise ValueError("missing required keyword argument: parent")
        super().__init__(**kwargs)
        self.create_indices()

    def create_indices(self):
        self.directories.create_index('path', unique=True)
