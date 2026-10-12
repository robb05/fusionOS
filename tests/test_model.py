import copy
import json
import math
from pathlib import Path
import tempfile
import unittest
from fusionos.model import Document, exact_bounds


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.doc = Document()

    def box(self):
        return self.doc.add("box",{"length":60.,"width":40.,"height":20.})

    def sketch(self,**updates):
        p = {"profile":"rectangle","width":20.,"height":10.,"x":0.,"y":0.,"z":0.}
        p.update(updates)
        return self.doc.add("sketch",p)

    def test_primitives(self):
        box = self.box()
        self.assertAlmostEqual(self.doc.shapes[box].Volume(),48000)
        cylinder = self.doc.add("cylinder",{"radius":5.,"height":10.})
        self.assertAlmostEqual(self.doc.shapes[cylinder].Volume(),250*math.pi)
        sphere = self.doc.add("sphere",{"radius":3.})
        self.assertAlmostEqual(self.doc.shapes[sphere].Volume(),36*math.pi)

    def test_sketch_extrude_edit_rebuild(self):
        sketch = self.sketch()
        result = self.doc.add("extrude",{"height":5.},[sketch])
        self.assertAlmostEqual(self.doc.shapes[result].Volume(),1000)
        p = copy.deepcopy(self.doc.nodes[0]["params"])
        p["width"] = 30
        self.doc.update(sketch,params=p)
        self.assertAlmostEqual(self.doc.shapes[result].Volume(),1500)

    def test_circle_and_polygon_sketches(self):
        c = self.doc.add("sketch",{"profile":"circle","radius":2.,"x":0.,"y":0.,"z":0.})
        solid = self.doc.add("extrude",{"height":3.},[c])
        self.assertAlmostEqual(self.doc.shapes[solid].Volume(),12*math.pi)
        p = self.doc.add("sketch",{"profile":"polygon","points":[[0,0],[10,0],[0,10]],"x":0.,"y":0.,"z":0.})
        solid = self.doc.add("extrude",{"height":2.},[p])
        self.assertAlmostEqual(self.doc.shapes[solid].Volume(),100)

    def test_loft_and_revolve(self):
        a = self.sketch()
        b = self.sketch(z=20.)
        loft = self.doc.add("loft",{"ruled":False},[a,b])
        self.assertAlmostEqual(self.doc.shapes[loft].Volume(),4000,places=5)
        section = self.sketch(width=2.,height=10.,x=5.)
        rev = self.doc.add("revolve",{"angle":360.},[section])
        self.assertAlmostEqual(self.doc.shapes[rev].Volume(),200*math.pi,places=5)

    def test_booleans(self):
        a = self.box()
        b = self.doc.add("translate",{"x":30.,"y":0.,"z":0.},[a])
        cut = self.doc.add("cut",{},[a,b])
        self.assertAlmostEqual(self.doc.shapes[cut].Volume(),24000)
        union = self.doc.add("union",{},[a,b])
        self.assertAlmostEqual(self.doc.shapes[union].Volume(),72000)
        common = self.doc.add("intersect",{},[a,b])
        self.assertAlmostEqual(self.doc.shapes[common].Volume(),24000)

    def test_finishing_and_shell(self):
        a = self.box()
        for kind,p in (("fillet",{"radius":1.,"edges":[]}),
                       ("chamfer",{"distance":1.,"edges":[1]}),
                       ("shell",{"thickness":1.,"face":6})):
            with self.subTest(kind=kind):
                key = self.doc.add(kind,p,[a])
                self.assertTrue(self.doc.shapes[key].isValid())
                self.assertLess(self.doc.shapes[key].Volume(),48000)

    def test_transform_stock_and_pattern(self):
        a = self.box()
        rot = self.doc.add("rotate",{"axis":"Z","angle":90.},[a])
        self.assertAlmostEqual(self.doc.shapes[rot].BoundingBox().xlen,40)
        mirrored = self.doc.add("mirror",{"plane":"YZ"},[a])
        self.assertAlmostEqual(self.doc.shapes[mirrored].Volume(),48000)
        stock = self.doc.add("stock",{"allowance":2.},[a])
        self.assertAlmostEqual(self.doc.shapes[stock].Volume(),64*44*24)
        series = self.doc.add("pattern",{"count":3,"x":80.,"y":0.,"z":0.},[a])
        self.assertEqual(len(self.doc.shapes[series].Solids()),3)
        self.assertAlmostEqual(self.doc.shapes[series].Volume(),144000)

    def test_failed_edit_atomicity(self):
        a = self.box()
        before = copy.deepcopy(self.doc.nodes)
        with self.assertRaises(ValueError):
            self.doc.update(a,{"length":-5,"width":40,"height":20})
        self.assertEqual(self.doc.nodes,before)
        self.assertAlmostEqual(self.doc.shapes[a].Volume(),48000)

    def test_undo_redo_and_dependency_delete(self):
        a = self.box()
        self.doc.add("translate",{"x":20.,"y":0.,"z":0.},[a])
        with self.assertRaises(ValueError):
            self.doc.remove(a)
        self.doc.undo()
        self.assertEqual(len(self.doc.nodes),1)
        self.assertTrue(self.doc.nodes[0]["visible"])
        self.doc.redo()
        self.assertEqual(len(self.doc.nodes),2)

    def test_save_reload_and_step_roundtrip(self):
        a = self.box()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"test.foscad"
            self.doc.save(path)
            other = Document.load(path)
            self.assertEqual(other.nodes,self.doc.nodes)
            step = Path(tmp)/"test.step"
            other.export(step,[a])
            third = Document()
            imported = third.import_step(step)
            step.unlink()  # Embedded BRep must be independent of the original file.
            third.save(path)
            third = Document.load(path)
            self.assertAlmostEqual(third.shapes[imported].Volume(),48000)
            for ext in ("stl","brep"):
                out = Path(tmp)/("test."+ext)
                third.export(out,[imported])
                self.assertGreater(out.stat().st_size,0)

    def test_invalid_graph_and_nonfinite_rejected(self):
        a = self.box()
        invalid = copy.deepcopy(self.doc.nodes)
        invalid[0]["inputs"] = [a]
        with self.assertRaises(ValueError):
            Document.evaluate(invalid)
        with self.assertRaises(ValueError):
            self.doc.add("sphere",{"radius":float("nan")})
        with self.assertRaises(ValueError):
            self.doc.add("pattern",{"count":1001,"x":1.,"y":0.,"z":0.},[a])

    def test_exact_bounds_independent_of_display_mesh(self):
        key = self.doc.add("sphere",{"radius":3.})
        shape = self.doc.shapes[key]
        shape.tessellate(0.6,0.25)
        self.assertAlmostEqual(exact_bounds(shape).xlen,6,places=8)


if __name__ == "__main__":
    unittest.main()
