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

		self.jobs = []

		# connect ui components
		self.form.comboJobs.currentIndexChanged.connect(self.onJobChange)

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

def Show():
    """Open the preferences dialog."""
    panel = PathSimPanel()

    if FreeCADGui.Control.activeDialog():
	    FreeCAD.Console.PrintMessage("Dialog Panel currently open: Close it?")
    FreeCADGui.Control.showDialog(panel)