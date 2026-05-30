"""Drift metrics — coupling, risk, and dependency entropy computations."""

import math


def compute_coupling_delta(old: float, new: float) -> float:
    return new - old


def compute_risk_delta(old: float, new: float) -> float:
    return compute_coupling_delta(old, new)


def compute_entropy(edges: int, nodes: int) -> float:
    if nodes == 0:
        return 0.0
    return math.log(edges + 1) / math.log(nodes + 1)
