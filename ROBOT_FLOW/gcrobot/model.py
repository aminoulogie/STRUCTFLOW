"""Host-independent modeling rules. Lengths are metres, angles are degrees."""
from dataclasses import dataclass, asdict, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
import math
import os
import tempfile


def number(value):
    if isinstance(value, bool):
        raise ValueError('Enter a number, not a boolean.')
    try:
        result = Decimal(str(value).strip().replace(',', '.'))
    except (InvalidOperation, ValueError):
        raise ValueError(f'Invalid number: {value!r}. Use a decimal point or comma; no thousands separators.') from None
    if not result.is_finite() or abs(result) > Decimal('1e9'):
        raise ValueError('Enter a finite number between -1e9 and 1e9.')
    return result


def positive(value):
    result = number(value)
    if result <= 0:
        raise ValueError('Dimension must be positive.')
    return float(result)


def name(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 100:
        raise ValueError('Enter a name of 1–100 characters.')
    return value.strip()


@dataclass
class Grid:
    name: str
    x: list
    y: list
    origin_x: str = '0'
    origin_y: str = '0'
    angle: str = '0'
    levels: list = field(default_factory=list)

    def __post_init__(self):
        self.name = name(self.name)
        for axis in ('x', 'y'):
            values = [number(v) for v in getattr(self, axis)]
            if not 2 <= len(values) <= 500 or any(a >= b for a,b in zip(values,values[1:])):
                raise ValueError('Each grid axis needs 2–500 strictly increasing coordinates.')
            setattr(self, axis, [str(v) for v in values])
        for attr in ('origin_x','origin_y','angle'):
            setattr(self, attr, str(number(getattr(self, attr))))
        self.levels = [name(v) for v in self.levels]

    def point(self, x, y):
        a = math.radians(float(self.angle))
        x, y = float(number(x)), float(number(y))
        return (float(self.origin_x)+x*math.cos(a)-y*math.sin(a),
                float(self.origin_y)+x*math.sin(a)+y*math.cos(a))


class Workspace:
    def __init__(self):
        self.levels = {}
        self.grids = []
        self.active = ''

    def elevation(self, key, trail=()):
        if key in trail:
            raise ValueError('Relative levels form a cycle.')
        if key not in self.levels:
            raise ValueError(f'Unknown reference level: {key}')
        item = self.levels[key]
        offset = number(item['offset'])
        return offset + (self.elevation(item['relative_to'], trail+(key,)) if item['relative_to'] else 0)

    def set_level(self, key, offset, relative_to=''):
        key = name(key)
        old = self.levels.copy()
        self.levels[key] = {'offset':str(number(offset)), 'relative_to':relative_to}
        try:
            for level in self.levels:
                number(self.elevation(level))
        except (ValueError, KeyError, RecursionError):
            self.levels = old
            raise ValueError('Invalid level reference, cycle, or elevation.') from None
        if not self.active:
            self.active = key

    def remove_level(self, key):
        if any(v['relative_to'] == key for v in self.levels.values()) or any(key in g.levels for g in self.grids):
            raise ValueError('This level is referenced by another level or grid.')
        del self.levels[key]
        if self.active == key:
            self.active = next(iter(self.levels), '')

    def save(self, path):
        path = Path(path)
        data = {'version':1, 'levels':self.levels, 'active':self.active,
                'grids':[asdict(g) for g in self.grids]}
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as f:
                temp = f.name
                json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
                f.flush(); os.fsync(f.fileno())
            os.replace(temp, path)
        finally:
            if temp and os.path.exists(temp): os.unlink(temp)

    @classmethod
    def load(cls, path):
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            if data['version'] != 1: raise ValueError('Unsupported settings version.')
            w = cls()
            raw = data['levels']
            if not isinstance(raw, dict) or len(raw) > 500: raise ValueError('Invalid levels.')
            w.levels = {name(k):{'offset':str(number(v['offset'])), 'relative_to':v['relative_to']} for k,v in raw.items()}
            for key in w.levels: number(w.elevation(key))
            w.active = data['active']
            if w.active and w.active not in w.levels: raise ValueError('Unknown active level.')
            if len(data['grids']) > 100: raise ValueError('Too many grid sets.')
            w.grids = [Grid(**g) for g in data['grids']]
            if len({g.name for g in w.grids}) != len(w.grids): raise ValueError('Duplicate grid names.')
            for g in w.grids:
                for key in g.levels: w.elevation(key)
            return w
        except (KeyError, TypeError, RecursionError, json.JSONDecodeError) as exc:
            raise ValueError('Invalid GCStructFlow settings file.') from exc


def point(p):
    if len(p) != 3: raise ValueError('A point requires X, Y and Z.')
    return tuple(float(number(v)) for v in p)


def column(x, y, bottom, top):
    if number(top) <= number(bottom): raise ValueError('Top level must be above bottom level.')
    return [point((x,y,bottom)), point((x,y,top))]


def wall(x1, y1, x2, y2, bottom, top):
    a,b = column(x1,y1,bottom,top)
    c,d = column(x2,y2,bottom,top)
    return panel([a,c,d,b])


def panel(points):
    pts = [point(p) for p in points]
    if len(pts) > 3 and pts[0] == pts[-1]: pts.pop()
    if not 3 <= len(pts) <= 500: raise ValueError('A panel needs 3–500 perimeter points.')
    if any(math.dist(a,b) < 1e-8 for i,a in enumerate(pts) for b in pts[i+1:]):
        raise ValueError('Panel contains repeated points.')
    # Newell normal is stable for concave, simple polygons.
    normal = [0.,0.,0.]
    for a,b in zip(pts,pts[1:]+pts[:1]):
        normal[0] += (a[1]-b[1])*(a[2]+b[2])
        normal[1] += (a[2]-b[2])*(a[0]+b[0])
        normal[2] += (a[0]-b[0])*(a[1]+b[1])
    length = math.sqrt(sum(v*v for v in normal))
    if length < 1e-10: raise ValueError('Panel has zero area or a crossed perimeter.')
    n = [v/length for v in normal]
    if any(abs(sum(n[k]*(p[k]-pts[0][k]) for k in range(3))) > 1e-7 for p in pts):
        raise ValueError('Panel is not planar. Divide a warped surface into planar panels.')
    drop = max(range(3), key=lambda k:abs(n[k]))
    flat = [tuple(v for k,v in enumerate(p) if k!=drop) for p in pts]
    def orient(a,b,c): return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def on(a,b,c):
        return abs(orient(a,b,c)) < 1e-10 and all(min(a[k],b[k])-1e-10<=c[k]<=max(a[k],b[k])+1e-10 for k in (0,1))
    def intersects(a,b,c,d):
        return (orient(a,b,c)*orient(a,b,d)<0 and orient(c,d,a)*orient(c,d,b)<0) or any((on(a,b,c),on(a,b,d),on(c,d,a),on(c,d,b)))
    count = len(flat)
    for i in range(count):
        for j in range(i+1,count):
            if j == i+1 or (i==0 and j==count-1): continue
            if intersects(flat[i],flat[(i+1)%count],flat[j],flat[(j+1)%count]):
                raise ValueError('Panel perimeter crosses or touches itself.')
    return pts


def matching_node(nodes, p):
    found = [key for key,xyz in nodes.items() if math.dist(xyz,p) <= 1e-8]
    if len(found)>1: raise ValueError(f'Multiple nodes occupy this position: {found}. Review before drawing.')
    return found[0] if found else None
