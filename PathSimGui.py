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

import os 

from PySide import QtGui, QtCore

import FreeCAD
import FreeCADGui
import Mesh

import PathScripts.PathUtil as PathUtil

import PathSim
import PathSimTimelineGui

dir = os.path.dirname(__file__)
ui_name = "PathSimGui.ui"
path_to_ui = dir + os.sep + ui_name
path_to_engines = dir + os.sep + "engines"

class PathSimPanel:
	def __init__(self, obj=None):
		# self will create a Qt widget from the ui file
		self.form = FreeCADGui.PySideUic.loadUi(path_to_ui)

		self.tool = None
		self.sim = PathSim.PathSim()
		self.jobs = []
		self.meshView = None
		self.counter = 0

		self.timeline = PathSimTimelineGui.timeline()

		# connect ui components
		self.form.comboJobs.currentIndexChanged.connect(self.onJobChange)
		self.sim.updatePos.connect(self.setPos)
		self.sim.complete.connect(self.simComplete)
		self.sim.updateMesh.connect(self.updateMesh)
		self.sim.progress.connect(self.timeline.setProgress)
		self.sim.cleanup.connect(self.cleanup)
		self.sim.changedOp.connect(self.loadTool)

		#self.timeline.quitSignal.connect(self.simStop)
		self.timeline.playSignal.connect(self.simPlay)
		self.timeline.stopSignal.connect(self.simStop)
		self.timeline.skipRequested.connect(self.sim.skipTo)

		self.setupUi()

	def setupUi(self):
		jobList = FreeCAD.ActiveDocument.findObjects("Path::FeaturePython", "Job.*")
		self.form.comboJobs.clear()
		self.jobs = []

		for j in jobList:
			self.jobs.append(j)
			self.form.comboJobs.addItem(j.ViewObject.Icon, j.Label)

		#show the timeline widget
		self.timeline.show()

		self.form.comboEngines.clear()
		engines = os.listdir(path_to_engines)
		for filename in engines:
			engine_str = "_engine.py"
			if engine_str in filename:
				engineName = filename.replace(".py", "")
				self.form.comboEngines.addItem(engineName)
		
	def reject(self):
		self.quit()

	def accept(self):
		FreeCAD.Console.PrintMessage("\nAccept Signal")
		self.quit()

	def clicked(self, button):
		if button == QtGui.QDialogButtonBox.Apply:
			FreeCAD.Console.PrintMessage("\nApply Signal")

	def quit(self):
		self.timeline.quit()
		self.simStop()
		self.cleanup()
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
		
		self.cleanup()
		self.meshView = FreeCAD.ActiveDocument.addObject("Mesh::Feature", "cutshape")
		job = FreeCAD.ActiveDocument.findObjects("Path::FeaturePython", "Job.*")[0]
		self.meshView.Mesh = Mesh.Mesh(job.Stock.Shape.tessellate(0.1))

		self.sim.setupEngine(self.form.comboEngines.currentText())
		self.sim.setOperations(operations)
		self.sim.start()
	
	def loadTool(self, op):
		''' load the tool for the operation '''
		if self.tool is None:
			self.tool = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", "Tool")
			self.tool.ViewObject.Proxy = 0
		self.tool.Shape = op.ToolController.Tool.Shape

	def simStop(self):
		if self.sim.isRunning() or not self.sim.isFinished():
			self.sim.stop()

	def setPos(self, pos):
		# update tool position 
		self.tool.Placement = pos

	def cleanup(self):
		self.cleanupStock()
		self.cleanupTool()

	def cleanupTool(self):
		''' Delete the tool created for the simulation '''
		if self.tool is not None:
			FreeCAD.ActiveDocument.removeObject(self.tool.Name)
			self.tool = None

	def cleanupStock(self):
		''' Delete the stock created for the simulation '''
		if self.meshView is not None:
			FreeCAD.ActiveDocument.removeObject(self.meshView.Name)
			self.meshView = None

	def simComplete(self):
		''' slot called on simulation completion'''
		self.cleanupTool()

	def updateMesh(self, mesh):
		''' slot called at intervals to update the meshView'''
		if self.meshView is not None:
			self.meshView.Mesh = mesh
			FreeCAD.ActiveDocument.recompute()

def Show():
	panel = PathSimPanel()
	FreeCADGui.Control.showDialog(panel)