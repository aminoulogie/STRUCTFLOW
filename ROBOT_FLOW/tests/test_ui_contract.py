import unittest
from types import SimpleNamespace
from unittest.mock import patch
from gcrobot.ui import App

class ConnectionTests(unittest.TestCase):
    def test_reconnect_clears_findings_before_refresh(self):
        deleted=[]
        fake=SimpleNamespace(expected_id=None,issues=['old finding'],session=None,
            checktree=SimpleNamespace(get_children=lambda:('old',),delete=lambda *keys:deleted.extend(keys)),
            status=SimpleNamespace(set=lambda text:None),refresh_robot=lambda:None)
        session=SimpleNamespace(app=SimpleNamespace(Project=SimpleNamespace(Name='New project')))
        with patch('gcrobot.ui.RobotSession.connect',return_value=session):
            App.connect(fake)
        self.assertEqual(fake.issues,[])
        self.assertEqual(deleted,['old'])
