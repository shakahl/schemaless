import logging
import unittest

import schemaless
import schemaless.orm
from schemaless import c

class TestBase(unittest.TestCase):

    def clear_tables(self, datastore):
        for tbl in ['entities', 'index_user_id', 'index_user_name', 'index_foo']:
            datastore.connection.execute('DELETE FROM %s' % (tbl,))

class SchemalessTestCase(TestBase):

    def setUp(self):
        super(SchemalessTestCase, self).setUp()
        self.ds = schemaless.DataStore(mysql_shards=['localhost:3306'], user='test', password='test', database='test')
        self.user = self.ds.define_index('index_user_id', ['user_id'])
        self.user_name = self.ds.define_index('index_user_name', ['first_name', 'last_name'])
        self.foo = self.ds.define_index('index_foo', ['bar'], {'m': 'right'})
        self.clear_tables(self.ds)

        self.entity = self.ds.put({'user_id': schemaless.guid(), 'first_name': 'evan', 'last_name': 'klitzke'})

    def test_query(self):
        self.assertEqual(1, len(self.user.query(c.user_id == self.entity.user_id)))
        self.assertEqual(1, len(self.user_name.query(c.first_name == 'evan', c.last_name == 'klitzke')))

        new_entity = self.ds.put({'user_id': schemaless.guid(), 'first_name': 'george'})
        self.assertEqual(1, len(self.user.query(c.user_id == new_entity.user_id)))
        self.assertEqual(0, len(self.user_name.query(c.first_name == 'george'))) # didn't have a full index

    def test_delete_by_entity(self):
        self.ds.delete(self.entity)
        self.assertEqual(0, len(self.user.query(c.user_id == self.entity.user_id)))

    def test_delete_by_entity_id(self):
        self.ds.delete(id=self.entity.id)
        self.assertEqual(0, len(self.user.query(c.user_id == self.entity.user_id)))

    def test_match_on(self):
        entity_one = self.ds.put({'foo_id': schemaless.guid(), 'bar': 1, 'm': 'left'})
        entity_two = self.ds.put({'foo_id': schemaless.guid(), 'bar': 1, 'm': 'right'}) # only this should match

        rows = self.foo.query(c.bar == 1)
        self.assertEqual(1, len(rows))
        self.assertEqual(rows[0].foo_id, entity_two.foo_id)

    def test_in_queries(self):
        user_ids = [self.entity.user_id]
        user_ids.append(self.ds.put({'user_id': schemaless.guid()}).user_id)

        rows = self.user.query(c.user_id.in_(user_ids))
        self.assertEqual(2, len(rows))
        self.assertEqual(set(user_ids), set(row['user_id'] for row in rows))

class SchemalessORMTestCase(TestBase):

    def setUp(self):
        datastore = schemaless.DataStore(mysql_shards=['localhost:3306'], user='test', password='test', database='test')
        self.clear_tables(datastore)

        self.session = schemaless.orm.Session(datastore)
        base_class = schemaless.orm.make_base(self.session)

        class User(base_class):
            _tag = 1
            _persist = ['user_id', 'first_name', 'last_name']
            _id_field = 'user_id'
            _indexes = [schemaless.orm.Index('index_user_id', ['user_id']),
                        schemaless.orm.Index('index_user_name', ['first_name', 'last_name'])
                       ]

        self.User = User

    def test_create_object_save_delete(self):
        # create a new, empty object
        u = self.User()
        assert not u._saveable()
        assert u.is_dirty

        # populate some, but not all of the fields; the object should be dirty,
        # but not saveable
        u.user_id = schemaless.guid()
        u.first_name = 'evan'
        assert not u._saveable()
        assert u.is_dirty
        user = self.User.get(c.user_id == u.user_id)
        assert not user

        # finish populating the fields, check that the object is saveable
        u.last_name = 'klitzke'
        assert u._saveable()
        assert u.is_dirty

        # persist the object, check that it made it to the datastore
        u.save()
        assert u._saveable()
        assert not u.is_dirty
        user = self.User.get(c.user_id == u.user_id)
        assert user

        # delete the object, check that it's deleted from the datastore
        u.delete()
        assert u._saveable()
        assert not u.is_dirty
        user = self.User.get(c.user_id == u.user_id)
        assert not user

    def test_in_query(self):
        user_ids = []
        users = []
        for x in range(5):
            u = self.User(user_id=schemaless.guid(), first_name='foo', last_name='bar')
            user_ids.append(u.user_id)
            users.append(u)
        self.session.save()

        fetched_users = self.User.query(c.user_id.in_(user_ids[:3]))
        self.assertEqual(set(user_ids[:3]), set(u.user_id for u in users[:3]))

    def test_name_query(self):
        u = self.User(user_id=schemaless.guid(), first_name='foo', last_name='bar')
        u.save()
        v = self.User.get(c.first_name == 'foo', c.last_name == 'bar')
        self.assertEqual(u.user_id, v.user_id)

if __name__ == '__main__':
    unittest.main()
