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
import traceback

from PySide import QtCore, QtGui

import FreeCAD

import engines
from dexel.motion import sample_turning_path, move_duration


def isTurningOperation(operation):
	return hasattr(operation, "MinDiameter") and hasattr(operation, "MaxDiameter")

class PathSim (QtCore.QThread):

	updatePos = QtCore.Signal(FreeCAD.Placement)
	meshReady = QtCore.Signal()
	complete = QtCore.Signal()
	progress = QtCore.Signal(float)
	cleanup = QtCore.Signal()
	changedOp = QtCore.Signal(object)
	pathReady = QtCore.Signal(object)

	# Legacy benchmark override: 0 runs unpaced; otherwise use controller speeds.
	stepDelay = 0.05
	previewSpeed = 40.0  # mm/s, used with a warning for zero controller speeds
	previewSpindleRPM = 1000.0
	# minimum seconds between meshes sent to the display
	meshInterval = 0.2
	# minimum seconds between tool position and progress updates sent to the display
	displayInterval = 1 / 30

	def __init__(self):
		QtCore.QThread.__init__(self)
		self.operations = []
		self.operationIds = {}
		self.pathPoints = []
		self.pathRapid = []
		self.turningCommandEnds = set()
		self._pendingCut = None
		self.stepDistance = 2
		# self.skippedDistance = 0
		self.running = False
		self.idx = 0  # index of current position
		self.engine = None
		self.meshesPublished = 0
		self._meshLock = threading.Lock()
		self._latestMesh = None
		self._meshSignalled = False
		self._stateLock = threading.Lock()
		self._wake = threading.Event()
		self._seekTarget = None
		self._seekSerial = 0
		self.initialised = False
		self._stock = None
		self._operation = None
		self._speeds = None
		self.spindleRPM = 0.0
		self._speedWarnings = set()

	def setupEngine(self, engine):
		# from engines import nativeEngine
		print("PathSim: Setup Engine:", engine)
		importstring = "engines.{}".format(engine)
		self.engine = None

		try:
			# try to load the selected engine
			engineModule = importlib.import_module(importstring)
			eng = engineModule.Engine()
			self.engine = eng
			return True
		except Exception as error:
			self.cleanup.emit()
			FreeCAD.Console.PrintError("PathSim: Cannot load {}: {}\n".format(importstring, error))
			msgBox = QtGui.QMessageBox()
			msgBox.setText("An error occoured while importing {}".format(importstring))
			msgBox.exec_()
			return False

	def setOperations(self, operations, operationIds=None):
		self.reset()
		self.operations = operations
		self.operationIds = (
			{op.Name: index + 1 for index, op in enumerate(operations)}
			if operationIds is None else dict(operationIds))

	def reset(self):
		self.initialised = False
		self._pendingCut = None
		self.idx = 0
		self._operation = None
		self._speeds = None
		self.spindleRPM = 0.0
		with self._stateLock:
			self.running = False
			self._seekTarget = None

	def play(self):
		with self._stateLock:
			if self.initialised and self.idx >= len(self.pathPoints) and self._seekTarget is None:
				self._seekTarget = 0
			self.running = True
			self._wake.set()

	def stop(self):
		with self._stateLock:
			self.running = False
			self._seekTarget = None
			self._seekSerial += 1
			self._wake.set()

	def needsWork(self):
		with self._stateLock:
			return self.running or self._seekTarget is not None

	def run(self):
		try:
			self.runSimulation()
		except Exception:
			self.stop()
			self.initialised = False
			FreeCAD.Console.PrintError("PathSim: Simulation failed:\n" + traceback.format_exc())

	def runSimulation(self):

		if self.engine is None:
			print("engine not set")
			return

		if not self.initialised:
			self._speedWarnings.clear()
			with self._meshLock:
				self._latestMesh = None
				self._meshSignalled = False
				self.meshesPublished = 0
			job = FreeCAD.ActiveDocument.findObjects("Path::FeaturePython", "Job.*")[0]
			self._stock = job.Stock.Shape.copy()
			self._pendingCut = None
			self.engine.setStock(self._stock)
			self.pathPoints = self.discretizePath()
			self.pathReady.emit(self.getOperationRanges())
			self.initialised = True
		elif self._operation is not None:
			self._speeds = self.operationSpeeds(self._operation)
		rot = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 0)
		meshPending = False
		lastMesh = time.perf_counter()
		lastDisplay = 0.0
		completed = False
		playbackDeadline = time.perf_counter()

		while True:
			iterationStart = time.perf_counter()
			with self._stateLock:
				self._wake.clear()
				target = self._seekTarget
				seekSerial = self._seekSerial
				playing = self.running

			if target is not None and target < self.idx:
				self._pendingCut = None
				self.engine.setStock(self._stock)
				self.idx = 0
				self._operation = None
				meshPending = True

			if target is not None and target == self.idx:
				if not self.publishMesh(seekSerial):
					continue
				meshPending = False
				with self._stateLock:
					if self._seekSerial != seekSerial:
						continue
					self._seekTarget = None
				self.showCurrentPosition(rot)
				lastMesh = time.perf_counter()
				playbackDeadline = lastMesh
				continue

			if not playing and target is None:
				break
			if self.idx >= len(self.pathPoints):
				remaining = playbackDeadline - time.perf_counter()
				if target is None and playing and remaining > 0:
					self._wake.wait(remaining)
					continue
				with self._stateLock:
					if self._seekTarget is not None:
						continue
					self.running = False
				completed = playing
				break

			pntData = self.pathPoints[self.idx]
			pos = pntData[0]
			operation = pntData[1]
			if self._operation is not operation:
				self.loadOperation(operation, notify=target is None)
				lastDisplay = 0.0

			duration = 0.0
			if target is None and self.stepDelay != 0 and self.idx > 0:
				previous, previousOperation = self.pathPoints[self.idx - 1]
				if previousOperation is operation:
					rapid = self.pathRapid[self.idx]
					horizontal, vertical = (
						("HorizRapid", "VertRapid") if rapid else ("HorizFeed", "VertFeed"))
					duration = move_duration(
						(previous.x, previous.y, previous.z), (pos.x, pos.y, pos.z),
						self._speeds[horizontal], self._speeds[vertical],
						rapid=rapid, turning=isTurningOperation(operation))

			placement = FreeCAD.Placement(pos, rot)
			if (isTurningOperation(operation) and self.turningCommandEnds
					and getattr(self.engine, "supportsTurningSweeps", False)):
				self._pendingCut = placement
				if self.idx + 1 in self.turningCommandEnds:
					self.flushPendingCut()
			else:
				self.engine.processPosition(placement)
			self.idx += 1
			meshPending = True

			# Reconstruct all cuts without rendering the path to the seek target.
			if target is not None:
				continue
			with self._stateLock:
				if self._seekSerial != seekSerial:
					continue

			if iterationStart - lastDisplay >= self.displayInterval:
				lastDisplay = iterationStart
				self.updateToolPosition(pos, rot)
				self.progress.emit(self.idx / len(self.pathPoints))

			if time.perf_counter() - lastMesh >= self.meshInterval:
				self.publishMesh()
				lastMesh = time.perf_counter()
				meshPending = False

			if target is None:
				playbackDeadline += duration
				remaining = playbackDeadline - time.perf_counter()
				# Batch short moves within one display frame, carrying computation
				# and meshing time forward instead of adding it to every segment.
				if remaining >= self.displayInterval:
					self._wake.wait(remaining)

		if meshPending:
			self.publishMesh()
		with self._stateLock:
			seeking = self._seekTarget is not None
		if not seeking:
			self.showCurrentPosition(rot)

		reportPerformance = getattr(self.engine, "reportPerformance", None)
		if reportPerformance is not None:
			reportPerformance()

		if completed:
			self.complete.emit()

	def loadOperation(self, operation, notify=True):
		if self._operation is operation:
			return
		self.flushPendingCut()
		if isTurningOperation(operation):
			setTool = getattr(self.engine, "setTurningTool", None)
			if setTool is None:
				raise RuntimeError("The selected engine does not support turning; select dexel_engine")
		else:
			setTool = self.engine.setTool
		setTool(operation.ToolController.Tool.Shape)
		setOperation = getattr(self.engine, "setOperation", None)
		if setOperation is not None:
			setOperation(self.operationIds[operation.Name])
		self._operation = operation
		self._speeds = self.operationSpeeds(operation)
		if notify:
			self.changedOp.emit(operation)

	def operationSpeeds(self, operation):
		controller = operation.ToolController
		label = getattr(controller, "Label", operation.Label)
		speeds = {}
		fallbacks = []
		for name in ("HorizFeed", "VertFeed", "HorizRapid", "VertRapid", "SpindleSpeed"):
			value = getattr(controller, name, None)
			value = float(getattr(value, "Value", value)) if value is not None else 0.0
			if not math.isfinite(value) or value < 0:
				raise ValueError("{}: {} must be finite and non-negative".format(label, name))
			if value == 0:
				value = self.previewSpindleRPM if name == "SpindleSpeed" else self.previewSpeed
				fallbacks.append("{}={} {}".format(
					name, value if name == "SpindleSpeed" else value * 60,
					"RPM" if name == "SpindleSpeed" else "mm/min"))
			speeds[name] = value
		if fallbacks:
			key = (getattr(controller, "Name", label), tuple(fallbacks))
			if key not in self._speedWarnings:
				self._speedWarnings.add(key)
				FreeCAD.Console.PrintWarning(
					"PathSim: {} has zero or missing speeds; preview fallbacks: {}. "
					"Set the tool controller/SetupSheet speeds for commanded timing.\n".format(
						label, ", ".join(fallbacks)))
		self.spindleRPM = speeds["SpindleSpeed"]
		return speeds

	def showCurrentPosition(self, rot):
		if self.pathPoints:
			pos, operation = self.pathPoints[max(0, self.idx - 1)]
			if self._operation is operation:
				self.changedOp.emit(operation)
			else:
				self.loadOperation(operation)
			self.updateToolPosition(pos, rot)
			self.progress.emit(self.idx / len(self.pathPoints))
		else:
			self.progress.emit(0)

	def getOperationRanges(self):
		''' timeline ranges use the same sampled positions as playback progress '''
		ranges = []
		count = len(self.pathPoints)
		for index, (_, operation) in enumerate(self.pathPoints):
			operationId = self.operationIds[operation.Name]
			if ranges and ranges[-1][2] == operationId:
				ranges[-1][1] = index + 1
			else:
				ranges.append([index, index + 1, operationId])
		return [(start / count, end / count, operationId)
			for start, end, operationId in ranges]

	def flushPendingCut(self):
		''' apply deferred straight turning motion before changing tools or showing stock '''
		if self._pendingCut is not None:
			self.engine.processPosition(self._pendingCut)
			self._pendingCut = None

	def publishMesh(self, seekSerial=None):
		''' make the engine mesh available to the display, with the operation id of each face if
		the engine tracks it. Only the newest mesh is kept, so a slow display skips meshes
		instead of building up a backlog. Engines must replace faceOperationIds for each mesh,
		not modify it, so the list is safe to hand to the gui thread.'''
		with self._stateLock:
			if seekSerial is None:
				if self._seekTarget is not None:
					return False
				seekSerial = self._seekSerial
			elif seekSerial != self._seekSerial:
				return False
		self.flushPendingCut()
		mesh = self.engine.getMesh()
		frame = (mesh, getattr(self.engine, "faceOperationIds", None))
		with self._stateLock:
			if seekSerial != self._seekSerial:
				return False
			with self._meshLock:
				self._latestMesh = frame
				self.meshesPublished += 1
				notify = not self._meshSignalled
				self._meshSignalled = True
		if notify:
			self.meshReady.emit()
		return True

	def takeMesh(self):
		''' return the newest (mesh, faceOperationIds) not yet displayed, or None '''
		with self._meshLock:
			frame = self._latestMesh
			self._latestMesh = None
			self._meshSignalled = False
		return frame

	def skipTo(self, progress):
		''' request a reconstructed state; only the worker changes the processed index '''
		if not math.isfinite(progress):
			raise ValueError("Seek progress must be finite")
		with self._stateLock:
			self._seekTarget = int(max(0.0, min(1.0, progress)) * len(self.pathPoints))
			self._seekSerial += 1
			with self._meshLock:
				self._latestMesh = None
			self._wake.set()

	def updateToolPosition(self, pos, rot):
		self.updatePos.emit(FreeCAD.Placement(pos, rot))

	def discretizePath(self):
		''' split the path in to discrete points'''
		pathPoints = []
		pathRapid = []
		turningCommandEnds = set()
		currentPos = FreeCAD.Vector(0, 0, 0)
		pos = FreeCAD.Vector(0, 0, 0)
		centrePos = FreeCAD.Vector()
		
		for op in self.operations:
			if isTurningOperation(op):
				samples, commandEnds = sample_turning_path(
					((command.Name, command.Parameters) for command in op.Path.Commands),
					self.stepDistance, (currentPos.x, currentPos.y, currentPos.z))
				offset = len(pathPoints)
				turningCommandEnds.update(offset + end for end in commandEnds)
				pathPoints.extend([FreeCAD.Vector(*point), op] for point, _ in samples)
				pathRapid.extend(rapid for _, rapid in samples)
				if samples:
					currentPos = FreeCAD.Vector(*samples[-1][0])
					pos = FreeCAD.Vector(*samples[-1][0])
				continue
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
							pathRapid.append(False)
							

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
								pathRapid.append(name in ("G0", "G00"))
								currentPos.x = pos.x
								currentPos.y = pos.y
								currentPos.z = pos.z
								#self.skippedDistance = 0
		self.pathRapid = pathRapid
		self.turningCommandEnds = turningCommandEnds
		return pathPoints