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
import threading
import importlib

from PySide import QtCore, QtGui

import FreeCAD

import engines

class PathSim (QtCore.QThread):

	updatePos = QtCore.Signal(FreeCAD.Placement)
	meshReady = QtCore.Signal()
	complete = QtCore.Signal()
	progress = QtCore.Signal(float)
	cleanup = QtCore.Signal()
	changedOp = QtCore.Signal(object)

	# seconds taken by each tool position during playback, 0 runs as fast as the engine can
	stepDelay = 0.05
	# minimum seconds between meshes sent to the display
	meshInterval = 0.2
	# minimum seconds between tool position and progress updates sent to the display
	displayInterval = 1 / 30

	def __init__(self):
		QtCore.QThread.__init__(self)
		self.operations = []
		self.operationIds = {}
		self.stepDistance = 2
		# self.skippedDistance = 0
		self.running = False
		self.idx = 0  # index of current position
		self.engine = None
		self.meshesPublished = 0
		self._meshLock = threading.Lock()
		self._latestMesh = None
		self._meshSignalled = False

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

	def setOperations(self, operations, operationIds=None):
		self.operations = operations
		self.operationIds = (
			{op.Name: index + 1 for index, op in enumerate(operations)}
			if operationIds is None else dict(operationIds))

	def stop(self):
		self.running = False

	def run(self):

		if self.engine is None:
			print("engine not set")
			return

		self.idx = 0  # reset the progress to 0
		self.running = True
		with self._meshLock:
			self._latestMesh = None
			self._meshSignalled = False
			self.meshesPublished = 0
		job = FreeCAD.ActiveDocument.findObjects("Path::FeaturePython", "Job.*")[0]
		stock = job.Stock
		self.engine.setStock(stock.Shape)
		## Expand the path
		self.pathPoints = self.discretizePath()
		rot = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 0)
		op = None
		meshPending = False
		lastMesh = time.perf_counter()
		lastDisplay = 0.0

		while self.idx < len(self.pathPoints):

			if not self.running:
				print("QUITING THREAD")
				self.quit()
				break

			iterationStart = time.perf_counter()
			pntData = self.pathPoints[self.idx]
			pos = pntData[0]
			operation = pntData[1]

			if op is not operation:
				print("Load Tool for op:", operation.Label)
				op = operation
				tool = operation.ToolController.Tool
				self.engine.setTool(tool.Shape)
				setOperation = getattr(self.engine, "setOperation", None)
				if setOperation is not None:
					setOperation(self.operationIds[operation.Name])
				self.changedOp.emit(operation)
				lastDisplay = 0.0  # show the tool at its first position straight away

			if iterationStart - lastDisplay >= self.displayInterval:
				lastDisplay = iterationStart
				self.updateToolPosition(pos, rot)
				self.progress.emit(self.idx / len(self.pathPoints))

			self.engine.processPosition(FreeCAD.Placement(pos, rot))
			meshPending = True

			if time.perf_counter() - lastMesh >= self.meshInterval:
				self.publishMesh()
				lastMesh = time.perf_counter()
				meshPending = False

			self.idx += 1

			# pace playback by the time each position takes, not by a sleep on top of the work
			remaining = self.stepDelay - (time.perf_counter() - iterationStart)
			if remaining > 0:
				time.sleep(remaining)

		if meshPending:
			self.publishMesh()
		if self.pathPoints:
			self.progress.emit(self.idx / len(self.pathPoints))

		reportPerformance = getattr(self.engine, "reportPerformance", None)
		if reportPerformance is not None:
			reportPerformance()

		# emit complete signal
		self.complete.emit()
	
	def publishMesh(self):
		''' make the engine mesh available to the display, with the operation id of each face if
		the engine tracks it. Only the newest mesh is kept, so a slow display skips meshes
		instead of building up a backlog. Engines must replace faceOperationIds for each mesh,
		not modify it, so the list is safe to hand to the gui thread.'''
		mesh = self.engine.getMesh()
		frame = (mesh, getattr(self.engine, "faceOperationIds", None))
		with self._meshLock:
			self._latestMesh = frame
			self.meshesPublished += 1
			notify = not self._meshSignalled
			self._meshSignalled = True
		if notify:
			self.meshReady.emit()

	def takeMesh(self):
		''' return the newest (mesh, faceOperationIds) not yet displayed, or None '''
		with self._meshLock:
			frame = self._latestMesh
			self._latestMesh = None
			self._meshSignalled = False
		return frame

	def skipTo(self, progress):
		''' skip the the selected point: progress is a percentage where 1 = 100% '''
		self.idx = int(progress * len(self.pathPoints))
		# print("PathSim.Jump: new pos", self.idx, "of", len(self.pathPoints))

	def updateToolPosition(self, pos, rot):
		self.updatePos.emit(FreeCAD.Placement(pos, rot))

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
							pathPoints.append([FreeCAD.Vector(segX, segY, segZ), op])
							

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
								pathPoints.append([FreeCAD.Vector(pos.x, pos.y, pos.z), op])
								currentPos.x = pos.x
								currentPos.y = pos.y
								currentPos.z = pos.z
								#self.skippedDistance = 0
		return pathPoints