# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2021 Daniel Wood <s.d.wood.82@googlemail.com>            *
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
import FreeCADGui
from PySide import QtGui
import PathSimGui, PathSim
import os

__dir__ = os.path.dirname(__file__)
iconPath = os.path.join( __dir__, 'Icons' )

def getIcon(iconName):
     return os.path.join( iconPath , iconName)

def updateMenu(workbench):

    if workbench == 'CAMWorkbench':
    
        print('Path Simulator Addon loaded:', workbench)
        
        mw = FreeCADGui.getMainWindow()
        addonMenu = None

        camMenu = mw.findChild(QtGui.QMenu, "&CAM")
        if camMenu is None:
            FreeCAD.Console.PrintError("Path Simulator: CAM menu not found.\n")
            return

        for menu in camMenu.actions():
            if menu.menu() is not None and menu.menu().objectName() == "CAM_Addons":
                addonMenu = menu.menu()
                break

        if addonMenu is None:
            addonMenu = QtGui.QMenu("CAM Addons", camMenu)
            addonMenu.setObjectName("CAM_Addons")

            dressupMenu = camMenu.findChild(QtGui.QMenu, "Path Dressup")

            if dressupMenu is not None:
                camMenu.insertMenu(dressupMenu.menuAction(), addonMenu)
            else:
                camMenu.addMenu(addonMenu)

        for action in addonMenu.actions():
            if action.objectName() == "PathSim_Show":
                return

        action = QtGui.QAction(addonMenu)
        action.setObjectName("PathSim_Show")
        action.setText("Path Simulator Next")
        action.setIcon(QtGui.QIcon(getIcon('Path_Sim.svg')))
        action.setStatusTip("Simulate CNC Toolpath")
        action.triggered.connect(PathSimGui.Show)

        # append this addon to addon menu
        addonMenu.addAction(action)

FreeCADGui.getMainWindow().workbenchActivated.connect(updateMenu)
