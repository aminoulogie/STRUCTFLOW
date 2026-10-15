import unittest
from types import SimpleNamespace
from gcrobot.robot import RobotSession

class SessionTests(unittest.TestCase):
    def test_project_change_blocks_operations(self):
        app = SimpleNamespace(Project=SimpleNamespace(IsActive=True,UniqueId='first'))
        session = RobotSession(app,None)
        self.assertIs(session.guard(),app.Project)
        app.Project.UniqueId='second'
        with self.assertRaisesRegex(RuntimeError,'changed'): session.guard()

    def test_closed_project_blocks_operations(self):
        app = SimpleNamespace(Project=SimpleNamespace(IsActive=True,UniqueId='first'))
        session = RobotSession(app,None)
        app.Project.IsActive=False
        with self.assertRaises(RuntimeError): session.guard()

    def test_empty_identity_is_rejected(self):
        app = SimpleNamespace(Project=SimpleNamespace(IsActive=True,UniqueId=''))
        with self.assertRaises(RuntimeError): RobotSession(app,None)

class GridManager:
    def __init__(self): self.items = {'Columns':True,'Pool':False,'Walls':True}
    @property
    def Count(self): return len(self.items)
    def Get(self,i): return SimpleNamespace(Name=list(self.items)[i-1])
    def IsActive(self,i): return self.items[list(self.items)[i-1]]
    def FindByName(self,key): return list(self.items).index(key)+1 if key in self.items else 0
    def Activate(self,i,value): self.items[list(self.items)[i-1]]=value

class VisibilityTests(unittest.TestCase):
    def session(self):
        manager=GridManager()
        project=SimpleNamespace(IsActive=True,UniqueId='first',AxisMngr=manager,ViewMngr=SimpleNamespace(Refresh=lambda:None))
        return RobotSession(SimpleNamespace(Project=project),None),manager

    def test_isolate_toggle_restore_original_combination(self):
        session,manager=self.session()
        original=manager.items.copy()
        session.grid_visibility('only','Pool')
        self.assertEqual(manager.items,{'Columns':False,'Pool':True,'Walls':False})
        session.grid_visibility('toggle','Walls')
        session.grid_visibility('restore')
        self.assertEqual(manager.items,original)
        self.assertIsNone(session.grid_snapshot)

    def test_restore_by_name_after_external_deletion(self):
        session,manager=self.session()
        session.grid_visibility('hide')
        del manager.items['Columns']
        manager.items['New']=True
        session.grid_visibility('restore')
        self.assertEqual(manager.items,{'Pool':False,'Walls':True,'New':True})

    def test_unknown_grid_does_not_change_visibility(self):
        session,manager=self.session()
        original=manager.items.copy()
        with self.assertRaises(ValueError): session.grid_visibility('only','Missing')
        self.assertEqual(manager.items,original)
        self.assertIsNone(session.grid_snapshot)

class CreationTests(unittest.TestCase):
    def session(self):
        project=SimpleNamespace(IsActive=True,UniqueId='first')
        return RobotSession(SimpleNamespace(Project=project),None)

    def test_invalid_material_is_rejected_before_com(self):
        session=self.session()
        for e,nu,weight,alpha in [('0','0.2','25','0.00001'),('30000','0.5','25','0.00001'),('30000','0.2','-25','0.00001')]:
            with self.assertRaises(ValueError): session.create_material('X',e,nu,weight,alpha)
        self.assertEqual(session.created,[])

    def test_invalid_geometry_is_rejected_before_com(self):
        session=self.session()
        with self.assertRaises(ValueError): session.create_bar([(0,0,0),(0,0,0)],'Missing')
        with self.assertRaises(ValueError): session.create_panel([(0,0,0),(1,0,0),(2,0,0)],'Missing')
        self.assertEqual(session.created,[])

class ResolvedEndpointTests(unittest.TestCase):
    def session(self):
        # This fake host permits observation of actual writes, without a Robot install.
        self.writes=[]
        bars=SimpleNamespace(FreeNumber=2,Create=lambda *args:self.writes.append(args),
                             Get=lambda key:SimpleNamespace(SetLabel=lambda *args:None))
        project=SimpleNamespace(IsActive=True,UniqueId='first',Structure=SimpleNamespace(Bars=bars),
                                ViewMngr=SimpleNamespace(Refresh=lambda:None))
        sdk=SimpleNamespace(IRobotBar=lambda obj:obj,IRobotLabelType=SimpleNamespace(I_LT_BAR_SECTION=3))
        session=RobotSession(SimpleNamespace(Project=project),sdk)
        session.nodes=lambda:{1:(0.,0.,0.),2:(1.,0.,0.)}
        session.bars=lambda:{1:(1,2,'Existing')}
        session.require_label=lambda *args:None
        return session

    def test_near_inputs_reusing_existing_bar_are_rejected(self):
        session=self.session()
        with self.assertRaises(ValueError):
            session.create_bar([(5e-9,0,0),(1+5e-9,0,0)],'Section')
        self.assertEqual(self.writes,[])

    def test_distinct_inputs_resolving_to_same_node_are_rejected(self):
        session=self.session()
        with self.assertRaises(ValueError):
            session.create_bar([(-7.5e-9,0,0),(7.5e-9,0,0)],'Section')
        self.assertEqual(self.writes,[])
