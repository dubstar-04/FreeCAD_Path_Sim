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

import FreeCAD
import Mesh

import dexel


class Engine:
	''' Material removal using the standalone dexel library.

	This adapter only converts between FreeCAD objects and the library: the stock
	becomes a dexel grid from its bounding box, each tool becomes a revolved
	profile, and the surface is returned as a FreeCAD mesh. Tool positions are
	cut as segments from the previous position so material between the sampled
	positions is removed too.
	'''

	def __init__(self):
		self.grid = None
		self.tool = None
		self.operationId = 0
		self.faceOperationIds = []  # replaced for each mesh, never modified
		self.resolution = None  # model units; None chooses it from the stock size
		self.targetColumns = 100000
		self.toolTessellation = 0.1
		self._lastPosition = None
		self._resetPerformance()

	def _resetPerformance(self):
		self._positions = 0
		self._resetWindow()
		self._triangles = 0

	def _resetWindow(self):
		self._cuts = 0
		self._cutTime = 0.0
		self._columnsChanged = 0
		self._meshUpdates = 0
		self._extractTime = 0.0
		self._meshTime = 0.0

	def setStock(self, stock):
		''' set the starting stock definition. stock is a freecad shape object'''
		box = stock.BoundBox
		if box.XLength <= 0 or box.YLength <= 0 or box.ZLength <= 0:
			raise ValueError("Stock has no volume")

		boxVolume = box.XLength * box.YLength * box.ZLength
		if abs(stock.Volume - boxVolume) > 0.01 * boxVolume:
			FreeCAD.Console.PrintWarning(
				"[PathSim dexel] Stock is not a box; its bounding box will be used.\n")

		resolution = self.resolution
		if resolution is None:
			resolution = max(0.01, math.sqrt(box.XLength * box.YLength / self.targetColumns))

		self.grid = dexel.DexelGrid(
			(box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax), resolution)
		self.tool = None
		self.operationId = 0
		self.faceOperationIds = []
		self._lastPosition = None
		self._resetPerformance()
		FreeCAD.Console.PrintMessage(
			"[PathSim dexel] grid {} x {} columns, resolution {:.3f}\n".format(
				self.grid.nx, self.grid.ny, resolution))

	def setTool(self, tool):
		''' set the tool definition. tool is a freecad shape object

		The tool origin is expected at the tip, with the axis along +Z.
		'''
		points = [(p.x, p.y, p.z) for p in tool.tessellate(self.toolTessellation)[0]]
		binWidth = 0.5 * min(self.grid.dx, self.grid.dy) if self.grid else 0.05
		self.tool = dexel.RevolvedTool.from_points(points, binWidth)
		self._lastPosition = None
		FreeCAD.Console.PrintMessage(
			"[PathSim dexel] tool: radius {:.3f}, length {:.3f}, {}\n".format(
				self.tool.radius, self.tool.top,
				"flat" if self.tool.is_flat else "profiled"))

	def setOperation(self, operationId):
		if not 0 < operationId < 65536:
			raise ValueError("Operation id must be between 1 and 65535")
		self.operationId = operationId
		self._lastPosition = None

	def processPosition(self, placement):
		''' process the new tool position. placement is a freecad placement object'''
		if self.grid is None or self.tool is None or not self.operationId:
			raise RuntimeError("The dexel engine needs a stock, tool and operation before cutting")

		base = placement.Base
		position = (base.x, base.y, base.z)
		start = time.perf_counter()
		self._columnsChanged += self.grid.cut_segment(
			self.tool, self.operationId, self._lastPosition or position, position)
		self._cutTime += time.perf_counter() - start
		self._lastPosition = position
		self._cuts += 1
		self._positions += 1
		if self._positions % 50 == 0:
			self.reportPerformance()

	def getMesh(self):
		''' return the cut shape as a freecad Mesh object'''
		start = time.perf_counter()
		triangles, self.faceOperationIds = self.grid.extract()
		extracted = time.perf_counter()
		mesh = Mesh.Mesh(triangles)
		finished = time.perf_counter()
		self._extractTime += extracted - start
		self._meshTime += finished - extracted
		self._meshUpdates += 1
		self._triangles = len(triangles)
		return mesh

	def reportPerformance(self):
		''' report averages since the previous report, excluding playback delay '''
		if not self._cuts and not self._meshUpdates:
			return

		def average(total, count):
			return "{:.3f}".format(total * 1000 / count) if count else "n/a"

		FreeCAD.Console.PrintMessage(
			"[PathSim dexel] positions={} cuts={} cut_avg_ms={} columns_changed={} "
			"mesh_updates={} triangles={} extract_avg_ms={} mesh_build_avg_ms={}\n".format(
				self._positions, self._cuts, average(self._cutTime, self._cuts),
				self._columnsChanged, self._meshUpdates, self._triangles,
				average(self._extractTime, self._meshUpdates),
				average(self._meshTime, self._meshUpdates)))
		self._resetWindow()
