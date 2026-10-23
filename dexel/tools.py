"""Cutting tools described as a profile revolved about a vertical axis."""

import bisect
import math


class RevolvedTool:
    """A tool whose lowest surface is a function of distance from its axis.

    ``profile`` is a sequence of ``(radius, bottom_z)`` points, with ``bottom_z``
    measured from the tool origin (normally the tip). The tool is assumed to
    occupy everything above that lower envelope, up to ``top``, for radii not
    larger than the outermost profile point.

    The envelope is made non-decreasing with radius (each point takes the lowest
    ``bottom_z`` found at its own or any larger radius). That is correct for
    flat, ball, bull-nose, conical and drill-style tools. It is not correct for
    tools whose bottom is lower toward the outside than the centre.
    """

    TABLE_STEPS = 512

    def __init__(self, profile, top=math.inf):
        points = sorted((float(r), float(z)) for r, z in profile)
        if not points:
            raise ValueError("A tool profile needs at least one point")
        if points[0][0] < 0:
            raise ValueError("Profile radii must not be negative")
        if points[-1][0] <= 0:
            raise ValueError("The tool radius must be positive")
        if points[0][0] > 0:
            points.insert(0, (0.0, points[0][1]))

        lowest = math.inf
        for index in range(len(points) - 1, -1, -1):
            radius, z = points[index]
            lowest = min(lowest, z)
            points[index] = (radius, lowest)

        self.profile = points
        self.radius = points[-1][0]
        self.top = float(top)
        self.flat_bottom = points[0][1]
        self.is_flat = all(z == self.flat_bottom for _, z in points)
        if self.top <= points[-1][1]:
            raise ValueError("The tool top must be above its lowest surface")

        radii = [r for r, _ in points]
        heights = [z for _, z in points]
        steps = self.TABLE_STEPS
        self.table = [
            self._interpolate(radii, heights, step * self.radius / steps)
            for step in range(steps + 1)
        ]
        self.table_scale = steps / self.radius

    @staticmethod
    def _interpolate(radii, heights, radius):
        index = bisect.bisect_right(radii, radius)
        if index == 0:
            return heights[0]
        if index >= len(radii):
            return heights[-1]
        r0, r1 = radii[index - 1], radii[index]
        z0, z1 = heights[index - 1], heights[index]
        return z0 + (z1 - z0) * (radius - r0) / (r1 - r0)

    def bottom(self, radius):
        """Height of the tool's lowest surface at ``radius`` from the axis."""
        if radius >= self.radius:
            return self.table[-1]
        return self.table[int(radius * self.table_scale + 0.5)]

    @classmethod
    def flat(cls, radius, length=math.inf):
        return cls([(0.0, 0.0), (radius, 0.0)], top=length)

    @classmethod
    def ball(cls, radius, length=math.inf, steps=32):
        points = []
        for step in range(steps + 1):
            r = radius * step / steps
            points.append((r, radius - math.sqrt(max(0.0, radius * radius - r * r))))
        return cls(points, top=length)

    @classmethod
    def from_points(cls, points, bin_width, top=None):
        """Estimate a tool from ``(x, y, z)`` points on its surface.

        Points are grouped by distance from the Z axis; the lowest point in each
        group defines the lower envelope. ``top`` defaults to the highest point.
        """
        if bin_width <= 0:
            raise ValueError("bin_width must be positive")
        lowest = {}
        highest = -math.inf
        for x, y, z in points:
            radius = math.hypot(x, y)
            key = int(radius / bin_width + 0.5)
            current = lowest.get(key)
            if current is None or z < current[1]:
                lowest[key] = (radius, z)
            highest = max(highest, z)
        if not lowest:
            raise ValueError("No points to build a tool from")
        return cls(lowest.values(), top=highest if top is None else top)
