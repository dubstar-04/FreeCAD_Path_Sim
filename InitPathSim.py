# -*- coding: utf-8 -*-

# ***************************************************************************
# *                                                                         *
# *   Copyright (c) 2021-2023 Daniel Wood <s.d.wood.82@googlemail.com>      *
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
import os

import FreeCADGui
from PySide import QtGui
import PathSimGui
import PathSim
import PathAddonCommon


def getIcon(iconName):
    __dir__ = os.path.dirname(__file__)
    iconPath = os.path.join(__dir__, 'Icons')
    return os.path.join(iconPath, iconName)


def getAction(mw, name):
    """Get a QAction to show the addon icon and launch the form"""
    AddonAction = QtGui.QAction(mw)
    AddonAction.setObjectName(name)
    AddonAction.setIconText("Path Simulator Next")
    AddonAction.setStatusTip("Simulate CNC Toolpath")
    AddonAction.setIcon(QtGui.QPixmap(getIcon('Path_Sim.svg')))
    AddonAction.triggered.connect(PathSimGui.Show)
    return AddonAction


def updateMenu(workbench):
    """Load the menu and toolbar"""
    if workbench == 'PathWorkbench':
        print('Path Simulator Addon loaded:', workbench)

        mw = FreeCADGui.getMainWindow()
        pathAddonAction = getAction(mw, "PathSimulatorNextToolbarAction")
        # Uncomment to show icon on path toolbar
        # PathAddonCommon.loadToolBar("Path Simulator Next", [pathAddonAction])

        pathAddonMenu = PathAddonCommon.loadPathAddonMenu()
        PathSimulatorNextAction = mw.findChild(QtGui.QAction, "PathSimulatorNextMenuAction")

        if not PathSimulatorNextAction:
            # create addon action
            pathAddonMenu.addAction(pathAddonAction)


FreeCADGui.getMainWindow().workbenchActivated.connect(updateMenu)
