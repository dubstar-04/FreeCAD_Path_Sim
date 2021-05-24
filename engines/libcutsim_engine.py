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

try:
	import libcutsim
except:
	print("libcutsim not installed")

class Engine:
	def __init__(self):

		self.tool = None
		self.cutShape = None

		self.gl = libcutsim.GLData()    # holds GL-data for drawing
		self.iso = libcutsim.MarchingCubes() # isosurface algorithm
		self.world_size = 100
		self.max_tree_depth = 7

		self.cs = libcutsim.Cutsim(self.world_size, self.max_tree_depth, self.gl, self.iso) # cutting simulation
		self.cs.init(3)  # initial subdivision of octree


	def setTool(self, tool):
		
		toolMesh = Mesh.Mesh(tool.tessellate(0.1))

		toolFacets = []
		for f in toolMesh.Facets:
			facetOut = f.Points
			fn = f.Normal
			normal = (fn.x, fn.y, fn.z)
			facetOut.insert(0, normal)
			toolFacets.append(facetOut)

		self.tool = libcutsim.MeshVolume()
		self.tool.loadMesh(toolFacets)
		# spherical for testing
		# self.tool = libcutsim.SphereVolume()
		# self.tool.setRadius(float(3.0))

	def setStock(self, stock):

		stockMesh = Mesh.Mesh(stock.tessellate(0.1))

		stockFacets = []

		for f in stockMesh.Facets:
			facetOut = f.Points
			fn = f.Normal
			normal = (fn.x, fn.y, fn.z)
			facetOut.insert(0, normal)
			stockFacets.append(facetOut)

		self.cutShape = libcutsim.MeshVolume() # a volume for adding/subtracting 
		self.cutShape.loadMesh(stockFacets)
		self.cs.sum_volume(self.cutShape)  # add volume to octree

	def getMesh(self):
		self.cs.updateGL()
		self.gl.get_stl('/home/sandal/libcutsim.stl')
		mesh = Mesh.Mesh()
		mesh.read('/home/sandal/libcutsim.stl')
		return mesh

	def processPosition(self, pos):
		self.tool.setMeshCenter(pos.Base.x, pos.Base.y, pos.Base.z)
		# self.tool.setCenter(pos.x, pos.y, pos.z + 3)
		self.cs.diff_volume(self.tool)
