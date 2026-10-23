import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from dexel import DexelGrid, TurningTool


class Signal:
    def __init__(self, *args):
        self.calls = []
        self.callback = None

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return instance.__dict__.setdefault(self.name, Signal())

    def emit(self, *args):
        self.calls.append(args)
        if self.callback is not None:
            self.callback(*args)


class Placement:
    def __init__(self, position, rotation):
        self.Base = position


def load_worker():
    freecad = SimpleNamespace(
        Placement=Placement, Vector=lambda *args: args, Rotation=lambda *args: None)
    qt = SimpleNamespace(QtCore=SimpleNamespace(QThread=object, Signal=Signal), QtGui=None)
    path = Path(__file__).resolve().parents[1] / "PathSim.py"
    spec = importlib.util.spec_from_file_location("seek_worker", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"FreeCAD": freecad, "PySide": qt}):
        spec.loader.exec_module(module)
    return module


worker = load_worker()


class Clock:
    def __init__(self):
        self.now = 0.0

    def perf_counter(self):
        return self.now


class Engine:
    def __init__(self, clock):
        self.clock = clock
        self.positions = []
        self.meshes = []
        self.resets = 0
        self.on_position = None
        self.on_mesh = None

    def setStock(self, stock):
        self.resets += 1
        self.positions = []

    def setTool(self, tool):
        pass

    def processPosition(self, placement):
        self.positions.append(placement.Base.x)
        self.clock.now += 0.05
        if self.on_position is not None:
            self.on_position()

    def getMesh(self):
        self.clock.now += 0.4
        self.meshes.append(tuple(self.positions))
        if self.on_mesh is not None:
            self.on_mesh()
        return self.meshes[-1]


class SeekTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.sim = worker.PathSim()
        self.sim.initialised = True
        self.sim.stepDelay = 0
        self.sim.engine = Engine(self.clock)
        self.sim.operationSpeeds = lambda operation: {}
        controller = SimpleNamespace(Tool=SimpleNamespace(Shape=None))
        self.operations = [SimpleNamespace(Name=name, ToolController=controller)
                           for name in ("first", "second")]
        self.sim.operationIds = {"first": 1, "second": 2}
        self.sim.pathPoints = [
            (SimpleNamespace(x=i, y=0, z=0), self.operations[i // 10])
            for i in range(20)]

    def run_worker(self):
        with patch.object(worker, "time", self.clock):
            self.sim.runSimulation()

    def test_forward_seek_only_displays_destination(self):
        self.sim.skipTo(0.8)
        self.run_worker()
        self.assertEqual(self.sim.engine.positions, list(range(16)))
        self.assertEqual(len(self.sim.engine.meshes), 1)
        self.assertEqual({args[0] for args in self.sim.progress.calls}, {0.8})
        self.assertEqual({args[0].Base.x for args in self.sim.updatePos.calls}, {15})
        self.assertTrue(all(args[0] is self.operations[1]
                            for args in self.sim.changedOp.calls))
        self.assertLess(self.clock.now, 1.21)
        self.assertFalse(self.sim.running)

    def test_backward_seek_reconstructs_original_path(self):
        self.sim.idx = 18
        self.sim.skipTo(0.3)
        self.run_worker()
        self.assertEqual(self.sim.engine.resets, 1)
        self.assertEqual(self.sim.engine.positions, list(range(6)))
        self.assertEqual(len(self.sim.engine.meshes), 1)
        self.assertEqual({args[0] for args in self.sim.progress.calls}, {0.3})

    def test_new_seek_supersedes_reconstruction(self):
        def retarget():
            if self.sim.idx == 4:
                self.sim.skipTo(0.1)

        self.sim.engine.on_position = retarget
        self.sim.skipTo(0.8)
        self.run_worker()
        self.assertEqual(self.sim.engine.positions, [0, 1])
        self.assertEqual(len(self.sim.engine.meshes), 1)
        self.assertEqual({args[0] for args in self.sim.progress.calls}, {0.1})

    def test_seek_during_endpoint_meshing_does_not_show_old_position(self):
        def retarget():
            self.sim.engine.on_mesh = None
            self.sim.skipTo(0.2)

        self.sim.engine.on_mesh = retarget
        self.sim.skipTo(0.8)
        self.run_worker()
        self.assertEqual({args[0] for args in self.sim.progress.calls}, {0.2})
        self.assertEqual(self.sim.takeMesh()[0], (0, 1, 2, 3))

    def test_seek_keeps_playing_from_destination(self):
        self.sim.running = True
        self.sim.skipTo(0.6)
        self.run_worker()
        self.assertEqual(self.sim.engine.positions, list(range(20)))
        self.assertEqual(self.sim.progress.calls[0], (0.6,))
        self.assertEqual(self.sim.progress.calls[-1], (1.0,))
        self.assertEqual(len(self.sim.complete.calls), 1)

    def test_stop_interrupts_seek(self):
        def stop():
            if self.sim.idx == 3:
                self.sim.stop()

        self.sim.engine.on_position = stop
        self.sim.skipTo(0.8)
        self.run_worker()
        self.assertEqual(self.sim.idx, 4)
        self.assertFalse(self.sim.needsWork())
        self.assertEqual(self.sim.progress.calls[-1], (0.2,))

    def test_normal_playback_still_displays_intermediate_frames(self):
        self.sim.running = True
        self.run_worker()
        self.assertGreater(len(self.sim.engine.meshes), 1)
        self.assertGreater(len(self.sim.progress.calls), 1)
        self.assertEqual(len(self.sim.complete.calls), 1)

    def test_seek_discards_queued_mesh(self):
        self.sim.publishMesh()
        self.sim.skipTo(0.8)
        self.assertIsNone(self.sim.takeMesh())
        self.run_worker()
        self.assertEqual(self.sim.takeMesh()[0], tuple(range(16)))

    def test_superseded_endpoint_mesh_is_not_published(self):
        def retarget():
            self.sim.engine.on_mesh = None
            self.sim.skipTo(0.9)

        self.sim.engine.on_mesh = retarget
        self.sim.skipTo(0.8)
        self.run_worker()
        self.assertEqual(self.sim.meshesPublished, 1)
        self.assertEqual(self.sim.takeMesh()[0], tuple(range(18)))
        self.assertEqual({args[0] for args in self.sim.progress.calls}, {0.9})

    def test_turning_seek_matches_original_geometry_and_face_colours(self):
        class TurningEngine(Engine):
            def setStock(self, stock):
                super().setStock(stock)
                self.grid = DexelGrid.cylinder(5, 10, 0.25)
                self.tool = TurningTool([(0, 0), (1, 0), (1, 1), (0, 1)])
                self.previous = None

            def setTurningTool(self, tool):
                self.previous = None

            def setOperation(self, operation_id):
                self.operation_id = operation_id
                self.previous = None

            def processPosition(self, placement):
                super().processPosition(placement)
                position = (placement.Base.x, placement.Base.z)
                self.grid.cut_turning(
                    self.tool, self.operation_id, self.previous or position, position)
                self.previous = position

            def getMesh(self):
                super().getMesh()
                mesh, self.faceOperationIds = self.grid.extract()
                return mesh

        self.sim.engine = TurningEngine(self.clock)
        self.sim.engine.setStock(None)
        for operation in self.operations:
            operation.MinDiameter = 0
            operation.MaxDiameter = 10
        for index, (position, _) in enumerate(self.sim.pathPoints):
            position.x = 3.0 + 0.05 * index
            position.z = 2.0 + 0.2 * index
        self.sim.skipTo(0.8)
        self.run_worker()
        grid = self.sim.engine.grid
        expected_mesh, expected_ids = grid.extract()
        expected_volume = grid.volume()
        self.assertTrue(grid.multi)
        self.assertIn(1, expected_ids)
        self.assertIn(2, expected_ids)

        self.sim.skipTo(0.2)
        self.run_worker()
        self.sim.skipTo(0.8)
        self.run_worker()
        actual_mesh, actual_ids = self.sim.engine.grid.extract()
        self.assertEqual(actual_mesh, expected_mesh)
        self.assertEqual(actual_ids, expected_ids)
        self.assertEqual(self.sim.engine.grid.volume(), expected_volume)


if __name__ == "__main__":
    unittest.main()
