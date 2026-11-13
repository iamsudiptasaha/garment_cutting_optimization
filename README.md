# Garment Nesting

A standalone Python project for nesting labelled CorelDRAW-exported SVG garment patterns.

## Scope
- Preserve original vector paths and internal text labels.
- Allow **only 0° and 180° rotation**; no mirroring.
- Support width-only, length-only, and simultaneous width/length bounds.
- Never silently drop required pattern instances.
- Validate exported geometry independently of the solver.
- Report `NOT_FOUND` separately from mathematically proven infeasibility.

## Phase 0: local setup

Requires Python 3.11 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
python -m ruff check src tests
python -m garment_nesting.cli --version
```

Install the geometry dependencies with `python -m pip install -e '.[dev,geometry]'`.
No nesting solver is installed or integrated yet.

### Geometry reports

```bash
# JSON audit of areas, bounds, topology and any bounded repairs
garment-nesting audit samples/FC_HH_Full_Pyjama.svg --output geometry-audit.json

# Compare polygon resolution; returns code 2 if any verification fails
garment-nesting verify samples/FC_HH_Full_Pyjama.svg --output geometry-verification.json
```

A `valid: true` geometry entry may have `repaired: true`. This means the
approximate polygon had a small self-touch and Shapely recovered a **single**
polygon with no holes, less than 0.25 mm of residual linework and boundary
change, and less than 0.001% area change. Every repair includes
`repair_details`. Larger spikes, bowties, separate polygons and major outline
changes remain errors. Original SVG paths and labels are **never edited**.

The `verify` command also performs an **original-curve guard**: each Bézier
control hull is subdivided independently of polygon flattening until it fits
inside a 0.25 mm envelope of the candidate polygon boundary. A shape that
cannot be certified fails verification, even if the coarse/fine polygon
comparison happens to agree. The JSON reports `source_curve_guard_passed`,
`source_curve_guard_mm` and `minimum_solver_buffer_mm`.

**Required future solver rule:** inflate each verified solver polygon outward
by at least its `minimum_solver_buffer_mm` before placement checks. This field
is an advisory requirement until a solver and independent final-layout
validator are implemented; the current project does **not** enforce clearance
between pieces. The curve guard proves only directed original-curve-to-polygon
boundary containment. It does not prove symmetric shape equivalence, original
topology, or that the original filled path is entirely inside the polygon's
buffer. Never label a nested layout cutter-safe from this check alone.

## Phase 3: first packing adapter (inches)

The fabric width is always entered in **inches**. Source SVG dimensions are
converted from millimetres automatically. The drawing must already have all
cutting pieces aligned with the intended fabric grain direction (vertical/Y).

The following command builds an instance for PackingSolver's irregular
**open-dimension-y** objective:

```bash
python -m pip install -e '.[dev,geometry]'
garment-nesting prepare "samples/FC_HH_Full_Pyjama.svg" \
  --fabric-width-in 60 --output-prefix trial
```

This produces \`trial.instance.json\` (PackingSolver-compatible) and
\`trial.manifest.json\` (source IDs, inch dimensions and validation shapes).
The height field inside the solver input is only a generous *search ceiling*,
not a requested marker length or a fabric-length input.

If you have separately installed the \`packingsolver_irregular\` command-line
solver, optimize and validate in one step:

```bash
garment-nesting nest "samples/FC_HH_Full_Pyjama.svg" \
  --fabric-width-in 60 --clearance-in 0.04 \
  --time-limit 30 --output-prefix trial
```

The \`nest\` command writes a solution certificate and a validated JSON
report containing \`fabric_length_consumed_in\`, \`utilization_pct\`, and
piece placements. If no complete solution was found, it returns \`NOT_FOUND\`
rather than pretending omitted pieces are a valid arrangement.

To validate an existing certificate without running the solver:

```bash
garment-nesting evaluate --manifest trial.manifest.json \
  --certificate trial.solution.json --output trial.report.json
```

Only 0° and 180° rotations are permitted; use \`--one-way\` to permit only
0°. Mirroring is always forbidden. Current certificate checks cover piece
counts, rotation, fabric width, clearance, and polygon overlap. The native
editable SVG output is a *later step* and is not produced here.

**Solver availability:** The external \`packingsolver_irregular\` executable is
not bundled by this project. \`prepare\` and \`evaluate\` work without it; the
\`nest\` command requires the executable on PATH (or \`--solver-binary\`).

## Milestones
- Phase 0: packaging, fixture, smoke tests, CI.
- Phase 1: import SVG groups, outlines, text and transforms.
- Phase 2: geometry validation and curve approximation.
- Phase 3: constrained solver integration.
- Phase 4: original-SVG export and independent collision validation.
- Phase 5: benchmarking and secondary solver.
- Phase 6: operator interface.

## Fixture
`samples/FC_HH_Full_Pyjama.svg` is the provided sample. Keep it unmodified; all geometry claims require explicit tests in later phases.
