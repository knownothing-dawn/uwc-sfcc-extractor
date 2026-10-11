"""Deterministic coordinates; no automatic interpretation of figure semantics."""
from dataclasses import dataclass
import math
import numpy as np


@dataclass
class Axis:
    scale: str
    slope: float
    intercept: float
    residual_px: float
    anchors: list

    def to_data(self, coordinate):
        value = self.slope * np.asarray(coordinate) + self.intercept
        return 10 ** value if self.scale == "log" else value

    def to_coordinate(self, data):
        data = np.asarray(data, dtype=float)
        if self.scale == "log":
            if np.any(data <= 0):
                raise ValueError("Log axis requires positive data")
            data = np.log10(data)
        return (data - self.intercept) / self.slope


def calibrate_axis(anchors, scale, max_residual_px):
    """Anchors are [image pixel coordinate, labelled data value] pairs."""
    a = np.asarray(anchors, dtype=float)
    if a.ndim != 2 or a.shape[1] != 2 or len(a) < 3 or not np.isfinite(a).all():
        raise ValueError("At least three finite calibration anchors are required")
    if scale not in ("linear", "log"):
        raise ValueError("Unsupported axis; manual review required")
    if not math.isfinite(max_residual_px) or max_residual_px <= 0:
        raise ValueError("Supply a positive validated residual threshold")
    if len(np.unique(a[:, 0])) != len(a) or len(np.unique(a[:, 1])) != len(a):
        raise ValueError("Duplicate ticks are not independent calibration anchors")
    values = a[:, 1]
    if scale == "log":
        if (values <= 0).any():
            raise ValueError("Positive log labels required; do not guess negative-temperature transforms")
        values = np.log10(values)
    slope, intercept = np.polyfit(a[:, 0], values, 1)
    if abs(slope) < np.finfo(float).eps:
        raise ValueError("Degenerate calibration")
    residual = float(np.max(np.abs((values - intercept) / slope - a[:, 0])))
    if residual > max_residual_px:
        raise ValueError(f"Calibration residual {residual:.6g} px exceeds threshold; review axes")
    return Axis(scale, float(slope), float(intercept), residual, a.tolist())


def normalized_points(points, bounds):
    points = np.asarray(points, dtype=float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 2 or not np.isfinite(points).all():
        raise ValueError("A finite ordered trace with at least two points is required")
    xmin, xmax, ymin, ymax = bounds
    span = np.array([xmax - xmin, ymax - ymin], dtype=float)
    if not np.isfinite(bounds).all() or (span <= 0).any():
        raise ValueError("Plot bounds must have positive spans")
    return (points - [xmin, ymin]) / span


def segment_distances(points, start, end):
    delta = end - start
    norm = float(delta @ delta)
    if norm == 0:
        return np.linalg.norm(points - start, axis=1)
    ratio = np.clip((points - start) @ delta / norm, 0, 1)
    return np.linalg.norm(points - (start + ratio[:, None] * delta), axis=1)


def adaptive_indices(points, bounds, tolerance):
    """RDP in normalized data coordinates, preserving endpoints and turning extrema."""
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Explicit positive tolerance required; no production default exists")
    p = normalized_points(points, bounds)
    keep = {0, len(p) - 1}
    for axis in (0, 1):
        # Ignore zero increments but preserve both sides of a plateau reversal.
        nonzero = np.flatnonzero(np.diff(p[:, axis]))
        for previous, current in zip(nonzero[:-1], nonzero[1:]):
            if np.sign(p[previous + 1, axis] - p[previous, axis]) != np.sign(p[current + 1, axis] - p[current, axis]):
                keep.update((int(previous + 1), int(current)))
    anchors = sorted(keep)
    stack = list(zip(anchors[:-1], anchors[1:]))
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        distances = segment_distances(p[start + 1:end], p[start], p[end])
        offset = int(np.argmax(distances))
        if distances[offset] > tolerance:
            index = start + offset + 1
            keep.add(index)
            stack.extend(((start, index), (index, end)))
    return sorted(keep)


def marker_centers(mask, minimum_area, maximum_area):
    """Only for isolated, verified marker masks. Does not classify marker shapes."""
    from scipy.ndimage import label, find_objects, center_of_mass
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2 or minimum_area <= 0 or maximum_area < minimum_area:
        raise ValueError("Invalid marker mask or size bounds")
    labels, count = label(mask, structure=np.ones((3, 3)))
    centers, rejected = [], []
    for i, region in enumerate(find_objects(labels), 1):
        area = int((labels[region] == i).sum())
        if not minimum_area <= area <= maximum_area:
            rejected.append({"component": i, "area": area})
            continue
        y, x = center_of_mass(mask, labels, i)
        centers.append([float(x), float(y)])
    return {"centers": centers, "rejected_components": rejected, "component_count": count}


def trace_columns(mask):
    """Centerline for one isolated, continuous y(x); refuses gaps and overlaps."""
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2:
        raise ValueError("Expected a binary 2-D mask")
    xs = np.flatnonzero(mask.any(axis=0))
    if len(xs) < 2 or np.any(np.diff(xs) != 1):
        raise ValueError("Empty trace or internal gaps; review instead of bridging")
    points = []
    for x in xs:
        ys = np.flatnonzero(mask[:, x])
        if np.any(np.diff(ys) != 1):
            raise ValueError("Multiple runs in column; series identity is ambiguous")
        points.append([float(x), float((ys[0] + ys[-1]) / 2)])
    return points


def flatten_cubic(control, tolerance):
    control = np.asarray(control, dtype=float)
    if control.shape != (4, 2) or not np.isfinite(control).all() or not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("Invalid cubic controls or geometric tolerance")
    stack = [(control, 0)]
    points = [control[0].tolist()]
    while stack:
        c, depth = stack.pop()
        if max(segment_distances(c[1:3], c[0], c[3])) <= tolerance:
            points.append(c[3].tolist())
            continue
        if depth >= 30:
            raise ValueError("Vector flattening failed to meet tolerance")
        ab, bc, cd = (c[0] + c[1]) / 2, (c[1] + c[2]) / 2, (c[2] + c[3]) / 2
        abc, bcd = (ab + bc) / 2, (bc + cd) / 2
        middle = (abc + bcd) / 2
        stack.extend(((np.array([middle, bcd, cd, c[3]]), depth + 1),
                      (np.array([c[0], ab, abc, middle]), depth + 1)))
    return points


def vector_polylines(items, tolerance):
    """Use selected get_drawings items; disconnected subpaths stay separate."""
    lines, current = [], []
    for item in items:
        if item[0] == "l":
            segment = [list(item[1]), list(item[2])]
        elif item[0] == "c":
            segment = flatten_cubic([list(v) for v in item[1:5]], tolerance)
        else:
            raise ValueError("Only selected line/cubic curve items are supported")
        if current and not np.allclose(current[-1], segment[0], rtol=0, atol=1e-9):
            lines.append(current)
            current = []
        current.extend(segment[1:] if current else segment)
    if current:
        lines.append(current)
    return lines


def save_overlay(image_path, output_path, dense_points, retained_points):
    from PIL import Image, ImageDraw
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    if len(dense_points) > 1:
        draw.line([tuple(p) for p in dense_points], fill=(0, 180, 220), width=2)
    for x, y in retained_points:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), outline=(230, 0, 100), width=2)
    image.save(output_path)
