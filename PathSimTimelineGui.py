# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2021 Daniel Wood <s.d.wood.82@googlemail.com>            *
# *                                                                         *
# *   This program is free software; you can redistribute it and/or modify  *
# *   it under the terms of the GNU Lesser General Public License (LGPL)    *
# *   as published by the Free Software Foundation; either version 2 of     *
# *   the License, or (at your option) any later version.                   *
# *   for detail see the LICENCE text file.                                 *
# *                                                                         *
# *   This program is distributed in the hope that it will be useful,       *
# *   but WITHOUT ANY WARRANTY; without even the implied warranty of        *
# *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         *
# *   GNU Library General Public License for more details.                  *
# *                                                                         *
# *   You should have received a copy of the GNU Library General Public     *
# *   License along with this program; if not, write to the Free Software   *
# *   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  *
# *   USA                                                                   *
# *                                                                         *
# ***************************************************************************

import os

from PySide import QtGui, QtCore

import FreeCADGui

dir = os.path.dirname(__file__)
ui_name = "PathSimTimelineGui.ui"
path_to_ui = dir + "/" + ui_name

mw = FreeCADGui.getMainWindow()

'''
class ProgressMarker(QtGui.QGraphicsRectItem):

    def __init__(self, w, h, maxX):
        super().__init__(0, 0, w, h)
        self.setFlag(QtGui.QGraphicsItem.ItemIsMovable, True)
        self.maxX = maxX - w
        self.setFlag(QtGui.QGraphicsItem.ItemSendsGeometryChanges, True)

    def itemChange(self, change, value):
        if change == QtGui.QGraphicsItem.ItemPositionChange:
            x = value.x()

            if x < 0:
                x = 0

            if x > self.maxX:
                x = self.maxX

            return QtCore.QPointF(x, self.y())
        return value
'''


class ProgressMarker(QtGui.QGraphicsObject):
    ''' graphics item to represent the progress marker on the timeline '''

    progresschange = QtCore.Signal(int)
    skipRequested = QtCore.Signal()

    def __init__(self, w, h, maxX):
        super().__init__()
        self.setFlag(QtGui.QGraphicsItem.ItemIsMovable, True)
        self.maxX = maxX - w
        self.setFlag(QtGui.QGraphicsItem.ItemSendsGeometryChanges, True)
        self.width = w
        self.height = h
        self.brush = None
        self.pen = None

    def setRect(self, x, y, w, h):
        self.setPos(x, y)
        self.width = w
        self.height = h

    def setMaxX(self, maxx):
        self.maxX = maxx

    def setBrush(self, brush):
        self.brush = brush

    def setPen(self, pen):
        self.pen = pen

    def paint(self, painter, option, widget):
        painter.setBrush(self.brush)
        painter.setPen(self.pen)
        painter.drawRect(0, 0, self.width, self.height)

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.width, self.height)

    def itemChange(self, change, value):

        if change == QtGui.QGraphicsItem.ItemPositionChange:

            x = value.x()

            if x < 0:
                x = 0

            if x > self.maxX:
                x = self.maxX

            self.progresschange.emit(x)

            return QtCore.QPointF(x, self.y())

        return value

    def mouseReleaseEvent(self, event):
        print("mouse event", event)


class timeline(QtCore.QObject):

    # quitSignal = QtCore.Signal()
    playSignal = QtCore.Signal()
    stopSignal = QtCore.Signal()
    progressChangedSignal = QtCore.Signal(float)
    skipRequested = QtCore.Signal(float)

    def __init__(self):
        super(timeline, self).__init__()
        #Build GUI
        self.form = FreeCADGui.PySideUic.loadUi(path_to_ui)
        self.form.setParent(mw.centralWidget())
        self.form.setWindowFlags(QtCore.Qt.Widget | QtCore.Qt.FramelessWindowHint | QtCore.Qt.CustomizeWindowHint)
        self.form.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        mw.installEventFilter(self)

        # timeline members
        self.progress = 0  # progess complete as a float i.e. 1.0 = %100 
        self.progressMarker = None  # graphics item representing the progress marker
        self.progressBarWidth = 0  # length of the timeline used for progess calculations and positions

        self.timeLine = QtGui.QGraphicsRectItem()
        self.progressMarker = ProgressMarker(10, 10, 0)


        ### collect widget
        self.playButton = self.form.playButton
        self.stopButton = self.form.stopButton
        self.progressBar = self.form.progressBar
        self.scene = QtGui.QGraphicsScene()
        self.progressBar.setScene(self.scene)

        ### connect
        self.playButton.clicked.connect(self.play)
        self.stopButton.clicked.connect(self.stop)
        self.progressMarker.progresschange.connect(self.progressUpdate)
        self.progressMarker.skipRequested.connect(self.skip)

        # initialise form
        self.initProgressBar()
        self.setPosition()
        self.setProgress(0)

    def initProgressBar(self):

        ## create brush and pen for drawing
        brush = QtGui.QBrush()
        brush.setStyle(QtCore.Qt.SolidPattern)
        pen = QtGui.QPen()

        def addToScene(colour, drawItem):
            brush.setColor(colour)
            pen.setColor(colour)
            drawItem.setBrush(brush)
            drawItem.setPen(pen)
            self.scene.addItem(drawItem)

        addToScene(QtGui.QColor(175, 175, 175, 175), self.timeLine)
        addToScene(QtGui.QColor(0, 0, 0), self.progressMarker)

    def eventFilter(self, object, event):
        #handle resize events for the freecad ui
        if event.type() == QtCore.QEvent.Type.Resize:
            self.setPosition()

        return False

    def setProgress(self, progress):
        ''' set the progress for the current simulation'''
        self.progress = progress
        pos = self.progressMarker.pos()
        position = self.progress * self.progressBarWidth
        self.progressMarker.setPos(position, pos.y())

    def progressUpdate(self, progress):
        ''' handle progress changes from the progress marker position '''
        percent_progress = progress / self.progressBarWidth
        if self.progress * 0.05 > percent_progress or self.progress * 0.05 < percent_progress:
            self.progress = percent_progress
            # print("progress Update:", progress, "=", round(self.progress * 100, 2), "%")
            self.progressChangedSignal.emit(self.progress)

    def setPosition(self):
        ''' position the form on the screen and progress bar on the form'''
        cen = mw.centralWidget()
        cengeom = cen.geometry()

        x = cengeom.width() * 0.1
        y = cengeom.height() - self.form.height() - 50
        newWidth = cengeom.width() * 0.8
        newHeight = self.form.height()
        self.form.setGeometry(x, y, newWidth, newHeight)

        self.progressBarWidth = self.form.geometry().width() * 0.9
        self.progressMarker.setMaxX(self.progressBarWidth)
        self.timeLine.setRect(self.timeLine.pos().x(), self.timeLine.pos().y(), self.progressBarWidth, 10)
        self.setProgress(self.progress)

    def play(self):
        self.playSignal.emit()

    def stop(self):
        self.stopSignal.emit()

    def skip(self):
        self.skipRequested.emit(self.progress)

    def show(self):
        self.form.show()

    def reject(self):
        FreeCAD.Console.PrintMessage("Reject Signal")
        self.quit()

    def accept(self):
        self.quit()

    def quit(self, data=None):
        # self.quitSignal.emit()
        self.form.close()
        self.deleteLater()

    def reset(self):
        pass