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

import FreeCAD
import Mesh


class Engine:
	def __init__(self):

		self.tool = None
		self.cutShape = None

	def setTool(self, tool):
		''' set the tool definition. tool is a freecad shape object'''
		self.tool = tool

	def setStock(self, stock):
		''' set the starting stock definition. stock is a freecad shape object'''
		self.cutShape = stock

	def getMesh(self):
		''' return the cut shape as a freecad Mesh object'''
		# print("native_engine: get mesh")
		mesh = Mesh.Mesh(self.cutShape.tessellate(0.1))
		return mesh

	def processPosition(self, placement):
		''' process the new tool position. placement is a freecad placement object'''
		# print("native_engine: processPosition")
		toolShape = FreeCAD.ActiveDocument.getObject("Tool").Shape
		self.cutShape = self.cutShape.cut(toolShape)
