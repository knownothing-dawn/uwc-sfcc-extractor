"""Offline benchmark comparison. Interpolation here never enters extraction data."""
import argparse
import csv
import json
import time
from pathlib import Path
import numpy as np
from geometry import adaptive_indices, normalized_points


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    return np.array([[float(r["temperature"]), float(r["uwc"])] for r in rows])


def paired_coordinate_metrics(automatic, reference, bounds):
    a, r = np.asarray(automatic, float), np.asarray(reference, float)
    if a.shape != r.shape or len(a) == 0:
        raise ValueError("Paired references of equal nonzero length are required")
    an, rn = normalized_points(a, bounds), normalized_points(r, bounds)
    error, normalized = np.abs(a - r), np.abs(an - rn)
    return {"temperature_mae": float(error[:, 0].mean()), "uwc_mae": float(error[:, 1].mean()),
            "normalized_x_mae": float(normalized[:, 0].mean()), "normalized_y_mae": float(normalized[:, 1].mean())}


def marker_metrics(automatic, reference, bounds, match_tolerance):
    from scipy.optimize import linear_sum_assignment
    if match_tolerance <= 0:
        raise ValueError("Explicit positive matching tolerance required")
    a, r = np.asarray(automatic, float), np.asarray(reference, float)
    if len(a) == 0 or len(r) == 0:
        return {"true_positive": 0, "false_positive": len(a), "false_negative": len(r), "precision": None if len(a) == 0 else 0.0, "recall": None if len(r) == 0 else 0.0}
    # Support one marker; unlike a trace it need not have two points.
    spans = np.array([bounds[1] - bounds[0], bounds[3] - bounds[2]])
    if (spans <= 0).any() or not np.isfinite(a).all() or not np.isfinite(r).all():
        raise ValueError("Finite coordinates and positive plot spans required")
    distances = np.linalg.norm((a[:, None, :] - r[None, :, :]) / spans, axis=2)
    # Penalize forbidden pairs enough to maximize valid one-to-one match count.
    cost = np.where(distances <= match_tolerance, distances, (max(len(a), len(r)) + 1) * match_tolerance)
    row, col = linear_sum_assignment(cost)
    tp = int((distances[row, col] <= match_tolerance).sum())
    return {"true_positive": tp, "false_positive": len(a) - tp, "false_negative": len(r) - tp,
            "precision": tp / len(a), "recall": tp / len(r)}


def curve_geometry_metrics(automatic, reference, bounds):
    """Symmetric normalized point-to-polyline distances for benchmark use only."""
    a=normalized_points(np.asarray(automatic,float),bounds);r=normalized_points(np.asarray(reference,float),bounds)
    if len(a)<2 or len(r)<2: raise ValueError('Each benchmark curve needs at least two points')
    def directed(points,line):
        return np.asarray([min(float(np.linalg.norm(p-line[i])) if np.allclose(line[i],line[i+1]) else
            float(np.linalg.norm(p-(line[i]+np.clip(np.dot(p-line[i],line[i+1]-line[i])/np.dot(line[i+1]-line[i],line[i+1]-line[i]),0,1)*(line[i+1]-line[i]))))
            for i in range(len(line)-1)) for p in points])
    ar=directed(a,r);ra=directed(r,a);both=np.r_[ar,ra]
    return {'automatic_to_reference_mean_normalized_distance':float(ar.mean()),
            'automatic_to_reference_max_normalized_distance':float(ar.max()),
            'reference_to_automatic_mean_normalized_distance':float(ra.mean()),
            'reference_to_automatic_max_normalized_distance':float(ra.max()),
            'symmetric_mean_normalized_distance':float(both.mean()),
            'symmetric_max_normalized_distance':float(both.max())}


def compare(trace, reference, bounds, fixed_count, temperature_step, tolerance):
    trace, reference = np.asarray(trace, float), np.asarray(reference, float)
    normalized_points(trace, bounds)
    normalized_points(reference, bounds)
    if np.any(np.diff(trace[:, 0]) <= 0) or np.any(np.diff(reference[:, 0]) <= 0):
        raise ValueError("Benchmark requires one branch with strictly increasing temperatures")
    if reference[0, 0] < trace[0, 0] or reference[-1, 0] > trace[-1, 0]:
        raise ValueError("Reference extends beyond trace; extrapolation is prohibited")
    if fixed_count < 2 or temperature_step <= 0 or not np.isfinite(temperature_step):
        raise ValueError("Invalid candidate sampling parameters")
    reports = []
    for method in ("fixed_point_count", "fixed_temperature_interval", "adaptive_shape_preserving"):
        start = time.perf_counter()
        if method == "adaptive_shape_preserving":
            sampled = trace[adaptive_indices(trace, bounds, tolerance)]
        else:
            if method == "fixed_point_count":
                x = np.linspace(trace[0, 0], trace[-1, 0], fixed_count)
            else:
                x = np.unique(np.r_[np.arange(trace[0, 0], trace[-1, 0], temperature_step), trace[-1, 0]])
            sampled = np.column_stack((x, np.interp(x, trace[:, 0], trace[:, 1])))
        elapsed = time.perf_counter() - start
        error = np.abs(np.interp(reference[:, 0], sampled[:, 0], sampled[:, 1]) - reference[:, 1])
        normalized = error / (bounds[3] - bounds[2])
        reports.append({"method": method, "point_count": len(sampled), "uwc_reconstruction_mae": float(error.mean()),
                        "normalized_reconstruction_mae": float(normalized.mean()), "normalized_reconstruction_max": float(normalized.max()),
                        "sampling_runtime_seconds": elapsed})
    return {"benchmark_scope": "continuous_curve_sampling_only", "production_threshold_validated": False,
            "settings": {"fixed_count": fixed_count, "temperature_step": temperature_step, "normalized_error_tolerance": tolerance, "bounds": list(bounds)},
            "results": reports}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("trace", "reference", "out"):
        p.add_argument("--" + arg, required=True)
    p.add_argument("--bounds", nargs=4, type=float, required=True)
    p.add_argument("--fixed-count", type=int, required=True)
    p.add_argument("--temperature-step", type=float, required=True)
    p.add_argument("--tolerance", type=float, required=True)
    args = p.parse_args()
    result = compare(read_csv(args.trace), read_csv(args.reference), args.bounds, args.fixed_count, args.temperature_step, args.tolerance)
    result["trace_file"] = str(Path(args.trace).resolve())
    result["reference_file"] = str(Path(args.reference).resolve())
    Path(args.out).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
