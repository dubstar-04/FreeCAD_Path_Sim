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

import math
import time
import importlib

from PySide import QtCore, QtGui

import FreeCAD
import Mesh

import engines

class PathSim (QtCore.QThread):

	updatePos = QtCore.Signal(FreeCAD.Placement)
	updateMesh = QtCore.Signal(Mesh.Mesh)
	complete = QtCore.Signal()
	progress = QtCore.Signal(float)
	cleanup = QtCore.Signal()
	changedOp = QtCore.Signal(object)

	def __init__(self):
		QtCore.QThread.__init__(self)
		self.operations = []
		self.stepDistance = 2
		# self.skippedDistance = 0
		self.running = False
		self.idx = 0  # index of current position
		self.engine = None

	def setupEngine(self, engine):
		# from engines import nativeEngine
		print("PathSim: Setup Engine:", engine)
		importstring = "engines.{}".format(engine)

		try:
			# try to load the selected engine
			engineModule = importlib.import_module(importstring)
			eng = engineModule.Engine()
			self.engine = eng
		except:
			self.cleanup.emit()
			msgBox = QtGui.QMessageBox()
			msgBox.setText("An error occoured while importing {}".format(importstring))
			msgBox.exec_()

	def setOperations(self, operations):
		self.operations = operations

	def stop(self):
		self.running = False

	def run(self):

		if self.engine is None:
			print("engine not set")
			return

		self.idx = 0  # reset the progress to 0
		self.running = True
		job = FreeCAD.ActiveDocument.findObjects("Path::FeaturePython", "Job.*")[0]
		stock = job.Stock
		self.engine.setStock(stock.Shape)
		## Expand the path
		self.pathPoints = self.discretizePath()
		rot = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 0)
		op = ""

		while self.idx < len(self.pathPoints):

			if not self.running:
				print("QUITING THREAD")
				self.quit()
				break

			pntData = self.pathPoints[self.idx]
			pos = pntData[0]
			opLabel = pntData[1]

			if op != opLabel:
				print("Load Tool for op:", opLabel)
				op = opLabel
				operation = FreeCAD.ActiveDocument.getObject(op)
				tool = operation.ToolController.Tool
				self.engine.setTool(tool.Shape)
				self.changedOp.emit(operation)
			
			self.updateToolPosition(pos, rot)
			self.engine.processPosition(FreeCAD.Placement(pos, rot))

			if self.idx % 5 == 0:  # update the next every x iterations
				mesh = self.engine.getMesh()
				self.updateMesh.emit(mesh)

			self.progress.emit(self.idx / len(self.pathPoints))
			self.idx += 1

		# emit complete signal
		self.complete.emit()
	
	def skipTo(self, progress):
		''' skip the the selected point: progress is a percentage where 1 = 100% '''
		self.idx = int(progress * len(self.pathPoints))
		# print("PathSim.Jump: new pos", self.idx, "of", len(self.pathPoints))

	def updateToolPosition(self, pos, rot):
		self.updatePos.emit(FreeCAD.Placement(pos, rot))
		time.sleep(0.05)

	def discretizePath(self):
		''' split the path in to discrete points'''
		pathPoints = []
		currentPos = FreeCAD.Vector(0, 0, 0)
		pos = FreeCAD.Vector(0, 0, 0)
		centrePos = FreeCAD.Vector()
		
		for op in self.operations:
			for command in op.Path.Commands:
				name = command.Name

				centrePos.x = currentPos.x
				centrePos.y = currentPos.y
				centrePos.z = currentPos.z

				if name in ["G0", "G00", "G1", "G01", "G2", "G02","G3", "G03"]:
					parameters = command.Parameters
					for param in parameters:
						if param == 'X':
							pos.x = parameters['X']
						if param == 'Y':
							pos.y = parameters['Y']
						if param == 'Z':
							pos.z = parameters['Z']
						if param == 'I':
							i = parameters['I']  # x offset to centre
							centrePos.x += i
						if param == 'J':
							j = parameters['J']  # y offset to centre
							centrePos.y += j

					if name in ["G2", "G02", "G3", "G03"]:
						radius = round(centrePos.sub(currentPos).Length, 2)

						aX = currentPos.x - centrePos.x
						aY = currentPos.y - centrePos.y
						bX = pos.x - centrePos.x
						bY = pos.y - centrePos.y

						startAng = math.atan2(aY, aX) 
						# endAng = math.atan2(bY, bX)
						totalAng = math.atan2(aX * bY - aY * bX, aX * bX + aY * bY)

						if round(totalAng, 2) == 0.0:
							totalAng = math.pi * 2

						if name in ["G2", "G02"]:
							totalAng = -abs(totalAng)		
						
						if name in ["G3", "G03"]:
							totalAng = abs(totalAng)

						arcLen = abs(totalAng) * radius
						segments = math.ceil(arcLen / self.stepDistance)
						stepAng = totalAng / segments
						stepZ = (pos.z - currentPos.z) / segments

						#print("Final Angles: start", startAng, " end: ", endAng, "total: ", totalAng, " segments: ", segments)

						for seg in range(segments):
							angle = startAng + seg * stepAng
							segX = centrePos.x + math.cos(angle) * radius
							segY = centrePos.y + math.sin(angle) * radius
							segZ = currentPos.z + stepZ * seg
							pathPoints.append([FreeCAD.Vector(segX, segY, segZ), op.Label])
							

						currentPos.x = pos.x
						currentPos.y = pos.y
						currentPos.z = pos.z

						### END OF ARC ###


					if name in ["G0", "G00", "G1", "G01"]:
						distance = currentPos.distanceToPoint(pos)
						# distance = self.calculateDistance(currentPos, pos)
						# print("pos", pos)
						# print("distance", distance, "skippedDistance", self.skippedDistance)

						'''
						if distance < self.stepDistance:
							# update the cutsim 
							# dont move the tool
							self.skippedDistance += distance
						'''

						if distance >= self.stepDistance:  # or self.skippedDistance >= self.stepDistance:
							# calculate the position for the stepDistance
							# update the cutsim
							# update the tool position
							normal = pos.sub(currentPos).normalize()
							# print("normal:", normal, "pos", pos)
							_stepDistance = normal * self.stepDistance
							steps = int(distance / self.stepDistance)

							for i in range(steps):
								# print("step ", i, "of", steps, "POS:", pos)
								pos = currentPos.add(_stepDistance)
								pathPoints.append([FreeCAD.Vector(pos.x, pos.y, pos.z), op.Label])
								currentPos.x = pos.x
								currentPos.y = pos.y
								currentPos.z = pos.z
								#self.skippedDistance = 0
		return pathPoints