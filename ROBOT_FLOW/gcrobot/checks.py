"""Read-only geometry checks; no structural adequacy conclusions."""
from dataclasses import dataclass
from collections import defaultdict
from itertools import product
import math

@dataclass
class Issue:
    code: str
    kind: str
    ids: tuple
    message: str


def inspect_model(nodes, bars, levels, tolerance=0.001):
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('Tolerance must be finite and positive, in metres.')
    issues = []
    buckets = defaultdict(list)
    for key, p in nodes.items():
        cell = tuple(math.floor(v/tolerance) for v in p)
        for delta in product((-1,0,1),repeat=3):
            for other in buckets[tuple(a+b for a,b in zip(cell,delta))]:
                distance = math.dist(p,nodes[other])
                if distance <= tolerance:
                    issues.append(Issue('near_nodes','node',(other,key),f'Nodes {other}, {key}: {distance:.6g} m apart.'))
        buckets[cell].append(key)
        if levels:
            distance = min(abs(p[2]-float(z)) for z in levels)
            if 1e-8 < distance <= tolerance:
                issues.append(Issue('off_level','node',(key,),f'Node {key}: {distance:.6g} m from a reference level.'))
    seen = {}
    for key,(start,end,section) in bars.items():
        if not section:
            issues.append(Issue('missing_section','bar',(key,),f'Bar {key}: no section label.'))
        if start not in nodes or end not in nodes:
            issues.append(Issue('missing_node','bar',(key,),f'Bar {key}: endpoint missing from node snapshot.'))
            continue
        if math.dist(nodes[start],nodes[end]) <= 1e-8:
            issues.append(Issue('zero_length','bar',(key,),f'Bar {key}: zero length.'))
        signature = tuple(sorted((nodes[start],nodes[end])))
        if signature in seen:
            issues.append(Issue('duplicate_bar','bar',(seen[signature],key),f'Bars {seen[signature]}, {key}: identical endpoints.'))
        else: seen[signature] = key
    return issues
