"""Execute the optional native PackingSolver optimizer (no input/output formatting)."""
from __future__ import annotations

from pathlib import Path


def solve_instance(instance_path: str | Path, certificate_path: str | Path, time_limit: int) -> None:
    if time_limit <= 0:
        raise ValueError("Optimization time limit must be positive")
    try:
        import packingsolver.irregular as psi
    except ImportError as exc:
        raise RuntimeError(
            'Native PackingSolver requires Python >=3.12 and pip install -e ".[solver]"'
        ) from exc
    builder = psi.InstanceBuilder()
    builder.read(str(instance_path))
    params = psi.OptimizeParameters()
    params.time_limit = time_limit
    output = psi.optimize(builder.build(), params)
    output.solution.write(str(certificate_path))
