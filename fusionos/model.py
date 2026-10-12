"""Parametric BRep document. JSON data only: no embedded executable scripts."""
from __future__ import annotations

import base64
import copy
import io
import json
import math
import os
from pathlib import Path
import tempfile
import uuid

import cadquery as cq
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

FORMAT = "fusionos-project"
VERSION = 1
MAX_PROJECT_BYTES = 50 * 1024 * 1024


def exact_bounds(shape):
    """Do not let display tessellation enlarge measured dimensions."""
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped,box,False,False)
    return cq.BoundBox(box)


def number(params, key, positive=False):
    value = params[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key}: serve un numero.")
    if not math.isfinite(value) or abs(value) > 1e6 or (positive and value <= 0):
        raise ValueError(f"{key}: valore non valido (limite ±1.000.000 mm/gradi).")
    return float(value)


def build(node, shapes):
    kind, p = node["kind"], node["params"]
    inputs = [shapes[key] for key in node["inputs"]]
    counts = {"sketch": 0, "box": 0, "cylinder": 0, "sphere": 0, "import": 0,
              "extrude": 1, "revolve": 1, "fillet": 1, "chamfer": 1,
              "translate": 1, "rotate": 1, "mirror": 1, "shell": 1,
              "union": 2, "cut": 2, "intersect": 2, "loft": 2, "stock": 1, "pattern": 1}
    if kind not in counts or len(inputs) != counts[kind]:
        raise ValueError("Operazione o numero di riferimenti non valido: " + kind)
    n = lambda key, positive=False: number(p, key, positive)
    if kind == "sketch":
        profile = p["profile"]
        wp = cq.Workplane("XY")
        if profile == "rectangle":
            wire = wp.rect(n("width", True), n("height", True)).val()
        elif profile == "circle":
            wire = wp.circle(n("radius", True)).val()
        elif profile == "polygon":
            raw = p["points"]
            if not isinstance(raw, list) or not 3 <= len(raw) <= 1000:
                raise ValueError("Il poligono deve avere da 3 a 1000 punti.")
            points = []
            for point in raw:
                if not isinstance(point, list) or len(point) != 2:
                    raise ValueError("Ogni punto richiede X e Y.")
                points.append((number({"x": point[0]}, "x"), number({"y": point[1]}, "y")))
            wire = wp.polyline(points).close().val()
        else:
            raise ValueError("Profilo non supportato.")
        result = cq.Face.makeFromWires(wire).translate((n("x"), n("y"), n("z")))
    elif kind == "box":
        result = cq.Workplane("XY").box(n("length", True), n("width", True), n("height", True)).val()
    elif kind == "cylinder":
        result = cq.Workplane("XY").circle(n("radius", True)).extrude(n("height", True)).val()
    elif kind == "sphere":
        result = cq.Workplane("XY").sphere(n("radius", True)).val()
    elif kind == "import":
        result = cq.Shape.importBrep(io.BytesIO(base64.b64decode(p["brep"], validate=True)))
    elif kind in ("extrude", "revolve"):
        if not isinstance(inputs[0], cq.Face):
            raise ValueError("Seleziona uno schizzo piano.")
        face = inputs[0]
        if kind == "extrude":
            result = cq.Solid.extrudeLinear(face.outerWire(), face.innerWires(), cq.Vector(0, 0, n("height", True)))
        else:
            angle = n("angle", True)
            if angle > 360:
                raise ValueError("Angolo massimo: 360°.")
            # Revolve around the global Y axis; offset sketch X to avoid crossing it.
            result = cq.Solid.revolve(face.outerWire(), face.innerWires(), angle,
                                      cq.Vector(0, 0, 0), cq.Vector(0, 1, 0))
    elif kind == "loft":
        if not all(isinstance(s, cq.Face) for s in inputs):
            raise ValueError("Il loft richiede due schizzi su quote Z diverse.")
        result = cq.Solid.makeLoft([s.outerWire() for s in inputs], ruled=bool(p.get("ruled", False)))
    elif kind in ("union", "cut", "intersect"):
        if not all(s.Solids() for s in inputs):
            raise ValueError("Le operazioni booleane richiedono due solidi.")
        result = getattr(inputs[0], {"union":"fuse", "cut":"cut", "intersect":"intersect"}[kind])(inputs[1]).clean()
    elif kind in ("fillet", "chamfer"):
        shape = inputs[0]
        solids = shape.Solids()
        if len(solids) != 1:
            raise ValueError("La finitura richiede un singolo solido.")
        shape = solids[0]
        edges = shape.Edges()
        indices = p.get("edges", [])
        if not isinstance(indices, list) or any(type(i) is not int or i < 1 or i > len(edges) for i in indices):
            raise ValueError("Indice spigolo non valido (numerazione da 1).")
        chosen = [edges[i-1] for i in sorted(set(indices))] if indices else edges
        result = shape.fillet(n("radius", True), chosen) if kind == "fillet" else shape.chamfer(n("distance", True), None, chosen)
    elif kind == "shell":
        solids = inputs[0].Solids()
        if len(solids) != 1:
            raise ValueError("Lo svuotamento richiede un singolo solido.")
        index = p["face"]
        faces = solids[0].Faces()
        if type(index) is not int or index < 1 or index > len(faces):
            raise ValueError("Indice faccia non valido (numerazione da 1).")
        result = solids[0].shell([faces[index-1]], -n("thickness", True))
    elif kind == "stock":
        margin = n("allowance")
        if margin < 0 or not inputs[0].Solids():
            raise ValueError("Il sovrametallo deve essere non negativo e il riferimento un solido.")
        box = exact_bounds(inputs[0])
        result = cq.Solid.makeBox(box.xlen+2*margin, box.ylen+2*margin, box.zlen+2*margin,
                                 cq.Vector(box.xmin-margin,box.ymin-margin,box.zmin-margin))
    elif kind == "pattern":
        count = p["count"]
        if type(count) is not int or not 2 <= count <= 100:
            raise ValueError("La serie deve contenere da 2 a 100 elementi.")
        if not inputs[0].Solids():
            raise ValueError("La serie richiede un solido.")
        delta = (n("x"),n("y"),n("z"))
        if not any(delta):
            raise ValueError("Il passo della serie deve essere diverso da zero.")
        result = cq.Compound.makeCompound([inputs[0].translate(tuple(i*v for v in delta)) for i in range(count)])
    elif kind == "translate":
        result = inputs[0].translate((n("x"), n("y"), n("z")))
    elif kind == "rotate":
        axis = p["axis"]
        if axis not in ("X", "Y", "Z"):
            raise ValueError("Asse non valido.")
        result = inputs[0].rotate((0, 0, 0), {"X":(1,0,0), "Y":(0,1,0), "Z":(0,0,1)}[axis], n("angle"))
    elif kind == "mirror":
        if p["plane"] not in ("XY", "XZ", "YZ"):
            raise ValueError("Piano non valido.")
        result = inputs[0].mirror(p["plane"])
    if result.isNull() or not result.isValid():
        raise ValueError("Geometria non valida. Controlla quote, intersezioni e selezioni.")
    is_surface = kind == "sketch" or (kind in ("translate", "rotate", "mirror") and not inputs[0].Solids())
    if not is_surface and (not result.Solids() or result.Volume() <= 1e-12):
        raise ValueError("L'operazione non produce un solido: controlla le intersezioni.")
    return result


