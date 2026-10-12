"""Local preferences only. No account, web requests or cloud storage."""
from PySide6 import QtCore, QtWidgets


class Settings:
    def __init__(self):
        self.store = QtCore.QSettings("fusionOS", "fusionOS")

    def value(self,key,default):
        return self.store.value(key,default,type=type(default))

    def edit(self,parent):
        dialog = QtWidgets.QDialog(parent)
        dialog.setWindowTitle("Impostazioni locali")
        layout = QtWidgets.QFormLayout(dialog)
        quality = QtWidgets.QComboBox()
        quality.addItems(["Veloce", "Bilanciata", "Accurata"])
        quality.setCurrentIndex(max(0,min(2,self.value("quality",1))))
        layout.addRow("Qualità visualizzazione",quality)
        grid = QtWidgets.QCheckBox("Mostra griglia di sfondo")
        grid.setChecked(self.value("grid",True))
        layout.addRow(grid)
        backup = QtWidgets.QSpinBox()
        backup.setRange(0,60)
        backup.setValue(max(0,min(60,self.value("backup_minutes",2))))
        backup.setSuffix(" min (0 = disattivo)")
        layout.addRow("Backup automatico",backup)
        density = QtWidgets.QDoubleSpinBox()
        density.setRange(0,100)
        density.setDecimals(3)
        density.setValue(self.value("density",2.7))
        layout.addRow("Densità materiale (g/cm³)",density)
        price = QtWidgets.QDoubleSpinBox()
        price.setRange(0,100000)
        price.setValue(self.value("price_per_kg",0.0))
        layout.addRow("Prezzo materiale (€/kg)",price)
        explanation = QtWidgets.QLabel("La qualità modifica solo l'anteprima, non la geometria CAD.\n"
            "Densità e prezzo sono ipotesi personalizzabili, applicate a tutti i corpi.\n"
            "La stima esclude lavorazione, scarti e componenti.\n"
            "I backup sono copie locali separate: il progetto salvato non viene sovrascritto.")
        explanation.setWordWrap(True)
        layout.addRow(explanation)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok|QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            for key,val in (("quality",quality.currentIndex()),("grid",grid.isChecked()),
                            ("backup_minutes",backup.value()),("density",density.value()),("price_per_kg",price.value())):
                self.store.setValue(key,val)
            return True
        return False


def material_estimate(volume_mm3,density_g_cm3,price_per_kg):
    mass_kg = volume_mm3 / 1_000_000 * density_g_cm3
    return mass_kg, mass_kg * price_per_kg
