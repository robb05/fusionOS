"""Generate a small editable CNC plate example using the actual CAD kernel."""
from pathlib import Path
from fusionos.model import Document


def demo():
    doc = Document()
    current = doc.add("box",{"length":100.,"width":60.,"height":8.},name="Piastra 100 × 60 × 8")
    current = doc.add("fillet",{"radius":2.,"edges":[]},[current],name="Raccordi R2")
    for i,(x,y) in enumerate(((-38,-18),(38,-18),(38,18),(-38,18)),1):
        tool = doc.add("cylinder",{"radius":3.,"height":12.},name=f"Utensile foro {i}")
        tool = doc.add("translate",{"x":float(x),"y":float(y),"z":-6.},[tool],name=f"Posizione foro {i}")
        current = doc.add("cut",{},[current,tool],name=f"Foro {i} Ø6")
    return doc,current


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1]/"examples"
    target.mkdir(exist_ok=True)
    doc,key = demo()
    doc.save(target/"piastra-cnc.foscad")
    doc.export(target/"piastra-cnc.step",[key])
    print(target)
