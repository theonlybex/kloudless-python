import unittest
import os

# Add parent dir to path to import utils
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__),
                '..')))
from test_cases import utils


class CRMTask(unittest.TestCase):

    @utils.allow(apis=['crm'])
    def setUp(self):
        data = {
            'status': 'API Test Task Name',
            'priority': 'High'
        }
        self.obj = self.account.crm_tasks.create(data=data)

    @utils.allow(apis=['crm'])
    def tearDown(self):
        self.obj.delete()

    @utils.allow(apis=['crm'], capabilities=['can_crud_crm_tasks'])
    def test_list_object(self):
        objects = self.account.crm_tasks.all()
        # assert properties
        if objects:
            obj = objects[0]
            self.assertEqual(obj.type, 'task')
            self.assertTrue('raw' in obj)

    @utils.allow(apis=['crm'], capabilities=['can_crud_crm_tasks'])
    def test_read_object(self):
        obj = self.account.crm_tasks.retrieve(self.obj.id)
        # assert Task properties
        self.assertEqual(obj.id, self.obj.id)
        self.assertEqual(obj.type, 'task')
        self.assertTrue('raw' in obj)

        self.assertTrue('created' in obj)
        self.assertTrue('modified' in obj)
        self.assertTrue('description' in obj)

    @utils.allow(apis=['crm'], capabilities=['can_crud_crm_tasks'])
    def test_update_object(self):
        obj = self.obj
        obj.description = 'test task description'
        obj.save()
        self.assertEqual('test task description', obj.description)


def test_cases():
    return [utils.create_test_case(acc, CRMTask) for acc in utils.accounts]

if __name__ == '__main__':
    suite = utils.create_suite(test_cases())
    unittest.TextTestRunner(verbosity=2).run(suite)
