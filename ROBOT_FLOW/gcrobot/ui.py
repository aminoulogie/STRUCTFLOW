"""Compact modeless desktop panel. All Robot calls stay on the Tk/COM STA thread."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from .model import Workspace, Grid, number, positive, column, wall, panel, point
from .checks import inspect_model
from .robot import RobotSession


class Form(tk.Toplevel):
    def __init__(self, parent, title, fields, submit):
        super().__init__(parent)
        self.title(title); self.transient(parent); self.resizable(False,False)
        body = ttk.Frame(self,padding=14); body.pack(fill='both',expand=True)
        self.values = {}
        for row,(key,label,default,choices) in enumerate(fields):
            ttk.Label(body,text=label).grid(row=row,column=0,sticky='w',padx=(0,14),pady=5)
            var = tk.StringVar(value=str(default)); self.values[key] = var
            if choices is not None:
                widget = ttk.Combobox(body,textvariable=var,values=choices,state='readonly',width=34)
            else: widget = ttk.Entry(body,textvariable=var,width=37)
            widget.grid(row=row,column=1,sticky='ew',pady=5)
            if row==0: widget.focus_set()
        def apply():
            try:
                if submit({k:v.get() for k,v in self.values.items()}) is not False: self.destroy()
            except Exception as exc:
                messagebox.showerror(title,str(exc),parent=self)
        buttons = ttk.Frame(body); buttons.grid(row=len(fields),column=0,columnspan=2,sticky='e',pady=(12,0))
        ttk.Button(buttons,text='Cancel',command=self.destroy).pack(side='left',padx=4)
        ttk.Button(buttons,text='Apply',command=apply).pack(side='left')
        self.bind('<Return>',lambda e:apply()); self.bind('<Escape>',lambda e:self.destroy())
        self.grab_set()


def icon(master, kind):
    """Original 16 px engineering glyphs, no Autodesk artwork."""
    img = tk.PhotoImage(master=master,width=18,height=18)
    ink,accent = '#344858','#dd8d27'
    def rect(x,y,w,h,color=ink): img.put(color,to=(x,y,x+w,y+h))
    if kind=='grid':
        for n in (3,8,13): rect(n,2,1,14); rect(2,n,14,1)
    elif kind=='level':
        for n,w in ((4,13),(9,10),(14,7)): rect(3,n,w,2)
        rect(2,2,2,14,accent)
    elif kind=='draw':
        rect(3,3,12,2); rect(3,13,12,2); rect(3,3,2,12); rect(13,3,2,12)
        rect(7,7,4,4,accent)
    elif kind=='check':
        for i in range(4): rect(2+i,8+i,2,2,accent)
        for i in range(8): rect(6+i,11-i,2,2,ink)
    elif kind=='material':
        rect(3,4,12,11); rect(5,6,8,7,accent)
    elif kind=='isolate':
        for x,y in ((2,2),(12,2),(2,12),(12,12)): rect(x,y,4,4)
        rect(7,7,4,4,accent)
    elif kind=='save':
        rect(3,2,12,14); rect(5,3,7,4,accent); rect(5,10,8,5,'#ffffff')
    elif kind=='open':
        rect(2,5,14,10,accent); rect(2,2,6,4); rect(4,7,10,6,'#ffffff')
    else:
        rect(2,6,5,6); rect(11,6,5,6); rect(7,8,4,2,accent)
    return img


class App(tk.Tk):
    def __init__(self, expected_id=None, initial_tab='Levels'):
        super().__init__()
        self.title('GCStructFlow · Robot modeling — 0.1 preview')
        self.geometry('840x690'); self.minsize(720,580)
        style = ttk.Style(self)
        if 'vista' in style.theme_names(): style.theme_use('vista')
        style.configure('Treeview',rowheight=25)
        self.workspace = Workspace(); self.session = None; self.expected_id = expected_id
        self.dirty = False; self.path = None; self.issues = []
        self.icons = {k:icon(self,k) for k in ('grid','level','draw','check','material','isolate','save','open','connect')}
        self.status = tk.StringVar(value='Disconnected · connect to an open Robot project')
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.make_menu()
        bar = ttk.Frame(self,padding=(6,5)); bar.pack(fill='x')
        for title,glyph,action in [('Connect','connect',self.connect),('Open','open',self.load),('Save','save',self.save),
                                   ('Level','level',self.edit_level),('Grid','grid',self.add_grid),
                                   ('Isolate','isolate',lambda:self.robot_action('Isolate selection',lambda s:s.isolate_selection())),
                                   ('Check','check',self.check)]:
            ttk.Button(bar,text=title,image=self.icons[glyph],compound='left',command=self.safe(action)).pack(side='left',padx=2)
        self.notebook = ttk.Notebook(self); self.notebook.pack(fill='both',expand=True,padx=8,pady=6)
        self.tabs = {}
        for title in ('Levels','Grids','Properties','Draw','Checks'):
            frame = ttk.Frame(self.notebook,padding=10); self.notebook.add(frame,text=title); self.tabs[title]=frame
        self.make_levels(); self.make_grids(); self.make_properties(); self.make_draw(); self.make_checks()
        self.logbox = tk.Text(self,height=4,wrap='word',state='disabled',font=('Consolas',9))
        self.logbox.pack(fill='x',padx=8,pady=3)
        ttk.Label(self,textvariable=self.status,relief='sunken',anchor='w',padding=5).pack(fill='x',side='bottom')
        self.notebook.select(self.tabs.get(initial_tab,self.tabs['Levels']))
        for event,action in {'<Control-s>':self.save,'<Control-o>':self.load,'<Control-l>':self.edit_level,
                             '<Control-g>':self.add_grid,'<F5>':self.refresh_robot,'<F8>':self.check,
                             '<Control-i>':lambda:self.robot_action('Isolate selection',lambda s:s.isolate_selection()),
                             '<Control-r>':lambda:self.robot_action('Restore view',lambda s:s.restore_view())}.items():
            self.bind(event,lambda e,a=action:self.safe(a)())
        self.render_levels(); self.render_grids()

    def safe(self, action):
        def run():
            try: return action()
            except Exception as exc:
                self.log(str(exc)); messagebox.showerror('GCStructFlow',str(exc),parent=self)
        return run

    def log(self, text):
        self.logbox.configure(state='normal'); self.logbox.insert('end',text+'\n')
        self.logbox.see('end'); self.logbox.configure(state='disabled')

    def make_menu(self):
        menu = tk.Menu(self); self.config(menu=menu)
        definitions = {
            'File':[('Open settings…',self.load),('Save settings',self.save),('Save settings as…',lambda:self.save(True)),('Close',self.close)],
            'Levels':[('Add level…',self.edit_level)],
            'Grids':[('Add grid set…',self.add_grid),('Refresh Robot grids',self.refresh_robot),('Restore grid visibility',lambda:self.visibility('restore'))],
            'Visibility':[('Isolate selected elements',lambda:self.robot_action('Isolate',lambda s:s.isolate_selection())),('Return to original view',lambda:self.robot_action('Restore',lambda s:s.restore_view()))],
            'Help':[('About / shortcuts',lambda:messagebox.showinfo('GCStructFlow','Initial modeling preview for Robot 2027.\n\nCtrl+L: level · Ctrl+G: grid\nCtrl+I: isolate · Ctrl+R: return to original view\nF5: refresh · F8: checks\nCtrl+S / Ctrl+O: save / open settings\n\nShortcuts work while this panel has focus.\nSee README for installation and Windows validation.',parent=self))]
        }
        for title,items in definitions.items():
            sub = tk.Menu(menu,tearoff=False); menu.add_cascade(label=title,menu=sub)
            for label,action in items: sub.add_command(label=label,command=self.safe(action))

    def tree(self, parent, columns):
        frame=ttk.Frame(parent); frame.pack(fill='both',expand=True,pady=6)
        tree=ttk.Treeview(frame,columns=[k for k,_ in columns],show='headings',selectmode='browse')
        for key,title in columns: tree.heading(key,text=title); tree.column(key,width=150)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=tree.yview); tree.configure(yscrollcommand=scroll.set)
        tree.pack(side='left',fill='both',expand=True); scroll.pack(side='right',fill='y')
        return tree

    def buttons(self,parent,items):
        row=ttk.Frame(parent); row.pack(fill='x',pady=5)
        for text,action in items: ttk.Button(row,text=text,command=self.safe(action)).pack(side='left',padx=(0,5))

    def selected(self, tree):
        keys=tree.selection()
        if not keys: raise ValueError('Select a row first.')
        return keys[0]

    def make_levels(self):
        frame=self.tabs['Levels']
        ttk.Label(frame,text='Exact reference elevations · metres',font=('Segoe UI',11,'bold')).pack(anchor='w')
        ttk.Label(frame,text='Reference edits do not move existing Robot geometry. Double-click a row to make it active.').pack(anchor='w')
        self.leveltree=self.tree(frame,[('name','Level'),('elevation','Elevation (m)'),('reference','Relative to'),('offset','Offset (m)')])
        self.leveltree.bind('<Double-1>',self.safe_event(self.activate_level))
        self.buttons(frame,[('Add…',self.edit_level),('Edit…',lambda:self.edit_level(self.selected(self.leveltree))),('Set active',self.activate_level),('Remove',self.remove_level)])
        self.active_label=tk.StringVar(); ttk.Label(frame,textvariable=self.active_label).pack(anchor='w')

    def safe_event(self,action): return lambda e:self.safe(action)()

    def edit_level(self,key=None):
        old=self.workspace.levels.get(key,{'offset':'0','relative_to':''})
        def apply(v):
            target=key or v['name']
            if key is None and target.strip() in self.workspace.levels: raise ValueError('Level name already exists. Use Edit.')
            self.workspace.set_level(target,v['offset'],v['relative']); self.dirty=True; self.render_levels()
        Form(self,'Edit level' if key else 'Add reference level',[
            ('name','Level name',key or '',[key] if key else None),
            ('offset','Elevation / offset (m)',old['offset'],None),
            ('relative','Relative to (blank = absolute)',old['relative_to'],['']+[k for k in self.workspace.levels if k!=key])],apply)

    def render_levels(self):
        self.leveltree.delete(*self.leveltree.get_children())
        for key in sorted(self.workspace.levels,key=self.workspace.elevation):
            item=self.workspace.levels[key]
            self.leveltree.insert('','end',iid=key,values=(key,str(self.workspace.elevation(key)),item['relative_to'],item['offset']))
        active=self.workspace.active
        self.active_label.set(f'Active drawing reference: {active}  /  {self.workspace.elevation(active)} m' if active else 'Add a level to start drawing.')
        if active: self.leveltree.selection_set(active)

    def activate_level(self):
        self.workspace.active=self.selected(self.leveltree); self.dirty=True; self.render_levels()

    def remove_level(self):
        self.workspace.remove_level(self.selected(self.leveltree)); self.dirty=True; self.render_levels()

    def make_grids(self):
        frame=self.tabs['Grids']
        ttk.Label(frame,text='Named grid sets · coordinates in metres',font=('Segoe UI',11,'bold')).pack(anchor='w')
        self.gridtree=self.tree(frame,[('name','Local definition'),('x','X positions'),('y','Y positions'),('rotation','Rotation (°)')])
        self.buttons(frame,[('Add…',self.add_grid),('Create selected in Robot',self.publish_grid),('Remove local definition',self.remove_grid)])
        ttk.Label(frame,text='Robot grid visibility · double-click to toggle').pack(anchor='w')
        self.robotgrids=self.tree(frame,[('name','Native Robot grid'),('visible','Visible')])
        self.robotgrids.bind('<Double-1>',self.safe_event(lambda:self.visibility('toggle')))
        self.buttons(frame,[('Toggle',lambda:self.visibility('toggle')),('Only selected',lambda:self.visibility('only')),
                            ('Show all',lambda:self.visibility('show')),('Hide all',lambda:self.visibility('hide')),('Restore',lambda:self.visibility('restore'))])

    def add_grid(self):
        def apply(v):
            levels=[s.strip() for s in v['levels'].split(';') if s.strip()]
            for level in levels: self.workspace.elevation(level)
            grid=Grid(v['name'],v['x'].split(';'),v['y'].split(';'),v['ox'],v['oy'],v['angle'],levels)
            if any(g.name==grid.name for g in self.workspace.grids): raise ValueError('Grid name already exists.')
            self.workspace.grids.append(grid); self.dirty=True; self.render_grids()
        Form(self,'Add grid set',[(k,label,default,None) for k,label,default in [
            ('name','Name','Pool'),('x','X positions (m), separated by ;','0; 2.37; 5.12'),('y','Y positions (m), separated by ;','0; 3.25; 7.6'),
            ('ox','Origin X (m)','0'),('oy','Origin Y (m)','0'),('angle','Rotation (degrees)','0'),
            ('levels','Level names separated by ; (blank = all)','')]],apply)

    def render_grids(self):
        self.gridtree.delete(*self.gridtree.get_children())
        for i,g in enumerate(self.workspace.grids): self.gridtree.insert('','end',iid=str(i),values=(g.name,'; '.join(g.x),'; '.join(g.y),g.angle))

    def remove_grid(self):
        self.workspace.grids.pop(int(self.selected(self.gridtree))); self.dirty=True; self.render_grids()

    def publish_grid(self):
        grid=self.workspace.grids[int(self.selected(self.gridtree))]
        elevations=[self.workspace.elevation(k) for k in (grid.levels or self.workspace.levels)]
        self.robot_action('Create grid',lambda s:s.create_grid(grid,elevations),mutate=True)
        self.refresh_robot()

    def visibility(self,mode):
        label=self.selected(self.robotgrids) if mode in ('toggle','only') else None
        self.robot_action('Grid visibility',lambda s:s.grid_visibility(mode,label)); self.refresh_robot()

    def make_properties(self):
        frame=self.tabs['Properties']
        ttk.Label(frame,text='Concrete properties',font=('Segoe UI',11,'bold')).pack(anchor='w')
        ttk.Label(frame,text='New names only. Existing Robot labels are never overwritten. Dimensions are in metres.').pack(anchor='w')
        self.properties=self.tree(frame,[('kind','Type'),('name','Robot label')])
        self.buttons(frame,[('Refresh',self.refresh_robot),('Concrete material…',self.add_material),('Rectangular section…',self.add_section),('Wall / floor thickness…',self.add_thickness)])
        ttk.Label(frame,text='Custom materials define elastic analysis properties. Set code-specific design strengths in Robot.',wraplength=740).pack(anchor='w')

    def require_session(self):
        if self.session is None: raise RuntimeError('Connect to Robot first.')
        self.session.guard(); return self.session

    def robot_action(self,title,action,mutate=False):
        session=self.require_session(); before=len(session.created)
        try:
            result=action(session)
            for item in session.created[before:]: self.log('Created: '+item)
            self.log(title+' completed.'); return result
        except Exception as exc:
            for item in session.created[before:]: self.log('Created before error: '+item)
            text=str(exc)
            if mutate: text+='\nThe API operation may have partially completed. Review Robot and the action log before retrying.'
            raise RuntimeError(text) from exc

    def connect(self):
        self.session=RobotSession.connect(self.expected_id)
        self.issues=[]
        self.checktree.delete(*self.checktree.get_children())
        self.status.set('Connected · '+str(self.session.app.Project.Name)+' · geometry units: m')
        self.refresh_robot()

    def refresh_robot(self):
        session=self.require_session()
        self.robotgrids.delete(*self.robotgrids.get_children())
        for key,visible in session.grid_states().items(): self.robotgrids.insert('','end',iid=key,values=(key,'Shown' if visible else 'Hidden'))
        self.properties.delete(*self.properties.get_children())
        for kind in ('material','section','thickness'):
            for label in session.label_names(kind): self.properties.insert('','end',values=(kind,label))

    def add_material(self):
        self.require_session()
        def apply(v):
            self.robot_action('Create material',lambda s:s.create_material(v['name'],v['e'],v['nu'],v['weight'],v['alpha']),True); self.refresh_robot()
        Form(self,'New elastic concrete material',[(k,label,value,None) for k,label,value in [
            ('name','Name','GC Concrete'),('e','Young modulus E (MPa)','30000'),('nu','Poisson ratio','0.2'),
            ('weight','Unit weight (kN/m³)','25'),('alpha','Thermal expansion (1/°C)','0.00001')]],apply)

    def add_section(self):
        materials=self.require_session().label_names('material')
        def apply(v):
            self.robot_action('Create section',lambda s:s.create_section(v['name'],v['kind'],v['material'],v['b'],v['h']),True); self.refresh_robot()
        Form(self,'New concrete rectangle',[
            ('name','Name','GC C300x500',None),('kind','Member type','Column',['Column','Beam']),
            ('material','Robot material',materials[0] if materials else '',materials),('b','Width (m)','0.30',None),('h','Depth (m)','0.50',None)],apply)

    def add_thickness(self):
        materials=self.require_session().label_names('material')
        def apply(v):
            self.robot_action('Create thickness',lambda s:s.create_thickness(v['name'],v['material'],v['t']),True); self.refresh_robot()
        Form(self,'New wall / floor thickness',[
            ('name','Name','GC Pool wall 250',None),('material','Robot material',materials[0] if materials else '',materials),('t','Thickness (m)','0.25',None)],apply)

    def make_draw(self):
        frame=self.tabs['Draw']
        ttk.Label(frame,text='Draw by exact coordinates',font=('Segoe UI',11,'bold')).pack(anchor='w')
        ttk.Label(frame,text='Choose a reference on Levels, then an element below. Review coordinates before creation.\nGrid axes remain native Robot snapping guides for drawing directly in Robot.',wraplength=740).pack(anchor='w',pady=8)
        for kind,description in [('Column','X / Y position and bottom / top reference levels'),('Beam','Two 3D endpoints'),
                                 ('Wall','Two plan points and bottom / top reference levels'),('Base','Rectangle at the active reference elevation'),
                                 ('Polygon','Planar perimeter, including a sloping pool base')]:
            row=ttk.Frame(frame); row.pack(fill='x',pady=7)
            ttk.Button(row,text=kind,image=self.icons['draw'],compound='left',width=14,command=self.safe(lambda k=kind:self.draw(k))).pack(side='left')
            ttk.Label(row,text=description).pack(side='left',padx=12)
        ttk.Label(frame,text='Panel generation creates geometry and thickness labels; it does not mesh or verify edge connectivity.',wraplength=740).pack(anchor='w',pady=12)

    def draw(self,kind):
        session=self.require_session()
        levels=list(self.workspace.levels)
        active=self.workspace.active
        if not active: raise ValueError('Create and select a reference level first.')
        z=str(self.workspace.elevation(active))
        labels=session.label_names('section' if kind in ('Beam','Column') else 'thickness')
        if not labels: raise ValueError('Create a matching section / thickness in Properties first.')
        if kind=='Polygon': return self.polygon_dialog(labels,z)
        fields=[('property','Section / thickness',labels[0],labels)]
        if kind in ('Column','Wall'):
            fields += [('bottom','Bottom reference',active,levels),('top','Top reference',next((k for k in levels if self.workspace.elevation(k)>self.workspace.elevation(active)),active),levels)]
        coordinates={'Column':[('x','0'),('y','0')], 'Wall':[('x1','0'),('y1','0'),('x2','4'),('y2','0')],
                     'Beam':[('x1','0'),('y1','0'),('z1',z),('x2','4'),('y2','0'),('z2',z)],
                     'Base':[('x1','0'),('y1','0'),('x2','4'),('y2','8'),('z',z)]}[kind]
        fields += [(k,k.upper()+' (m)',default,None) for k,default in coordinates]
        def apply(v):
            if kind=='Column': pts=column(v['x'],v['y'],self.workspace.elevation(v['bottom']),self.workspace.elevation(v['top']))
            elif kind=='Wall': pts=wall(v['x1'],v['y1'],v['x2'],v['y2'],self.workspace.elevation(v['bottom']),self.workspace.elevation(v['top']))
            elif kind=='Beam': pts=[point((v['x1'],v['y1'],v['z1'])),point((v['x2'],v['y2'],v['z2']))]
            else: pts=panel([(v['x1'],v['y1'],v['z']),(v['x2'],v['y1'],v['z']),(v['x2'],v['y2'],v['z']),(v['x1'],v['y2'],v['z'])])
            return self.create_geometry(kind,pts,v['property'])
        Form(self,'Draw '+kind,fields,apply)

    def create_geometry(self,kind,points,prop):
        summary=f'{kind} · {prop}\nCoordinates in metres:\n'+'\n'.join(', '.join(f'{v:.9g}' for v in p) for p in points)
        if not messagebox.askokcancel('Create in Robot',summary,parent=self): return False
        self.robot_action('Create '+kind,lambda s:s.create_bar(points,prop) if kind in ('Beam','Column') else s.create_panel(points,prop),True)
        return True

    def polygon_dialog(self,labels,z):
        win=tk.Toplevel(self); win.title('Draw planar polygon'); win.transient(self); win.grab_set()
        ttk.Label(win,text='One X; Y; Z point per line, metres. Follow the perimeter in order.').pack(padx=12,pady=10)
        prop=tk.StringVar(value=labels[0]); ttk.Combobox(win,textvariable=prop,values=labels,state='readonly',width=45).pack()
        text=tk.Text(win,width=55,height=12); text.pack(padx=12,pady=10)
        text.insert('1.0',f'0; 0; {z}\n4; 0; {z}\n4; 8; {z}\n0; 8; {z}')
        def apply():
            pts=panel([line.split(';') for line in text.get('1.0','end').splitlines() if line.strip()])
            if self.create_geometry('Polygon',pts,prop.get()): win.destroy()
        ttk.Button(win,text='Preview / create',command=self.safe(apply)).pack(pady=10)

    def make_checks(self):
        frame=self.tabs['Checks']
        ttk.Label(frame,text='Geometry review · nodes and bars',font=('Segoe UI',11,'bold')).pack(anchor='w')
        row=ttk.Frame(frame); row.pack(fill='x',pady=8)
        ttk.Label(row,text='Proximity tolerance (m)').pack(side='left')
        self.tolerance=tk.StringVar(value='0.001'); ttk.Entry(row,textvariable=self.tolerance,width=12).pack(side='left',padx=8)
        ttk.Button(row,text='Run checks',command=self.safe(self.check)).pack(side='left')
        self.checktree=self.tree(frame,[('code','Check'),('message','Finding')]); self.checktree.column('message',width=500)
        self.checktree.bind('<Double-1>',self.safe_event(self.select_issue))
        self.buttons(frame,[('Select affected elements',self.select_issue)])
        ttk.Label(frame,text='Read-only findings for review, not automatic repairs. Panel connectivity and structural adequacy are not checked.',wraplength=740).pack(anchor='w')

    def check(self):
        session=self.require_session(); tolerance=positive(self.tolerance.get())
        self.issues=inspect_model(session.nodes(),session.bars(),[self.workspace.elevation(k) for k in self.workspace.levels],tolerance)
        self.checktree.delete(*self.checktree.get_children())
        for i,issue in enumerate(self.issues): self.checktree.insert('','end',iid=str(i),values=(issue.code,issue.message))
        self.notebook.select(self.tabs['Checks']); self.log(f'{len(self.issues)} findings from node/bar geometry checks. Panels were not checked.')

    def select_issue(self):
        issue=self.issues[int(self.selected(self.checktree))]
        self.robot_action('Select finding',lambda s:s.select(issue.kind,issue.ids))

    def save(self,save_as=False):
        path=self.path if not save_as else None
        if not path: path=filedialog.asksaveasfilename(parent=self,defaultextension='.gcrobot.json',filetypes=[('GCStructFlow settings','*.json')])
        if not path: return False
        self.workspace.save(path); self.path=path; self.dirty=False; self.log('Settings saved: '+path); return True

    def can_discard(self):
        if not self.dirty: return True
        answer=messagebox.askyesnocancel('Unsaved reference settings','Save reference levels and grid definitions before continuing?',parent=self)
        if answer is None: return False
        return self.save() if answer else True

    def load(self):
        if not self.can_discard(): return
        path=filedialog.askopenfilename(parent=self,filetypes=[('GCStructFlow settings','*.json')])
        if not path: return
        workspace=Workspace.load(path)
        self.workspace=workspace; self.path=path; self.dirty=False
        self.render_levels(); self.render_grids(); self.log('Settings loaded. Robot geometry was not changed.')

    def close(self):
        if self.can_discard(): self.destroy()
