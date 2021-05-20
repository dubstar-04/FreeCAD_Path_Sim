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
import Mesh
import math
import time

from PySide import QtCore

try:
	import libcutsim
except:
	print("libcutsim not installed")
class PathSim (QtCore.QThread):

	updatePos = QtCore.Signal(FreeCAD.Placement)
	updateMesh = QtCore.Signal()
	complete = QtCore.Signal()

	def __init__(self):
		QtCore.QThread.__init__(self)
		self.commands = []
		self.stepDistance = 2
		self.skippedDistance = 0
		self.running = False

	def stop(self):
		self.running = False

	def run(self):

		self.running = True

		job = FreeCAD.ActiveDocument.findObjects("Path::FeaturePython", "Job.*")[0]
		stock = job.Stock.Shape
		stockMesh = Mesh.Mesh(stock.tessellate(0.1))

		tool = FreeCAD.ActiveDocument.getObject("ToolBit008")
		toolMesh = Mesh.Mesh(tool.Shape.tessellate(0.1))

		stockFacets = []
		for f in stockMesh.Facets:
			facetOut = f.Points
			fn = f.Normal
			normal = (fn.x, fn.y, fn.z)
			facetOut.insert(0, normal)
			stockFacets.append(facetOut)

		toolFacets = []
		for f in toolMesh.Facets:
			facetOut = f.Points
			fn = f.Normal
			normal = (fn.x, fn.y, fn.z)
			facetOut.insert(0, normal)
			toolFacets.append(facetOut)

		gl = libcutsim.GLData()         # holds GL-data for drawing
		iso = libcutsim.MarchingCubes() # isosurface algorithm
		world_size = 100
		max_tree_depth = 7
		cs = libcutsim.Cutsim(world_size, max_tree_depth, gl, iso) # cutting simulation
		# print(cs)
		cs.init(3) # initial subdivision of octree

		vol = libcutsim.MeshVolume() # a volume for adding/subtracting 
		vol.loadMesh(stockFacets)

		cs.sum_volume(vol) # add volume to octree
		cs.updateGL()

		# cutter = libcutsim.MeshVolume()
		# cutter.loadMesh(toolFacets)

		cutter = libcutsim.SphereVolume()
		cutter.setRadius(float(3.0))

		## Expand the path

		pathPoints = self.discretizePath()
		rot = FreeCAD.Rotation(FreeCAD.Vector(0, 0, 1), 0)

		for idx, pos in enumerate(pathPoints):

			if not self.running:
				print("QUITING THREAD")
				self.quit()
				break

			self.updateToolPosition(pos, rot)
			# cutter.setMeshCenter(pos.x, pos.y, pos.z)
			#cutter.setCenter(pos.x, pos.y, pos.z + 3)
			#cs.diff_volume(cutter)
			#cs.updateGL()
			if idx % 5 == 0:  # update the next every x iterations
				#gl.get_stl('/home/sandal/libcutsim.stl')
				#self.updateMesh.emit()
				pass


		# emit complete signal
		self.complete.emit()

	def calculateDistance(self, currentPos, pos):
		distance = math.sqrt(pow((pos.x - currentPos.x), 2) + pow((pos.y - currentPos.y), 2) + pow((pos.z - currentPos.z), 2))
		return distance

	def updateToolPosition(self, pos, rot):
		self.updatePos.emit(FreeCAD.Placement(pos, rot))
		time.sleep(0.1)

	def discretizePath(self):
		''' split the path in to discrete points'''
		pathPoints = []
		currentPos = FreeCAD.Vector(0, 0, 0)
		pos = FreeCAD.Vector(0, 0, 0)
		centrePos = FreeCAD.Vector()
			
		for command in self.commands:
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

					# print("Arc Count:", arcCount, name)
					# print("Pos", currentPos, centrePos, pos)
					# print("Rad", radius)

					aX = currentPos.x - centrePos.x
					aY = currentPos.y - centrePos.y
					bX = pos.x - centrePos.x
					bY = pos.y - centrePos.y

					startAng = math.atan2(aY, aX) 
					endAng = math.atan2(bY, bX)
					totalAng = math.atan2(aX * bY - aY * bX, aX * bX + aY * bY)

					if totalAng < 0:
						totalAng += math.pi * 2

					if name in ["G2", "G02"]:
						totalAng -= math.pi * 2

					if name in ["G3", "G03"]:
						totalAng += math.pi * 2

					arcLen = abs(totalAng) * radius
					segments = math.ceil(arcLen / self.stepDistance)
					stepAng = totalAng / segments
					stepZ = (pos.z - currentPos.z) / segments

					# print("Angles: start", startAng, " end: ", endAng, "total: ", totalAng, " segments: ", segments)

					for seg in range(segments):
						angle = startAng + seg * stepAng
						segX = centrePos.x + math.cos(angle) * radius
						segY = centrePos.y + math.sin(angle) * radius
						segZ = currentPos.z + stepZ * seg
						pathPoints.append(FreeCAD.Vector(segX, segY, segZ))
						

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
							pathPoints.append(FreeCAD.Vector(pos.x, pos.y, pos.z))
							currentPos.x = pos.x
							currentPos.y = pos.y
							currentPos.z = pos.z
							#self.skippedDistance = 0

		return pathPoints