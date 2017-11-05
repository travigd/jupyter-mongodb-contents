from unittest import TestCase
from mongocontents import MongoContents


class TestSaveDirectory(TestCase):
    contents: MongoContents

    def setUp(self):
        self.contents = MongoContents()

    def reset_db(self):
        self.contents._client.drop_database(self.contents.database_name)
        self.contents = MongoContents()

    @staticmethod
    def fixture1():
        return {
            'content': """{
                'metadata': {},
                'nbformat': 4,
                'nbformat_minor': 0,
                'cells': [
                    {
                        'cell_type': 'markdown',
                        'metadata': {},
                        'source': 'Some **Markdown**',
                    },
                ],
            },""",
            'format': 'text',
            'mimetype': 'text/plain',
            'type': 'file'
        }

    def test_basic_save(self):
        self.reset_db()
        model = self.fixture1()
        self.contents.save(model, path='foo.txt')
        file = self.contents.get('foo.txt', type='file')
        assert file['content'] == model['content']

    def test_save_in_directory(self):
        self.reset_db()
        self.contents.save({'type': 'directory'}, path='mydir')
        model = self.fixture1()
        self.contents.save(model, path='mydir/foo.txt')
        file = self.contents.get('mydir/foo.txt', type='file')
        print(file)
        assert file['content'] == model['content']
        dir = self.contents.get('mydir')
        print(dir)
        assert (len(dir['content']) == 1)
        self.contents.save({'type': 'directory'}, path='mydir/foo')
        dir = self.contents.get('mydir')
        assert (len(dir['content']) == 2)
        print([item['path'] for item in dir['content']])

    def test_delete(self):
        self.reset_db()
        self.contents.save(self.fixture1(), 'foo.txt')
        file = self.contents.get('foo.txt')
        assert file is not None
        self.contents.delete_file('foo.txt')
        file = self.contents.get('foo.txt')
        assert file is None

    def test_rename(self):
        self.reset_db()
        self.contents.save(self.fixture1(), 'foo.txt')
        self.contents.rename_file('foo.txt', 'bar.txt')
        assert self.contents.get('bar.txt') is not None
