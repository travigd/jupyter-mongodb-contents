import datetime
import json
import os.path
import re
from typing import List, Union
import nbformat
import notebook.transutils
from notebook.services.contents.manager import ContentsManager
from tornado import web
from traitlets import Unicode
from pymongo import MongoClient
from pymongo.collection import Collection as MongoCollection
from pymongo.database import Database as MongoDatabase
from pymongo.errors import DuplicateKeyError
from gridfs import GridFSBucket
from gridfs.grid_file import GridIn, GridOutCursor, GridOut

# see http://jupyter-notebook.readthedocs.io/en/latest/extending/contents.html
# for a high-level overview of entity types (much of the documentation below
# is based on, or copied verbatim from, this source)


class MongoContents(ContentsManager):

    mongodb_uri: str = Unicode(
        "mongodb://localhost:27017",
        config=True,
        help="MongoDB URI to use when connection to mongod. See "
             "https://docs.mongodb.com/manual/reference/connection-string/ "
             "for information about format.")

    database_name: str = Unicode(
        'jupyter',
        config='True',
        help="Database in which to store files.")

    directories_collection_name: str = Unicode(
        'directories',
        config=True,
        help="Collection in which directory metadata is stored.")

    files_collection_name: str = Unicode(
        'files',
        config=True,
        help="Collection in which file metadata is stored.")

    path_prefix: str = Unicode(
        '/',
        config=True,
        help="Prefix at which to serve files."
    )

    _client: MongoClient
    _database: MongoDatabase
    _directories: MongoCollection
    _files: GridFSBucket

    # regex to match valid file/directory names
    _name_regex = r'^[^\\/?%*:|"<>\.]+$'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client: MongoClient = MongoClient(self.mongodb_uri)
        self._database: MongoDatabase = self._client[self.database_name]
        self._directories: MongoCollection\
            = self._database[self.directories_collection_name]
        self._files: GridFSBucket\
            = GridFSBucket(self._database, self.files_collection_name)
        self._files_metadata: MongoCollection\
            = self._database[self.files_collection_name].files

        self._directories.create_index('path', unique=True)
        if not self.dir_exists('/'):
            self.save({'type': 'directory'}, '/')

    def normalize_path(self, path):
        return os.path.join(self.path_prefix, path)

    def denormalize_path(self, path):
        return path[len(self.path_prefix):]

    def dir_exists(self, path):
        """Does a directory exist at the given path?

        Like os.path.isdir

        Parameters
        ----------
        path : string
            The path to check

        Returns
        -------
        exists : bool
            Whether the path does indeed exist.
        """
        return self._dir_exists(self.normalize_path(path))

    def _dir_exists(self, path):
        result = self._directories.find_one({
            'path': path
        })
        if result is None:
            return False
        else:
            return True

    def is_hidden(self, path: str) -> bool:
        """Is path a hidden directory or file?

        Employs simple heuristic to exclude all files that start with . or
        __ (e.g. __pycache__).

        Parameters
        ----------
        path : string
            The path to check. This is an API path (`/` separated,
            relative to root dir).

        Returns
        -------
        hidden : bool
            Whether the path is hidden.

        """
        basename = os.path.basename(path)
        return (basename.startswith('.')
                or basename.startswith('__'))

    def _get_file_gridout(self, path, ignore_deleted=True) \
            -> Union[GridOut, None]:
        """Get the GridOut object associated with the file.

        If a deleted file is found and ignore_deleted is True, None will be
        returned.
        """
        cursor: GridOutCursor
        cursor = (self._files
                  .find({'filename': path})
                  .sort('uploadDate', -1)
                  .limit(1))
        if cursor.count() == 0:
            return None
        file: GridOut = list(cursor)[0]
        metadata: dict = file.metadata
        if (ignore_deleted and 'deleted' in metadata
                and metadata['deleted'] is True):
            return None
        return file

    def _update_file_metadata(self, path_: str, filename=None, **kwargs):
        """Update file metadata.

        update should be a dict of {key: new-value} pairs in the metadata, with
        the exception of the filename key, which updates the filename of the
        GridFS file (not in file.metadata)."""
        # path is a metadata key too and we don't want to accidentally pass it
        # twice as an argument to the function if we're trying to rename a file
        path = path_
        # map keys to metadata keys
        update = {'$set': {('metadata.' + key): kwargs[key]
                           for key in kwargs.keys()}}
        # special case for filename
        if filename is not None:
            update['$set']['filename'] = filename
        result = self._files_metadata.find_one_and_update(
            filter={'filename': path},
            update=update,
            sort=[('uploadDate', -1)])
        if result is None:
            raise FileNotFoundError

    def file_exists(self, path: str = '') -> bool:
        """Does a file exist at the given path?

        Like os.path.isfile

        Parameters
        ----------
        path : string
            The API path of a file to check for.

        Returns
        -------
        exists : bool
            Whether the file exists.
        """
        return self._file_exists(self.normalize_path(path))

    def _file_exists(self, path: str) -> bool:
        """Like file_exists but expects normalized path."""
        return self._get_file_gridout(path) is not None

    def get(self, path, content=True, type=None, format=None) -> dict:
        """Get a file or directory model.

        Parameters
        ----------
        path : string
            The API path of a file to check for.
        content : bool (optional)
            True if the content key should be exist and be populated; False
            otherwise
        type : string (optional)
            The type of resource to check for; valid options are "directory",
            "file", and "notebook"; if omitted, the type is inferred.
        format : string
            The format expected; valid options are "json", "text", or "base64"
            Note: this option is currently ignored (format is specified at file
            creation and no format-coercions will be done)

        Returns
        -------
        exists : dict (model)
            A dictionary model representing the request resource. The model may
            contain the following fields.
            - name (unicode)
                basename of the entity
            - path (unicode)
                full (API-style) path to the entity relative to the root
                directory
            - type (unicode)
                the entity type, one of "notebook", "file" or "directory"
            - created (datetime)
                creation date of the entity.
                Note: this currently may not be accurate if files are
                overwritten
            - last_modified (datetime)
                last modified date of the entity
            - content (variable)
                the “content” of the entity; content is a list of models if type
                is "directory", or a string of type is "file", or NotebookNode
                if type is "notebook"
            - mimetype (unicode or None)
                the mimetype of content, if any
            - format (unicode or None)
                the format of content, if any"""
        path = self.normalize_path(path)
        # we delegate to subroutines based on type
        if type == 'directory' or (type is None and self._dir_exists(path)):
            model = self._get_directory(path, content)
        elif type == 'file' or (type is None and self._file_exists(path)):
            model = self._get_file(path, content)
        elif type == 'notebook':
            model = self._get_notebook(path, content)
        else:
            model = None
        self.log.debug(f"got model at path {path}: {repr(model)}")
        return model

    def _get_directory(self, path, content=True) -> Union[dict, None]:
        """Get a dictionary model or none.

        See the get method for parameter and return type details."""
        data = self._directories.find_one({'path': path})
        if data is None:
            return None

        model = {
            'name': os.path.basename(data['path']),
            'path': self.denormalize_path(data['path']),
            'mimetype': None,
            'type': 'directory',
            'writable': True,
            'created': data['created'],
            'last_modified': data['last_modified'],
            'content': None,
            'format': None,
        }
        if not content:
            return model

        # get content
        # this is fun! :)
        # directories are easier than files

        # children: list of content-less models
        children: List[dict] = []
        # match_regex: regex to match exactly one level past the path
        match_regex = '^' + re.escape(path.rstrip('/') + '/') + r'[^\/]+$'

        subdirectories = self._directories.find(
            {'path': {'$regex': match_regex}})
        for subdirectory in subdirectories:
            print(subdirectory['path'])
            children.append({
                'name': os.path.basename(subdirectory['path']),
                'path': self.denormalize_path(subdirectory['path']),
                'type': 'directory',
                'created': subdirectory['created'],
                'last_modified': subdirectory['last_modified'],
                'mimetype': None,
                'format': 'json',
                'content': None,
            })

        # description of pipeline:
        # $match: is pretty obvious
        # $sort: sorts individual files by their uploadedDate (newest first)
        # $group: groups documents together
        #   - _id: $filename groups by filename
        #   - item is the directory or file in the returned document ($first:
        #     specifies that we want the first matching document (i.e. newest)
        #     and $$ROOT means that we want the entire document
        # $project: we only care about the file we found in the grouping stage
        pipeline = [
            {'$match': {'filename': {'$regex': match_regex}}},
            {'$sort': {'uploadedDate': -1}},
            {'$group': {'_id': '$filename', 'file': {'$first': '$$ROOT'}}},
            {'$project': {'file': 1, '_id': 0}},
        ]
        files_cursor = self._files_metadata.aggregate(pipeline)
        for document in files_cursor:
            # note: since file is a document, not a GridOut, we can't use
            # .attribute, we have to use ['attribute']
            file = document['file']
            metadata = file['metadata']
            print(file['filename'])
            if ('deleted' in metadata
                    and metadata['deleted'] is True):
                continue
            children.append({
                'name': os.path.basename(file['filename']),
                'path': self.denormalize_path(file['filename']),
                'type': metadata['type'],
                'created': metadata['created'],
                'last_modified': metadata['last_modified'],
                'mimetype': metadata['mimetype'],
                'format': metadata['format'],
                'content': None,
            })
        children.sort(key=lambda i: i['name'])
        model['content'] = children
        model['format'] = 'json'
        return model

    def _get_file(self, path, content=True) -> Union[dict, None]:
        file: GridOut = self._get_file_gridout(path)
        metadata: dict = file.metadata

        # if type wasn't specified as a parameter to self.get, we tend to
        # initially guess that notebooks are files, so we have to change courses
        # if that happens
        if metadata['type'] == 'notebook':
            return self._get_notebook(path, content, file=file)

        model = {
            'name': os.path.basename(metadata['path']),
            'path': self.denormalize_path(metadata['path']),
            'format': metadata['format'],
            'mimetype': metadata['mimetype'],
            'type': metadata['type'],
            'created': metadata['created'],
            'last_modified': metadata['last_modified'],
            'writable': True,
            'content': None,
        }
        if not content:
            return model

        model['content'] = file.read().decode()
        return model

    def _get_notebook(self, path: str, content: bool, file: GridOut = None) \
            -> Union[dict, None]:
        """Get a dictionary model or None.

        See the get method for parameter and return type details."""
        print('get notebook')
        file: GridOut = self._get_file_gridout(path) if file is None else file
        metadata: dict = file.metadata

        model = {
            'name': metadata['name'],
            'path': self.denormalize_path(metadata['path']),
            'format': None,
            'content': None,
            'mimetype': metadata['mimetype'],
            'type': metadata['type'],
            'created': metadata['created'],
            'last_modified': metadata['last_modified'],
            'writable': True,
        }
        if not content:
            self.log.debug(
                f"Returning model at {path} without content: {model}")
            return model

        model['format'] = 'json'
        model['content'] = nbformat.notebooknode.from_dict(json.load(file))
        self.log.debug(
            f"Returning model at {path} with content: {model}")
        return model

    def delete_file(self, path):
        self._delete_file(self.normalize_path(path))

    def _delete_file(self, path):
        self._update_file_metadata(path, deleted=True)

    def rename_file(self, old_path, new_path):
        return self._rename_file(self.normalize_path(old_path),
                                 self.normalize_path(new_path))

    def _rename_file(self, old_path, new_path):
        self._update_file_metadata(old_path,
                                   filename=new_path,
                                   name=os.path.basename(new_path),
                                   path=new_path)

    def save(self, model: dict, path: str):
        """Save a file or directory model to path.

        Should return the saved model with no content. Save implementations
        should call self.run_pre_save_hook(model=model, path=path) prior to
        writing any data.
        """
        if 'type' not in model:
            raise web.HTTPError(400, u'No file type provided')
        if 'content' not in model and model['type'] != 'directory':
            raise web.HTTPError(400, u'No file content provided')

        self.run_pre_save_hook(model, path)

        model['path'] = path.strip('/')
        model['name'] = os.path.basename(model['path'])
        model['created'] = (model['created'] if 'created' in model
                            else datetime.datetime.now())
        model['last_modified'] = datetime.datetime.now()
        model['mimetype'] = (model['mimetype'] if 'mimetype' in model
                             else None)
        model['writable'] = True

        normal_path = self.normalize_path(path)
        if model['type'] == 'directory':
            self._save_directory(model, normal_path)
        elif model['type'] == 'file':
            self._save_file(model, normal_path)
        elif model['type'] == 'notebook':
            self._save_notebook(model, normal_path)
        else:
            raise web.HTTPError(400, "Not implemented.")

        return self.get(path, content=False)

    def _save_directory(self, model, path):
        try:
            result = self._directories.insert_one({
                'path': path,
                'created': datetime.datetime.now(),
                'last_modified': datetime.datetime.now(),
            })
        except DuplicateKeyError:
            self.log.debug('Tried to create directory {} which already exists'
                           .format(path))
        return model

    def _save_file(self, model, path, file_type='file'):
        file_metadata = {
            'name': os.path.basename(path),
            'path': path,
            'type': file_type,
            'created': model['created'],
            'last_modified': model['last_modified'],
            'mimetype': model['mimetype'],
            'format': model['format'] if 'format' in model else None,
        }
        file: GridIn = self._files.open_upload_stream(
            filename=path, metadata=file_metadata)
        if 'mimetype' is not None:
            file.content_type = model['mimetype']
        file.write(model["content"].encode())
        file.close()
        self.log.debug(f"Saved file {path} model {repr(model)}")
        return {key: model[key] for key in model.keys() if key != 'content'}

    def _save_notebook(self, model, path):
        model['format'] = 'json'
        json_serialization = json.dumps(model['content'])
        # create a quasi-deep copy (so we don't overwrite original content)
        file_model = {key: model[key]
                      for key in model.keys() if key != 'content'}
        file_model['content'] = json_serialization
        self._save_file(file_model, path, file_type='notebook')
        result = {key: model[key] for key in model.keys()}
        self.log.debug(f"Saved notebook {path} model {repr(result)}")
        return {key: model[key] for key in model.keys()
                if (key != 'content' and key != 'format')}
