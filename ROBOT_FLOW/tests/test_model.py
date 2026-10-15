import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from gcrobot.model import number, Workspace, Grid, panel, wall, column, matching_node
from gcrobot.checks import inspect_model

class ModelTests(unittest.TestCase):
    def test_decimal_comma_and_precision(self):
        self.assertEqual(number('-1,370123'), Decimal('-1.370123'))
        for value in ('NaN', 'Infinity', '1,234.56', '', True):
            with self.assertRaises(ValueError): number(value)

    def test_relative_levels_and_cycle_rejection(self):
        w = Workspace()
        w.set_level('Deck', '0.23')
        w.set_level('Bottom', '-1.45', 'Deck')
        self.assertEqual(w.elevation('Bottom'), Decimal('-1.22'))
        with self.assertRaises(ValueError): w.set_level('Deck', '0', 'Bottom')
        self.assertEqual(w.elevation('Deck'), Decimal('0.23'))

    def test_grid_rotation_and_decimal_axes(self):
        g = Grid('Pool', ['0', '2.37'], ['0', '4.12'], '10', '20', '90')
        x, y = g.point('2.37', '4.12')
        self.assertAlmostEqual(x, 5.88)
        self.assertAlmostEqual(y, 22.37)
        with self.assertRaises(ValueError): Grid('Bad', ['0','0'], ['0','1'])

    def test_geometry_and_invalid_panels(self):
        self.assertEqual(column('2','3','-1.37','0.23'), [(2.,3.,-1.37),(2.,3.,0.23)])
        self.assertEqual(wall('0','0','4','0','-1.37','0.23')[2], (4.,0.,0.23))
        self.assertEqual(len(panel([(0,0,0),(4,0,0),(4,3,1),(0,3,1)])), 4)
        for points in ([(0,0,0),(1,0,0),(2,0,0)],
                       [(0,0,0),(1,0,0),(1,1,1),(0,1,0)],
                       [(0,0,0),(2,2,0),(0,2,0),(2,0,0)]):
            with self.assertRaises(ValueError): panel(points)
        with self.assertRaises(ValueError): column(0,0,1,1)

    def test_node_reuse_is_not_nearby_merge(self):
        nodes = {1:(0,0,0), 2:(0.001,0,0)}
        self.assertEqual(matching_node(nodes, (0,0,0)), 1)
        self.assertIsNone(matching_node(nodes, (0.0005,0,0)))
        with self.assertRaises(ValueError): matching_node({1:(0,0,0),2:(0,0,0)}, (0,0,0))

    def test_persistence_and_invalid_schema(self):
        w = Workspace(); w.set_level('Pool', '-1.370123')
        w.grids.append(Grid('Walls',['0','2'],['0','3']))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'project.json'; w.save(p)
            restored = Workspace.load(p)
            self.assertEqual(restored.elevation('Pool'), Decimal('-1.370123'))
            self.assertEqual(restored.grids[0].name,'Walls')
            p.write_text('{"version":99}')
            with self.assertRaises(ValueError): Workspace.load(p)

    def test_diagnostics_do_not_modify_model(self):
        nodes = {1:(0,0,0),2:(1,0,0),3:(0.0008,0,0),4:(0,0,0.0007)}
        bars = {10:(1,2,'R'),11:(2,1,'R'),12:(1,1,'')}
        original = dict(nodes)
        issues = inspect_model(nodes,bars,[0.0],0.001)
        codes = {i.code for i in issues}
        self.assertTrue({'near_nodes','duplicate_bar','zero_length','missing_section','off_level'} <= codes)
        self.assertEqual(nodes,original)
        for tol in (0,-1,float('nan')):
            with self.assertRaises(ValueError): inspect_model(nodes,bars,[],tol)

if __name__ == '__main__': unittest.main()
