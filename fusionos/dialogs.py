import copy
from PySide6 import QtWidgets

LABELS = {"length":"Lunghezza", "width":"Larghezza", "height":"Altezza / profondità",
          "radius":"Raggio", "x":"X", "y":"Y", "z":"Z", "angle":"Angolo (°)",
          "distance":"Distanza", "thickness":"Spessore", "face":"Indice faccia (da 1)",
          "edges":"Spigoli (1,2,…; vuoto = tutti)", "axis":"Asse globale", "plane":"Piano globale",
          "points":"Vertici XY — una coppia X,Y per riga", "ruled":"Superficie rigata",
          "allowance":"Sovrametallo per lato (mm)", "count":"Numero elementi"}


class ParametersDialog(QtWidgets.QDialog):
    def __init__(self, title, params, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title + " · mm")
        self.params = copy.deepcopy(params)
        self.fields = {}
        form = QtWidgets.QFormLayout(self)
        for key, value in params.items():
            if key in ("profile", "brep"):
                continue
            if isinstance(value, bool):
                field = QtWidgets.QCheckBox()
                field.setChecked(value)
            elif key in ("axis", "plane"):
                field = QtWidgets.QComboBox()
                field.addItems(["X","Y","Z"] if key == "axis" else ["XY","XZ","YZ"])
                field.setCurrentText(value)
            elif key == "points":
                field = QtWidgets.QPlainTextEdit("\n".join(f"{x},{y}" for x,y in value))
            elif key == "edges":
                field = QtWidgets.QLineEdit(",".join(map(str,value)))
            elif key in ("face", "count"):
                field = QtWidgets.QSpinBox()
                field.setRange(1,100000)
                field.setValue(value)
            else:
                field = QtWidgets.QDoubleSpinBox()
                field.setDecimals(4)
                field.setRange(-1e6,1e6)
                field.setValue(value)
            form.addRow(LABELS.get(key,key),field)
            self.fields[key] = field
        self.error = QtWidgets.QLabel()
        self.error.setWordWrap(True)
        form.addRow(self.error)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def validate(self):
        try:
            for key,field in self.fields.items():
                if key == "points":
                    self.params[key] = [[float(v.strip()) for v in line.split(",")] for line in field.toPlainText().splitlines() if line.strip()]
                    if any(len(point) != 2 for point in self.params[key]):
                        raise ValueError("Scrivi due coordinate X,Y per ogni riga.")
                elif key == "edges":
                    self.params[key] = [int(v.strip()) for v in field.text().split(",") if v.strip()]
                elif isinstance(field, QtWidgets.QCheckBox):
                    self.params[key] = field.isChecked()
                elif isinstance(field, QtWidgets.QComboBox):
                    self.params[key] = field.currentText()
                else:
                    self.params[key] = field.value()
            self.accept()
        except ValueError as exc:
            self.error.setText(str(exc))