class Document:
    def __init__(self):
        self.nodes = []
        self.shapes = {}
        self._undo = []
        self._redo = []

    @staticmethod
    def evaluate(nodes):
        if not isinstance(nodes, list) or len(nodes) > 1000:
            raise ValueError("Progetto non valido o oltre 1000 operazioni.")
        shapes = {}
        for node in nodes:
            if not isinstance(node, dict) or set(node) != {"id", "kind", "name", "params", "inputs", "visible"}:
                raise ValueError("Struttura operazione non valida.")
            if not all(isinstance(node[key], str) for key in ("id", "kind", "name")):
                raise ValueError("Identificatore o nome non valido.")
            if node["id"] in shapes or not node["id"]:
                raise ValueError("Identificatore duplicato o vuoto.")
            if not isinstance(node["params"], dict) or not isinstance(node["inputs"], list) or type(node["visible"]) is not bool:
                raise ValueError("Parametri o visibilità non validi.")
            if any(not isinstance(ref, str) or ref not in shapes for ref in node["inputs"]):
                raise ValueError("Riferimento mancante o circolare.")
            try:
                shapes[node["id"]] = build(node, shapes)
            except Exception as exc:
                raise ValueError(f'{node["name"]}: {exc}') from exc
        return shapes

    def _commit(self, nodes):
        shapes = self.evaluate(nodes)  # Build before replacing any live state.
        self._undo.append(copy.deepcopy(self.nodes))
        self._undo = self._undo[-50:]
        self._redo.clear()
        self.nodes, self.shapes = nodes, shapes

    def add(self, kind, params, inputs=(), name=None):
        nodes = copy.deepcopy(self.nodes)
        key = uuid.uuid4().hex
        for node in nodes:
            if node["id"] in inputs:
                node["visible"] = False
        nodes.append({"id": key, "kind": kind, "name": name or kind,
                      "params": copy.deepcopy(params), "inputs": list(inputs), "visible": True})
        self._commit(nodes)
        return key

    def update(self, key, params=None, name=None):
        nodes = copy.deepcopy(self.nodes)
        node = next(n for n in nodes if n["id"] == key)
        if params is not None:
            node["params"] = copy.deepcopy(params)
        if name is not None:
            node["name"] = name
        self._commit(nodes)

    def set_visible(self, key, value):
        nodes = copy.deepcopy(self.nodes)
        next(n for n in nodes if n["id"] == key)["visible"] = bool(value)
        # Visibility doesn't change the kernel model.
        self._undo.append(copy.deepcopy(self.nodes))
        self._undo = self._undo[-50:]
        self._redo.clear()
        self.nodes = nodes

    def remove(self, key):
        if any(key in node["inputs"] for node in self.nodes):
            raise ValueError("Prima elimina le operazioni che dipendono da questa.")
        self._commit([copy.deepcopy(n) for n in self.nodes if n["id"] != key])

    def undo(self):
        if self._undo:
            nodes = self._undo[-1]
            shapes = self.evaluate(nodes)
            self._undo.pop()
            self._redo.append(copy.deepcopy(self.nodes))
            self.nodes, self.shapes = nodes, shapes

    def redo(self):
        if self._redo:
            nodes = self._redo[-1]
            shapes = self.evaluate(nodes)
            self._redo.pop()
            self._undo.append(copy.deepcopy(self.nodes))
            self.nodes, self.shapes = nodes, shapes

    def save(self, filename):
        path = Path(filename)
        payload = json.dumps({"format": FORMAT, "version": VERSION, "units": "mm", "nodes": self.nodes},
                             ensure_ascii=False, indent=2, allow_nan=False)
        if len(payload.encode("utf-8")) > MAX_PROJECT_BYTES:
            raise ValueError("Il progetto supera il limite di 50 MiB di questa versione.")
        fd, temp = tempfile.mkstemp(prefix=".fusionos-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(payload)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    @classmethod
    def load(cls, filename):
        if Path(filename).stat().st_size > MAX_PROJECT_BYTES:
            raise ValueError("File oltre il limite di 50 MiB.")
        payload = json.loads(Path(filename).read_text(encoding="utf-8"))
        if (not isinstance(payload, dict) or payload.get("format") != FORMAT
                or payload.get("version") != VERSION or payload.get("units") != "mm"):
            raise ValueError("Formato, versione o unità del progetto non supportati.")
        doc = cls()
        nodes = payload["nodes"]
        doc.shapes = cls.evaluate(nodes)
        doc.nodes = nodes
        return doc

    def import_step(self, filename):
        imported = cq.importers.importStep(str(filename))
        shape = cq.Compound.makeCompound(imported.vals())
        stream = io.BytesIO()
        shape.exportBrep(stream)
        return self.add("import", {"brep": base64.b64encode(stream.getvalue()).decode("ascii")},
                        name=Path(filename).stem)

    def export(self, filename, keys):
        if not keys:
            raise ValueError("Seleziona almeno un solido da esportare.")
        if any(not self.shapes[key].Solids() for key in keys):
            raise ValueError("Seleziona solidi, non schizzi.")
        suffix = Path(filename).suffix.lower()
        formats = {".step": "STEP", ".stp": "STEP", ".stl": "STL", ".brep": "BREP"}
        if suffix not in formats:
            raise ValueError("Usa .step, .stl oppure .brep.")
        shape = cq.Compound.makeCompound([self.shapes[key] for key in keys])
        cq.exporters.export(shape, str(filename), exportType=formats[suffix])
