import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import unittest
from PySide6 import QtWidgets, QtCore
from fusionos.app import MainWindow
from fusionos.settings import material_estimate


class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.app.setApplicationName("fusionOS-test")
        QtCore.QStandardPaths.setTestModeEnabled(True)

    def test_window_model_selection_and_render(self):
        window = MainWindow()
        key = window.doc.add("box",{"length":50.,"width":30.,"height":8.})
        window.refresh(key,fit=True)
        window.show()
        self.app.processEvents()
        self.assertEqual(window.selected(),[key])
        self.assertIn("12000.000",window.details.text())
        self.assertFalse(window.grab().isNull())
        window.dirty = False
        window.close()

    def test_material_estimate_units(self):
        mass,cost = material_estimate(1_000_000,2.7,5.)
        self.assertAlmostEqual(mass,2.7)
        self.assertAlmostEqual(cost,13.5)


if __name__ == "__main__":
    unittest.main()
