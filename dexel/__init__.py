"""Standalone dexel material-removal library.

Standard library only: nothing in this package imports FreeCAD, so it can be
used, tested and distributed independently of the FreeCAD add-in.

Typical use::

    from dexel import DexelGrid, RevolvedTool

    grid = DexelGrid((0, 0, 0, 100, 100, 20), resolution=0.25)
    tool = RevolvedTool.flat(radius=3.0, length=30.0)
    grid.cut_segment(tool, 1, (10, 10, 12), (40, 10, 12))
    triangles, tool_ids = grid.extract()
"""

from .grid import DexelGrid
from .tools import RevolvedTool

__all__ = ["DexelGrid", "RevolvedTool"]
__version__ = "0.1.0"
