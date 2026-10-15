"""RobotOM boundary. Importing this module does not load COM or require Windows.

Integration is based on Autodesk Robot API examples; verify on Robot 2027 using
README's smoke checklist. Mutations are additive and never silently retried.
"""
import math
import os
from pathlib import Path
from .model import number, positive, name, point, panel, matching_node


class RobotSession:
    def __init__(self, app, sdk, expected_id=None):
        self.app, self.sdk = app, sdk
        self.project_id = str(app.Project.UniqueId)
        if not self.project_id or (expected_id and expected_id != self.project_id):
            raise RuntimeError('Robot project identity does not match the launching project.')
        self.grid_snapshot = None
        self.original_view = None
        self.created = []
        self.guard()

    @classmethod
    def connect(cls, expected_id=None):
        if os.name != 'nt': raise RuntimeError('Robot connection requires Windows and a running Robot project.')
        from pythonnet import load
        load('netfx')
        import clr
        dll = os.environ.get('ROBOTOM_DLL')
        if not dll:
            base = Path(os.environ.get('ProgramFiles', r'C:\Program Files'))/'Autodesk'/'Robot Structural Analysis Professional 2027'
            dll = next((str(p) for p in (base/'Exe'/'Interop.RobotOM.dll',base/'System'/'Exe'/'Interop.RobotOM.dll') if p.is_file()), None)
        if not dll or not Path(dll).is_file():
            raise RuntimeError('RobotOM DLL not found. Set ROBOTOM_DLL to Robot 2027 Interop.RobotOM.dll.')
        clr.AddReference(str(Path(dll).resolve()))
        import RobotOM as sdk
        from System.Runtime.InteropServices import Marshal
        app = sdk.IRobotApplication(Marshal.GetActiveObject('Robot.Application'))
        return cls(app,sdk,expected_id)

    def guard(self):
        project = self.app.Project
        if not project.IsActive or str(project.UniqueId) != self.project_id:
            raise RuntimeError('Robot project closed or changed. Reconnect before continuing.')
        return project

    def enum(self, enum_type, member):
        return getattr(getattr(self.sdk,enum_type),member)

    def cast(self, kind, value):
        return getattr(self.sdk,kind)(value)

    def refresh(self):
        self.guard().ViewMngr.Refresh()

    def label_type(self, kind):
        return self.enum('IRobotLabelType', {'material':'I_LT_MATERIAL','section':'I_LT_BAR_SECTION','thickness':'I_LT_PANEL_THICKNESS'}[kind])

    def label_names(self, kind):
        names = self.guard().Structure.Labels.GetAvailableNames(self.label_type(kind))
        return [str(names.Get(i)) for i in range(1,names.Count+1)]

    def require_label(self, kind, label):
        if not label or not self.guard().Structure.Labels.Exist(self.label_type(kind),label):
            raise ValueError(f'Unknown Robot {kind}: {label!r}. Refresh the property lists.')

    def new_label(self, kind, label):
        label = name(label)
        labels = self.guard().Structure.Labels
        if labels.Exist(self.label_type(kind),label):
            raise ValueError(f'{label} already exists; use a new name. Existing properties are never overwritten.')
        return self.cast('IRobotLabel',labels.Create(self.label_type(kind),label))

    def create_material(self, label, e_mpa, poisson, weight_kn, alpha):
        e, weight, alpha = positive(e_mpa)*1e6, positive(weight_kn)*1000, float(number(alpha))
        nu = float(number(poisson))
        if not 0 <= nu < 0.5 or alpha < 0: raise ValueError('Use 0 ≤ Poisson ratio < 0.5 and non-negative thermal expansion.')
        item = self.new_label('material',label)
        data = self.cast('IRobotMaterialData',item.Data)
        data.Type = self.enum('IRobotMaterialType','I_MT_CONCRETE')
        data.E, data.NU, data.RO, data.LX = e, nu, weight, alpha
        self.guard().Structure.Labels.Store(item)
        self.created.append(f'Material {label} (elastic properties only)')

    def create_section(self, label, kind, material, width, depth):
        b,h = positive(width),positive(depth)
        if kind not in ('Column','Beam'): raise ValueError('Choose Column or Beam.')
        self.require_label('material',material)
        item = self.new_label('section',label)
        data = self.cast('IRobotBarSectionData',item.Data)
        data.ShapeType = self.enum('IRobotBarSectionShapeType','I_BSST_CONCR_COL_R' if kind=='Column' else 'I_BSST_CONCR_BEAM_RECT')
        concrete = self.cast('IRobotBarSectionConcreteData',data.Concrete)
        prefix = 'COL' if kind=='Column' else 'BEAM'
        concrete.SetValue(self.enum('IRobotBarSectionConcreteDataValue','I_BSCDV_'+prefix+'_B'),b)
        concrete.SetValue(self.enum('IRobotBarSectionConcreteDataValue','I_BSCDV_'+prefix+'_H'),h)
        data.MaterialName = material
        data.CalcNonstdGeometry()
        self.guard().Structure.Labels.Store(item)
        self.created.append(f'Section {label}')

    def create_thickness(self, label, material, thickness):
        t = positive(thickness)
        self.require_label('material',material)
        item = self.new_label('thickness',label)
        data = self.cast('IRobotThicknessData',item.Data)
        data.MaterialName = material
        data.ThicknessType = self.enum('IRobotThicknessType','I_TT_HOMOGENEOUS')
        self.cast('IRobotThicknessHomoData',data.Data).ThickConst = t
        self.guard().Structure.Labels.Store(item)
        self.created.append(f'Thickness {label}')

    def nodes(self):
        objects = self.guard().Structure.Nodes.GetAll()
        result = {}
        for i in range(1,objects.Count+1):
            node = self.cast('IRobotNode',objects.Get(i))
            result[int(node.Number)] = (float(node.X),float(node.Y),float(node.Z))
        return result

    def bars(self):
        objects = self.guard().Structure.Bars.GetAll()
        result = {}
        kind = self.label_type('section')
        for i in range(1,objects.Count+1):
            bar = self.cast('IRobotBar',objects.Get(i))
            section = str(bar.GetLabelName(kind)) if bar.HasLabel(kind) else ''
            result[int(bar.Number)] = (int(bar.StartNode),int(bar.EndNode),section)
        return result

    def create_bar(self, points, section):
        a,b = map(point,points)
        if math.dist(a,b) <= 1e-8: raise ValueError('Bar endpoints must differ.')
        self.require_label('section',section)
        nodes = self.nodes()
        # Resolve every endpoint before any writes; ambiguous nodes abort here.
        ids = [matching_node(nodes,p) for p in (a,b)]
        effective = [nodes[key] if key is not None else p for key,p in zip(ids,(a,b))]
        if math.dist(*effective) <= 1e-8:
            raise ValueError('Endpoints resolve to the same node position.')
        existing = self.bars()
        if any(tuple(sorted((nodes[s],nodes[e]))) == tuple(sorted(effective)) for s,e,_ in existing.values()):
            raise ValueError('A bar already has these endpoints.')
        structure = self.guard().Structure
        for i,p in enumerate((a,b)):
            if ids[i] is None:
                ids[i] = int(structure.Nodes.FreeNumber)
                structure.Nodes.Create(ids[i],*p)
                self.created.append(f'Node {ids[i]}')
        key = int(structure.Bars.FreeNumber)
        structure.Bars.Create(key,*ids)
        self.created.append(f'Bar {key}')
        self.cast('IRobotBar',structure.Bars.Get(key)).SetLabel(self.label_type('section'),section)
        self.refresh()
        return key

    def create_panel(self, points, thickness):
        points = panel(points)
        self.require_label('thickness',thickness)
        structure = self.guard().Structure
        array = self.cast('IRobotPointsArray',self.app.CmpntFactory.Create(self.enum('IRobotComponentType','I_CT_POINTS_ARRAY')))
        array.SetSize(len(points))
        for i,p in enumerate(points,1): array.Set(i,*p)
        key = int(structure.Objects.FreeNumber)
        structure.Objects.CreateContour(key,array)
        self.created.append(f'Panel contour {key}')
        obj = self.cast('IRobotObjObject',structure.Objects.Get(key))
        obj.Main.Attribs.Meshed = True
        obj.SetLabel(self.label_type('thickness'),thickness)
        obj.Initialize()
        obj.Update()
        self.refresh()
        return key

    def grid_states(self):
        manager = self.guard().AxisMngr
        return {str(manager.Get(i).Name):bool(manager.IsActive(i)) for i in range(1,manager.Count+1)}

    def create_grid(self, grid, elevations):
        manager = self.guard().AxisMngr
        label = 'GC / '+grid.name
        if manager.FindByName(label): raise ValueError(f'Grid {label} already exists. Choose a new name.')
        z = sorted(set(number(v) for v in elevations))
        if not z: raise ValueError('Add at least one reference level.')
        xs,ys = [number(v) for v in grid.x],[number(v) for v in grid.y]
        origin = grid.point(xs[0],ys[0])
        native = self.cast('IRobotStructuralAxisGridCartesian',manager.Create(self.enum('IRobotStructuralAxisGridType','I_SAGT_CARTESIAN'),label))
        self.created.append(f'Grid {label}')
        native.IncludeStoreysInZ = False
        native.SetRelativeToPoint(True,*origin,float(z[0]))
        native.RotationAxis = self.enum('IRobotGeoCoordinateAxis','I_GCA_OZ')
        native.RotationAngle = math.radians(float(grid.angle))
        for sequence,values,format_name in ((native.X,xs,'I_SALT_123'),(native.Y,ys,'I_SALT_ABC'),(native.Z,z,'I_SALT_123')):
            sequence.SetLabelFormat(self.enum('IRobotStructuralAxisLabelType',format_name))
            for a,b in zip(values,values[1:]): sequence.AddSequence(float(b-a),1)
        native.Save()
        manager.Activate(manager.FindByName(label),True)
        self.refresh()

    def grid_visibility(self, mode, label=None):
        states = self.grid_states()
        if mode in ('toggle','only') and label not in states: raise ValueError('Select an existing Robot grid.')
        manager = self.guard().AxisMngr
        if mode == 'restore':
            if self.grid_snapshot is None: raise ValueError('No grid visibility state to restore.')
            desired = {k:v for k,v in self.grid_snapshot.items() if k in states}
        else:
            desired = ({label:not states[label]} if mode=='toggle' else
                       {k:(k==label if mode=='only' else mode=='show') for k in states})
            if mode not in ('toggle','only','show','hide'): raise ValueError('Unknown grid visibility action.')
            if self.grid_snapshot is None: self.grid_snapshot = states
        for key,visible in desired.items(): manager.Activate(manager.FindByName(key),visible)
        self.refresh()
        if mode=='restore': self.grid_snapshot = None

    def active_view(self):
        manager = self.guard().ViewMngr
        for i in range(1,manager.ViewCount+1):
            view = self.cast('IRobotView3',manager.GetView(i))
            if view.Window.IsActive: return view
        raise RuntimeError('Activate a Robot graphical view first.')

    def select(self, kind, ids):
        object_type = self.enum('IRobotObjectType','I_OT_NODE' if kind=='node' else 'I_OT_BAR')
        self.guard().Structure.Selections.Get(object_type).FromText(' '.join(map(str,ids)))
        self.active_view().Selection.Get(object_type).FromText(' '.join(map(str,ids)))
        self.refresh()

    def isolate_selection(self):
        project = self.guard()
        kinds = [self.enum('IRobotObjectType','I_OT_'+k) for k in ('NODE','BAR','GEOMETRY','OBJECT','PANEL','FINITE_ELEMENT')]
        selections = [(k,project.Structure.Selections.Get(k)) for k in kinds]
        if not any(sel.Count for _,sel in selections): raise ValueError('Select elements in Robot first.')
        previous = self.active_view()
        view = self.cast('IRobotView3',project.ViewMngr.CreateView(previous.Type))
        view.Projection = previous.Projection
        for kind,selection in selections: view.Selection.Set(kind,selection)
        view.Visible = True
        view.Redraw(0)
        view.Window.Activate()
        if self.original_view is None: self.original_view = previous
        self.refresh()

    def restore_view(self):
        self.guard()
        if self.original_view is None: raise ValueError('No original view recorded.')
        self.original_view.Window.Activate()
        self.original_view = None
