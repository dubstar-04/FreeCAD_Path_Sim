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

import time

import FreeCAD
import Mesh


def _averageMs(total, count):
	return "{:.3f}".format(total * 1000 / count) if count else "n/a"


class Engine:
	def __init__(self):

		self.tool = None
		self.cutShape = None
		# tool positions removed per boolean cut. Larger batches are faster overall once the
		# stock is complex, but each cut blocks for longer, which makes playback less smooth
		self.batchSize = 1
		self._pendingTools = []
		self._resetPerformance()

	def _resetPerformance(self):
		self._positions = 0
		self._resetWindow()

	def _resetWindow(self):
		self._cuts = 0
		self._batches = 0
		self._cutTime = 0.0
		self._meshUpdates = 0
		self._tessellationTime = 0.0
		self._meshTime = 0.0

	def setTool(self, tool):
		''' set the tool definition. tool is a freecad shape object'''
		self._flushCuts()
		self.tool = tool.copy()

	def setStock(self, stock):
		''' set the starting stock definition. stock is a freecad shape object'''
		self.cutShape = stock
		self._pendingTools = []
		self._resetPerformance()

	def getMesh(self):
		''' return the cut shape as a freecad Mesh object'''
		self._flushCuts()
		start = time.perf_counter()
		tessellation = self.cutShape.tessellate(0.1)
		tessellated = time.perf_counter()
		mesh = Mesh.Mesh(tessellation)
		finished = time.perf_counter()
		self._tessellationTime += tessellated - start
		self._meshTime += finished - tessellated
		self._meshUpdates += 1
		return mesh

	def processPosition(self, placement):
		''' process the new tool position. placement is a freecad placement object'''
		if self.tool is None:
			raise RuntimeError("Native engine requires a tool before processing positions")
		toolShape = self.tool.copy()
		toolShape.Placement = placement
		self._pendingTools.append(toolShape)
		self._positions += 1
		if len(self._pendingTools) >= max(1, self.batchSize):
			self._flushCuts()
		if self._positions % 50 == 0:
			self.reportPerformance()

	def _flushCuts(self):
		''' remove all pending tool positions from the stock with one boolean cut '''
		if not self._pendingTools:
			return
		start = time.perf_counter()
		self.cutShape = self.cutShape.cut(self._pendingTools)
		self._cutTime += time.perf_counter() - start
		self._cuts += len(self._pendingTools)
		self._batches += 1
		self._pendingTools = []

	def reportPerformance(self):
		''' report averages since the previous report, excluding playback delay '''
		if not self._cuts and not self._meshUpdates:
			return

		FreeCAD.Console.PrintMessage(
			"[PathSim native] positions={} cuts={} batches={} faces={} cut_avg_ms={} "
			"mesh_updates={} tessellate_avg_ms={} mesh_build_avg_ms={}\n".format(
				self._positions, self._cuts, self._batches, len(self.cutShape.Faces),
				_averageMs(self._cutTime, self._cuts), self._meshUpdates,
				_averageMs(self._tessellationTime, self._meshUpdates),
				_averageMs(self._meshTime, self._meshUpdates)
			)
		)
		self._resetWindow()
