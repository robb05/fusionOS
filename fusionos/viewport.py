"""Portable Qt triangle viewer. Exact BRep is retained separately by the model.

This prototype uses a CPU painter, not a production GPU CAD viewport.
"""
import math
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets


class Viewport(QtWidgets.QWidget):
    picked = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(360, 300)
        self.setMouseTracking(True)
        self.meshes = []
        self.selected = set()
        self.yaw, self.pitch = -35.0, -55.0
        self.zoom = 5.0
        self.pan = np.zeros(2)
        self.centre = np.zeros(3)
        self._last = None
        self._press = None
        self._pick_buffer = None
        self._pick_keys = []
        self.tolerance = 0.15
        self.show_grid = True

    def set_shapes(self, shapes, selected=()):
        meshes = []
        for key, shape in shapes.items():
            vertices, triangles = shape.tessellate(self.tolerance, 0.25)
            if len(triangles) > 100000:
                raise ValueError("Modello troppo denso per il visualizzatore iniziale (100.000 triangoli per corpo).")
            meshes.append((key, np.array([v.toTuple() for v in vertices]), triangles, bool(shape.Solids())))
        self.meshes, self.selected = meshes, set(selected)
        self.update()

    def fit(self):
        arrays = [v for _, v, _, _ in self.meshes if len(v)]
        if arrays:
            all_points = np.concatenate(arrays)
            low, high = all_points.min(axis=0), all_points.max(axis=0)
            self.centre = (low+high)/2
            self.zoom = min(self.width(), self.height()) * 0.65 / max(np.linalg.norm(high-low), 1)
        self.pan[:] = 0
        self.update()

    def view(self, name):
        self.yaw, self.pitch = {"iso":(-35,-55), "top":(0,0), "front":(0,-90), "right":(90,-90)}[name]
        self.update()

    def matrix(self):
        y, p = math.radians(self.yaw), math.radians(self.pitch)
        rz = np.array([[math.cos(y),-math.sin(y),0], [math.sin(y),math.cos(y),0], [0,0,1]])
        rx = np.array([[1,0,0], [0,math.cos(p),-math.sin(p)], [0,math.sin(p),math.cos(p)]])
        return rx @ rz

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor("#e7edf3"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#d5dfe8"), 1))
        for x in range(0, self.width(), 40) if self.show_grid else ():
            painter.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), 40) if self.show_grid else ():
            painter.drawLine(0, y, self.width(), y)
        matrix = self.matrix()
        offset = np.array([self.width()/2, self.height()/2]) + self.pan
        width, height = self.width(), self.height()
        pixels = np.zeros((height,width,4),dtype=np.uint8)
        depth_buffer = np.full((height,width),-np.inf)
        pick_buffer = np.full((height,width),-1,dtype=np.int32)
        self._pick_keys = [key for key,_,_,_ in self.meshes]
        for mesh_index, (key, vertices, triangles, solid) in enumerate(self.meshes):
            if not len(vertices):
                continue
            rotated = (vertices-self.centre) @ matrix.T
            points = rotated[:,:2] * np.array([self.zoom, -self.zoom]) + offset
            for ids in triangles:
                a,b,c = rotated[list(ids)]
                normal = np.cross(b-a,c-a)
                light = 0.48 + 0.52*abs(normal[2])/max(np.linalg.norm(normal),1e-15)
                rgb = (40,157,215) if key in self.selected else (152,177,196)
                color = [int(channel*light) for channel in rgb]+[255]
                coords = points[list(ids)]
                xmin = max(0,int(np.floor(coords[:,0].min())))
                xmax = min(width-1,int(np.ceil(coords[:,0].max())))
                ymin = max(0,int(np.floor(coords[:,1].min())))
                ymax = min(height-1,int(np.ceil(coords[:,1].max())))
                if xmax < xmin or ymax < ymin:
                    continue
                x0,y0 = coords[0]; x1,y1 = coords[1]; x2,y2 = coords[2]
                denominator = (y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
                if abs(denominator) < 1e-12:
                    continue
                yy,xx = np.mgrid[ymin:ymax+1,xmin:xmax+1]
                xx = xx+0.5; yy = yy+0.5
                w0 = ((y1-y2)*(xx-x2)+(x2-x1)*(yy-y2))/denominator
                w1 = ((y2-y0)*(xx-x2)+(x0-x2)*(yy-y2))/denominator
                w2 = 1-w0-w1
                depth = w0*a[2]+w1*b[2]+w2*c[2]
                region = depth_buffer[ymin:ymax+1,xmin:xmax+1]
                mask = (w0>=-1e-9)&(w1>=-1e-9)&(w2>=-1e-9)&(depth>region)
                region[mask] = depth[mask]
                pixels[ymin:ymax+1,xmin:xmax+1][mask] = color
                pick_buffer[ymin:ymax+1,xmin:xmax+1][mask] = mesh_index
        self._pick_buffer = pick_buffer
        frame = QtGui.QImage(pixels.data,width,height,width*4,QtGui.QImage.Format_RGBA8888)
        painter.drawImage(0,0,frame)
        painter.setPen(QtGui.QColor("#586b7c"))
        painter.drawText(18, 28, "fusionOS  /  PROGETTA LOCALE")
        if not self.meshes:
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "Crea uno schizzo o un solido per iniziare")
        painter.drawText(18, self.height()-18, "Trascina: orbita   ·   Centrale / Shift: sposta   ·   Rotella: zoom   ·   Click: seleziona")
        # Axis triad in view coordinates.
        origin = QtCore.QPointF(self.width()-70, self.height()-70)
        for i, (label, color) in enumerate((("X", "#ce5555"),("Y", "#39925d"),("Z", "#397ec1"))):
            vector = matrix[:,i]*35
            end = origin + QtCore.QPointF(vector[0], -vector[1])
            painter.setPen(QtGui.QPen(QtGui.QColor(color), 2))
            painter.drawLine(origin,end)
            painter.drawText(end + QtCore.QPointF(3,-3), label)
        painter.end()

    def mousePressEvent(self, event):
        self._last = event.position()
        self._press = event.position()

    def mouseMoveEvent(self, event):
        if self._last is None or not event.buttons():
            return
        delta = event.position()-self._last
        self._last = event.position()
        if event.buttons() & QtCore.Qt.MiddleButton or event.modifiers() & QtCore.Qt.ShiftModifier:
            self.pan += (delta.x(),delta.y())
        else:
            self.yaw += delta.x()*0.5
            self.pitch += delta.y()*0.5
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._press is not None and (event.position()-self._press).manhattanLength() < 4:
            x,y = int(event.position().x()),int(event.position().y())
            if self._pick_buffer is not None and 0<=y<self._pick_buffer.shape[0] and 0<=x<self._pick_buffer.shape[1]:
                index = self._pick_buffer[y,x]
                if index >= 0:
                    self.picked.emit(self._pick_keys[index])
        self._last = self._press = None

    def wheelEvent(self, event):
        self.zoom = min(1e6, max(1e-5, self.zoom*1.15**(event.angleDelta().y()/120)))
        self.update()
