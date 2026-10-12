from __future__ import annotations

import sys
import uuid
from datetime import datetime
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
from .model import Document, exact_bounds
from .dialogs import ParametersDialog
from .viewport import Viewport
from .settings import Settings, material_estimate


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.doc = Document()
        self.path = None
        self.dirty = False
        self._refreshing = False
        self.settings = Settings()
        self.session_id = uuid.uuid4().hex[:10]
        self.resize(1380,860)
        self.setWindowTitle("fusionOS — Nuovo progetto")
        self.viewport = Viewport()
        self.setCentralWidget(self.viewport)
        self.viewport.picked.connect(self.pick)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["BROWSER · operazioni", "Tipo"])
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(self.selection_changed)
        self.tree.itemChanged.connect(self.visibility_changed)
        self.tree.itemDoubleClicked.connect(lambda *_:self.guard(self.edit))
        self.dock("Browser",self.tree,QtCore.Qt.LeftDockWidgetArea)
        inspector = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(inspector)
        self.details = QtWidgets.QLabel("Seleziona un oggetto per leggere le proprietà.")
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        layout.addWidget(self.details)
        edit = QtWidgets.QPushButton("Modifica parametri…")
        edit.clicked.connect(lambda:self.guard(self.edit))
        layout.addWidget(edit)
        layout.addStretch()
        self.dock("Proprietà",inspector,QtCore.Qt.RightDockWidgetArea)
        self.timeline = QtWidgets.QListWidget()
        self.timeline.setFlow(QtWidgets.QListView.LeftToRight)
        self.timeline.setMaximumHeight(92)
        self.timeline.itemClicked.connect(lambda item:self.pick(item.data(QtCore.Qt.UserRole)))
        self.dock("CRONOLOGIA · clicca per selezionare, doppio click nel browser per modificare",
                  self.timeline,QtCore.Qt.BottomDockWidgetArea)
        self.make_actions()
        self.backup_timer = QtCore.QTimer(self)
        self.backup_timer.timeout.connect(self.auto_backup)
        self.apply_settings()
        self.statusBar().showMessage("OFFLINE  ·  mm  ·  Motore Open CASCADE  ·  Prototipo 0.1")
        self.setStyleSheet("QMainWindow{background:#eef2f6;} QToolBar{background:#fff;spacing:6px;padding:7px;border-bottom:1px solid #ccd7e1;}"
                           "QToolButton{padding:7px;border-radius:4px;} QToolButton:hover{background:#deedf8;}"
                           "QDockWidget{font-weight:600;} QTreeWidget,QListWidget{background:#f8fafc;border:0;}"
                           "QPushButton{padding:7px;} QStatusBar{background:#172c40;color:#dce8f3;}")

    def dock(self,title,widget,area):
        dock = QtWidgets.QDockWidget(title,self)
        dock.setObjectName(title)
        dock.setWidget(widget)
        self.addDockWidget(area,dock)
        return dock

    def action(self,container,label,callback,shortcut=None):
        action = QtGui.QAction(label,self)
        if shortcut:
            action.setShortcut(shortcut)
        action.triggered.connect(lambda checked=False:self.guard(callback))
        container.addAction(action)
        return action

    def make_actions(self):
        file = self.menuBar().addMenu("File")
        for label,fn,shortcut in (("Nuovo",self.new,"Ctrl+N"),("Apri…",self.open,"Ctrl+O"),
                                   ("Salva",self.save,"Ctrl+S"),("Salva con nome…",lambda:self.save(True),"Ctrl+Shift+S"),
                                   ("Importa STEP…",self.import_step,None),("Esporta selezione…",self.export,None)):
            self.action(file,label,fn,shortcut)
        edit = self.menuBar().addMenu("Modifica")
        self.action(edit,"Annulla",lambda:self.history(False),"Ctrl+Z")
        self.action(edit,"Ripeti",lambda:self.history(True),"Ctrl+Y")
        self.action(edit,"Parametri…",self.edit,"Enter")
        self.action(edit,"Elimina operazione",self.remove,"Delete")
        tools = self.addToolBar("CREA")
        self.action(tools,"▱ Schizzo rettangolo",lambda:self.create("sketch",{"profile":"rectangle","width":60.,"height":40.,"x":0.,"y":0.,"z":0.},0,"Schizzo rettangolo"))
        self.action(tools,"◯ Cerchio",lambda:self.create("sketch",{"profile":"circle","radius":15.,"x":0.,"y":0.,"z":0.},0,"Schizzo cerchio"))
        self.action(tools,"Poligono",lambda:self.create("sketch",{"profile":"polygon","points":[[0,0],[40,0],[40,20],[20,30],[0,20]],"x":0.,"y":0.,"z":0.},0,"Schizzo poligono"))
        tools.addSeparator()
        for label,kind,params in (("Box","box",{"length":60.,"width":40.,"height":20.}),
                                   ("Cilindro","cylinder",{"radius":10.,"height":30.}),
                                   ("Sfera","sphere",{"radius":15.})):
            self.action(tools,label,lambda k=kind,p=params,l=label:self.create(k,p,0,l))
        self.addToolBarBreak()
        tools = self.addToolBar("MODELLAZIONE")
        specs = (("Estrudi","extrude",{"height":20.},1),
                 ("Rivoluzione Y","revolve",{"angle":360.},1),
                 ("Loft","loft",{"ruled":False},2),
                 ("Unione","union",{},2),("Sottrai","cut",{},2),("Intersezione","intersect",{},2),
                 ("Raccordo","fillet",{"radius":2.,"edges":[]},1),
                 ("Smusso","chamfer",{"distance":1.,"edges":[]},1),
                 ("Svuota","shell",{"thickness":2.,"face":6},1))
        for label,kind,params,count in specs:
            self.action(tools,label,lambda k=kind,p=params,c=count,l=label:self.create(k,p,c,l))
        transform = self.menuBar().addMenu("Trasforma")
        for label,kind,params in (("Sposta","translate",{"x":10.,"y":0.,"z":0.}),
                                   ("Ruota","rotate",{"axis":"Z","angle":45.}),
                                   ("Specchia","mirror",{"plane":"YZ"})):
            self.action(transform,label,lambda k=kind,p=params,l=label:self.create(k,p,1,l))
        view = self.menuBar().addMenu("Vista")
        self.action(view,"Adatta",self.viewport.fit,"F")
        for label,name in (("Isometrica","iso"),("Superiore","top"),("Frontale","front"),("Destra","right")):
            self.action(view,label,lambda n=name:self.viewport.view(n))
        help_menu = self.menuBar().addMenu("Aiuto")
        self.action(help_menu,"Guida rapida",self.help)
        workshop = self.menuBar().addMenu("Officina")
        self.action(workshop,"Grezzo con sovrametallo…",lambda:self.create("stock",{"allowance":2.},1,"Grezzo"))
        self.action(workshop,"Serie lineare…",lambda:self.create("pattern",{"count":3,"x":80.,"y":0.,"z":0.},1,"Serie lineare"))
        self.action(workshop,"Salva variante…",self.save_variant)
        self.action(workshop,"Confronta con variante…",self.compare_variant)
        self.action(workshop,"Apri cartella backup",self.open_backups)
        self.action(workshop,"Impostazioni…",self.preferences)

    def guard(self,callback):
        try:
            return callback()
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self,"Operazione non completata",str(exc))

    def selected(self):
        # Stable browser order, independent of Qt's selectedItems ordering.
        keys = {item.data(0,QtCore.Qt.UserRole) for item in self.tree.selectedItems()}
        return [node["id"] for node in self.doc.nodes if node["id"] in keys]

    def create(self,kind,params,count,label):
        keys = self.selected() if count else []
        if len(keys) != count:
            raise ValueError(f"Seleziona {count} oggetto/i nel browser (Ctrl per selezione multipla).")
        if kind == "cut":
            names = {n["id"]:n["name"] for n in self.doc.nodes}
            choice,ok = QtWidgets.QInputDialog.getItem(self,"Sottrazione", "Quale corpo conservare come base?",
                [f"{i+1} · {names[key]}" for i,key in enumerate(keys)],0,False)
            if not ok:
                return
            if choice.startswith("2"):
                keys.reverse()
        if params:
            dialog = ParametersDialog(label,params,self)
            if dialog.exec() != QtWidgets.QDialog.Accepted:
                return
            params = dialog.params
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            key = self.doc.add(kind,params,keys,label)
            self.dirty = True
            self.refresh(key,fit=True)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def refresh(self,selected=None,fit=False):
        self._refreshing = True
        try:
            self.tree.clear()
            self.timeline.clear()
            for i,node in enumerate(self.doc.nodes):
                item = QtWidgets.QTreeWidgetItem([node["name"],node["kind"]])
                item.setData(0,QtCore.Qt.UserRole,node["id"])
                item.setFlags(item.flags()|QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(0,QtCore.Qt.Checked if node["visible"] else QtCore.Qt.Unchecked)
                self.tree.addTopLevelItem(item)
                item.setSelected(node["id"] == selected)
                step = QtWidgets.QListWidgetItem(f"{i+1:02d}  {node['name']}   →")
                step.setData(QtCore.Qt.UserRole,node["id"])
                self.timeline.addItem(step)
            self.tree.resizeColumnToContents(0)
        finally:
            self._refreshing = False
        self.viewport.set_shapes({n["id"]:self.doc.shapes[n["id"]] for n in self.doc.nodes if n["visible"]},self.selected())
        if fit:
            self.viewport.fit()
        self.selection_changed()
        self.update_title()

    def selection_changed(self):
        if self._refreshing:
            return
        keys = self.selected()
        self.viewport.selected = set(keys)
        self.viewport.update()
        if len(keys) == 1:
            shape = self.doc.shapes[keys[0]]
            box = exact_bounds(shape)
            self.details.setText(f"Ingombro (mm)\nX  {box.xlen:.3f}\nY  {box.ylen:.3f}\nZ  {box.zlen:.3f}\n\n"
                                 f"Volume  {shape.Volume() if shape.Solids() else 0:.3f} mm³\n"
                                 f"Area  {shape.Area():.3f} mm²\nFacce  {len(shape.Faces())}\nSpigoli  {len(shape.Edges())}")
            if shape.Solids():
                mass,cost = material_estimate(shape.Volume(),self.settings.value("density",2.7),self.settings.value("price_per_kg",0.0))
                self.details.setText(self.details.text()+f"\n\nStima materiale\nMassa  {mass:.4f} kg\nCosto  {cost:.2f} €\n"
                    f"Densità  {self.settings.value('density',2.7):.3f} g/cm³\nPrezzo  {self.settings.value('price_per_kg',0.0):.2f} €/kg")
        else:
            self.details.setText(f"{len(keys)} oggetti selezionati.\nCtrl+click nel browser per selezionare più oggetti.")

    def pick(self,key):
        self.tree.clearSelection()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(0,QtCore.Qt.UserRole) == key:
                item.setSelected(True)
                self.tree.scrollToItem(item)

    def visibility_changed(self,item,column):
        if not self._refreshing:
            key = item.data(0,QtCore.Qt.UserRole)
            self.doc.set_visible(key,item.checkState(0) == QtCore.Qt.Checked)
            self.dirty = True
            self.guard(lambda:self.refresh(key))

    def edit(self):
        keys = self.selected()
        if len(keys) != 1:
            raise ValueError("Seleziona una sola operazione da modificare.")
        node = next(n for n in self.doc.nodes if n["id"] == keys[0])
        if node["kind"] == "import" or not node["params"]:
            raise ValueError("Questa operazione non ha quote modificabili. Modifica le operazioni a monte.")
        dialog = ParametersDialog(node["name"],node["params"],self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.doc.update(keys[0],params=dialog.params)
            self.dirty = True
            self.refresh(keys[0])

    def remove(self):
        keys = self.selected()
        if len(keys) != 1:
            raise ValueError("Seleziona una sola operazione da eliminare.")
        self.doc.remove(keys[0])
        self.dirty = True
        self.refresh()

    def history(self,redo):
        if not (self.doc._redo if redo else self.doc._undo):
            return
        self.doc.redo() if redo else self.doc.undo()
        self.dirty = True
        self.refresh()

    def update_title(self):
        self.setWindowTitle(f"fusionOS — {self.path.name if self.path else 'Nuovo progetto'}{' *' if self.dirty else ''}")

    def maybe_save(self):
        if not self.dirty:
            return True
        answer = QtWidgets.QMessageBox.question(self,"Modifiche non salvate","Salvare prima di continuare?",
            QtWidgets.QMessageBox.Save|QtWidgets.QMessageBox.Discard|QtWidgets.QMessageBox.Cancel)
        if answer == QtWidgets.QMessageBox.Cancel:
            return False
        return self.save() if answer == QtWidgets.QMessageBox.Save else True

    def new(self):
        if self.maybe_save():
            self.doc,self.path,self.dirty = Document(),None,False
            self.refresh()

    def open(self):
        if not self.maybe_save():
            return
        filename,_ = QtWidgets.QFileDialog.getOpenFileName(self,"Apri progetto","","fusionOS (*.foscad)")
        if filename:
            doc = Document.load(filename)
            self.doc,self.path,self.dirty = doc,Path(filename),False
            self.refresh(fit=True)

    def save(self,as_new=False):
        path = self.path
        if path is None or as_new:
            filename,_ = QtWidgets.QFileDialog.getSaveFileName(self,"Salva progetto","progetto.foscad","fusionOS (*.foscad)")
            if not filename:
                return False
            path = Path(filename)
            if path.suffix.lower() != ".foscad":
                path = Path(str(path)+".foscad")
                if path.exists() and QtWidgets.QMessageBox.question(self,"Sovrascrivere?",str(path)) != QtWidgets.QMessageBox.Yes:
                    return False
        self.doc.save(path)
        self.path,self.dirty = path,False
        self.update_title()
        return True

    def import_step(self):
        filename,_ = QtWidgets.QFileDialog.getOpenFileName(self,"Importa STEP","","STEP (*.step *.stp)")
        if filename:
            key = self.doc.import_step(filename)
            self.dirty = True
            self.refresh(key,fit=True)

    def export(self):
        keys = self.selected()
        if not keys:
            raise ValueError("Seleziona uno o più solidi da esportare.")
        filename,selected_filter = QtWidgets.QFileDialog.getSaveFileName(self,"Esporta solidi","modello.step",
            "STEP (*.step);;STL (*.stl);;BREP (*.brep)")
        if filename:
            if not Path(filename).suffix:
                filename += {"STEP (*.step)":".step","STL (*.stl)":".stl","BREP (*.brep)":".brep"}[selected_filter]
                if Path(filename).exists() and QtWidgets.QMessageBox.question(self,"Sovrascrivere?",filename) != QtWidgets.QMessageBox.Yes:
                    return
            self.doc.export(filename,keys)
            self.statusBar().showMessage("Esportato: " + filename,10000)

    def help(self):
        QtWidgets.QMessageBox.information(self,"fusionOS 0.1 — guida rapida",
            "1. Crea uno schizzo, poi selezionalo e premi Estrudi.\n"
            "2. Le quote sono in millimetri; modifica una lavorazione con doppio click nel browser.\n"
            "3. Per booleani e loft seleziona due oggetti con Ctrl. Per sottrarre scegli il corpo base nel dialogo.\n"
            "4. La rivoluzione usa l'asse Y globale: sposta lo schizzo in X per non attraversare l'asse.\n"
            "5. Per loft crea due schizzi a quote Z diverse.\n"
            "6. Raccordi: spigoli numerati da 1; campo vuoto significa tutti.\n"
            "7. Salva .foscad per mantenere la cronologia; STEP conserva la geometria.\n\n"
            "Prototipo indipendente, non affiliato ad Autodesk. Non legge file .f3d.\n"
            "Schizzi a quote numeriche: solver di vincoli e disegno interattivo non ancora presenti.")

    def apply_settings(self):
        self.viewport.tolerance = (0.6,0.15,0.03)[max(0,min(2,self.settings.value("quality",1)))]
        self.viewport.show_grid = self.settings.value("grid",True)
        minutes = max(0,min(60,self.settings.value("backup_minutes",2)))
        self.backup_timer.stop()
        if minutes:
            self.backup_timer.start(minutes*60000)

    def preferences(self):
        if self.settings.edit(self):
            self.apply_settings()
            self.refresh()

    def backup_directory(self):
        base = Path(QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.AppLocalDataLocation))
        directory = base/"backups"
        directory.mkdir(parents=True,exist_ok=True)
        return directory

    def auto_backup(self):
        if not self.dirty or not self.doc.nodes:
            return
        try:
            directory = self.backup_directory()
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            self.doc.save(directory/f"{self.session_id}-{stamp}.foscad")
            # Retain the latest 10 backups for this running session only.
            for old in sorted(directory.glob(self.session_id+"-*.foscad"))[:-10]:
                old.unlink()
            self.statusBar().showMessage("Backup locale creato. Officina → Apri cartella backup",6000)
        except Exception as exc:
            self.statusBar().showMessage("Backup non riuscito: "+str(exc),15000)

    def open_backups(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.backup_directory())))

    def save_variant(self):
        filename,_ = QtWidgets.QFileDialog.getSaveFileName(self,"Salva copia variante","variante.foscad","fusionOS (*.foscad)")
        if filename:
            if not filename.lower().endswith(".foscad"):
                filename += ".foscad"
                if Path(filename).exists() and QtWidgets.QMessageBox.question(self,"Sovrascrivere?",filename) != QtWidgets.QMessageBox.Yes:
                    return
            self.doc.save(filename)

    def compare_variant(self):
        keys = self.selected()
        if len(keys) != 1:
            raise ValueError("Seleziona un oggetto da confrontare con la stessa operazione nella variante.")
        filename,_ = QtWidgets.QFileDialog.getOpenFileName(self,"Confronta variante","","fusionOS (*.foscad)")
        if not filename:
            return
        other = Document.load(filename)
        if keys[0] not in other.shapes:
            raise ValueError("La variante non contiene la stessa operazione. Salva una variante prima di modificare le quote.")
        current,previous = self.doc.shapes[keys[0]],other.shapes[keys[0]]
        a,b = exact_bounds(current),exact_bounds(previous)
        av = current.Volume() if current.Solids() else 0
        bv = previous.Volume() if previous.Solids() else 0
        rows = [("X (mm)",a.xlen,b.xlen),("Y (mm)",a.ylen,b.ylen),("Z (mm)",a.zlen,b.zlen),("Volume (mm³)",av,bv)]
        html = "<table cellpadding='8'><tr><th>Misura</th><th>Attuale</th><th>Variante</th><th>Differenza</th></tr>"
        for name,value,old in rows:
            html += f"<tr><td>{name}</td><td>{value:.3f}</td><td>{old:.3f}</td><td>{value-old:+.3f}</td></tr>"
        html += "</table><p>Confronto dimensionale e volumetrico; non è un'analisi delle deviazioni superficiali.</p>"
        QtWidgets.QMessageBox.information(self,"Confronto variante",html)

    def closeEvent(self,event):
        try:
            event.accept() if self.maybe_save() else event.ignore()
        except Exception as exc:
            event.ignore()
            QtWidgets.QMessageBox.warning(self,"Salvataggio non riuscito",str(exc))


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("fusionOS")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
