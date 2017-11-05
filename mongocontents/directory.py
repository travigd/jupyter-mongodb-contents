from collections import namedtuple
from typing import List, NamedTuple
from .connection import Connection


Subdirectory = namedtuple('Subdirectory', ['id', 'name'])
File = namedtuple('File', ['id', 'name'])


class Directory:
    """Model representing a logical directory."""

    """path: logical filesystem  path"""
    path: str

    """subdirectories: list of Subdirectory namedtuple's"""
    subdirectories: List[Subdirectory]

    """files: list of File namedtuple's"""
    files: List[File]

    # class attributes

    def __init__(self, path, parent):
        super().__init__()

    @classmethod
    def load(cls, path):
        connection: Connection = Connection.instance()
        result = connection.directories.find_one({'path': path})
