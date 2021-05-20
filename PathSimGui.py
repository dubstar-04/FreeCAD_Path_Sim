# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2020 Daniel Wood <s.d.wood.82@googlemail.com>            *
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

import FreeCAD, FreeCADGui
import Draft
import Mesh
import os, math

from PySide import QtGui, QtCore
from PySide.QtGui import QTreeWidgetItem

import PathScripts.PathUtil as PathUtil

import PathSim

dir = os.path.dirname(__file__)
ui_name = "PathSimGui.ui"
path_to_ui = dir + "/" + ui_name

class PathSimPanel:
	def __init__(self, obj=None):
		# self will create a Qt widget from the ui file
		self.form = FreeCADGui.PySideUic.loadUi(path_to_ui)

		self.tool = None
		self.sim = PathSim.PathSim()
		self.jobs = []
		self.mesh = Mesh.Mesh()
		self.meshView = None

		# connect ui components
		self.form.comboJobs.currentIndexChanged.connect(self.onJobChange)
		self.form.toolButtonStop.clicked.connect(self.simStop)
		self.form.toolButtonPlay.clicked.connect(self.simPlay)
		#self.Connect(form.toolButtonPause, self.SimPause)
		#self.Connect(form.toolButtonStep, self.SimStep)
		#self.Connect(form.toolButtonFF, self.SimFF)
		self.sim.updatePos.connect(self.setPos)
		self.sim.complete.connect(self.simComplete)
		self.sim.updateMesh.connect(self.updateMesh)

		self.setupUi()

	def setupUi(self):
		jobList = FreeCAD.ActiveDocument.findObjects("Path::FeaturePython", "Job.*")
		self.form.comboJobs.clear()
		self.jobs = []

		for j in jobList:
			self.jobs.append(j)
			self.form.comboJobs.addItem(j.ViewObject.Icon, j.Label)
		
	def reject(self):
		self.quit()

	def accept(self):
		FreeCAD.Console.PrintMessage("\nAccept Signal")
		self.quit()

	def clicked(self, button):
		if button == QtGui.QDialogButtonBox.Apply:
			FreeCAD.Console.PrintMessage("\nApply Signal")

	def quit(self):
		self.simComplete()
		FreeCADGui.Control.closeDialog()
		
	def getStandardButtons(self):
		return int(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)

	def onJobChange(self):
		j = self.jobs[self.form.comboJobs.currentIndex()]
		self.job = j
		self.form.listOperations.clear()
		self.operations = []
		for op in j.Operations.OutList:
			if PathUtil.opProperty(op, 'Active'):
				listItem = QtGui.QListWidgetItem(op.ViewObject.Icon, op.Label)
				listItem.setFlags(listItem.flags() | QtCore.Qt.ItemIsUserCheckable)
				listItem.setCheckState(QtCore.Qt.CheckState.Checked)
				self.operations.append(op)
				self.form.listOperations.addItem(listItem)

	def getOperations(self):
		activeOps = []
		for i in range(self.form.listOperations.count()):
			if self.form.listOperations.item(i).checkState() == QtCore.Qt.CheckState.Checked:
				activeOps.append(self.operations[i])

		return activeOps

	def simPlay(self):

		if self.sim.isRunning():
			return

		operations = self.getOperations()
		if len(operations) == 0:
			print("No Operations active in selected job")
			return

		self.tool = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "Tool")
		self.tool.ViewObject.Proxy = 0
		self.tool.ViewObject.hide()

		self.meshView = FreeCAD.ActiveDocument.addObject("Mesh::Feature", "libcutsim")

		for op in operations:
			print(op.Label)
			# job = self.jobs[self.form.comboJobs.currentIndex()]
			self.tool.Shape = op.ToolController.Tool.Shape
			self.tool.ViewObject.show()
			self.sim.commands += op.Path.Commands
		
		self.sim.start()

	def simStop(self):
		self.simComplete()

	def setPos(self, pos):
		# update tool position 
		self.tool.Placement = pos
		#Draft.makePoint(pos.x, pos.y, pos.z)
	
	def simComplete(self):
		# clean up tool
		if self.sim.isRunning() or not self.sim.isFinished():
			self.sim.stop()

		if self.tool is not None:
			FreeCAD.ActiveDocument.removeObject(self.tool.Name)
			self.tool = None

		if self.meshView is not None:
			FreeCAD.ActiveDocument.removeObject(self.meshView.Name)
			self.meshView = None
	
	def updateMesh(self):
		# print("update Mesh")
		self.mesh.clear()
		self.mesh.read('/home/sandal/libcutsim.stl')
		if self.meshView is not None:
			self.meshView.Mesh = self.mesh
			FreeCAD.ActiveDocument.recompute()



def Show():
	try:
		import libcutsim
		panel = PathSimPanel()

		if FreeCADGui.Control.activeDialog():
			FreeCAD.Console.PrintMessage("Dialog Panel currently open: Close it?")

		FreeCADGui.Control.showDialog(panel)
	
	except ImportError:
		msgBox = QtGui.QMessageBox()
		msgBox.setText("libcutsim python module not installed")
		msgBox.exec_()
		# TODO: Delete me
		# show the dialog anyway for testing - delete me
		print("Delete me - PathSimGui.py")
		panel = PathSimPanel()
		FreeCADGui.Control.showDialog(panel)