from unittest import TestCase
from mongocontents import MongoContents


class TestSaveDirectory(TestCase):
    contents: MongoContents

    def setUp(self):
        self.contents = MongoContents()

    def reset_db(self):
        self.contents._client.drop_database(self.contents.database_name)
        self.contents = MongoContents()

    def test_model_fields(self):
        self.reset_db()
        self.contents.save({'type': 'directory'}, path='foo')
        dir = self.contents.get('foo', type='directory')
        assert dir['format'] == 'json'
        assert dir['mimetype'] is None
        assert dir['name'] == 'foo'
        assert dir['path'] == 'foo'

    def test_basic(self):
        self.reset_db()
        self.contents.save({'type': 'directory'}, path='foo')
        assert self.contents.dir_exists('foo')
        model = self.contents.get('foo', type='directory')
        assert model is not None
        print(model)
        assert model['name'] == 'foo'
        assert len(model['content']) == 0
        self.contents.save({'type': 'directory'}, path='foo/bar')
        model = self.contents.get('foo', type='directory')
        print(model)
        assert len(model['content']) == 1
        assert model['content'][0]['name']

    def test_double_save(self):
        self.reset_db()
        self.contents.save({'type': 'directory'}, path='foo')
        self.contents.save({'type': 'directory'}, path='foo')
        assert self.contents.dir_exists('foo')

    def test_nested(self):
        self.reset_db()
        self.contents.save({'type': 'directory'}, path='foo')
        self.contents.save({'type': 'directory'}, path='foo/bar')
        self.contents.save({'type': 'directory'}, path='foo/bar/spam')
        self.contents.save({'type': 'directory'}, path='foo/bar/spam/eggs')
        assert self.contents.dir_exists('foo')
        print(self.contents.get('foo', type='directory'))
        assert len(self.contents.get('foo', type='directory')['content']) == 1
        assert self.contents.dir_exists('foo/bar')
        assert len(self.contents.get(
            'foo/bar', type='directory')['content']) == 1
        assert self.contents.dir_exists('foo/bar/spam')
        assert len(self.contents.get(
            'foo/bar/spam', type='directory')['content']) == 1
        assert self.contents.dir_exists('foo/bar/spam/eggs')
        assert len(self.contents.get(
            'foo/bar/spam/eggs', type='directory')['content']) == 0

    def test_without_explicit_type(self):
        self.reset_db()
        self.contents.save({'type': 'directory'}, path='foo')
        dir = self.contents.get('foo')
        assert dir is not None
        assert dir['type'] == 'directory'

    def test_root(self):
        self.reset_db()
        assert self.contents.get('') is not None

    def test_rename(self):
        self.reset_db()
        self.contents.save({'type': 'directory'}, 'foo')
        self.contents.save({'type': 'directory'}, 'bar')
        self.contents.rename_file('foo', 'spam')
