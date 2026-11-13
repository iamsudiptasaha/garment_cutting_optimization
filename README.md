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
The optional native PackingSolver integration is described under Phase 3.

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

The MVP uses a finite-chord adaptive approximation for SVG curves. It
retains explicit line-segment notches and automatically repairs small outline
artifacts when they meet the existing repair limits. Larger invalid outlines
are reported rather than silently placed.

`verify` reports area and boundary differences at two approximation
resolutions, but does not reject shapes for small differences by default.
Original paths and labels remain unchanged. No nesting solver or final
collision checker is implemented yet. When nesting is added, a small
configurable clearance can absorb approximation error without requiring
mathematically exact curve reconstruction.

## Phase 3: fixed-width nesting in inches

Fabric width is entered in **inches**; source SVG millimetres are converted
automatically. Patterns must already follow the fabric length/grain direction
along SVG Y. The solver may rotate pieces only 0°/180° (or 0° with
`--one-way`). Mirroring is prohibited.

Requires Python 3.12 or 3.13 to execute PackingSolver on an Apple Silicon Mac:

```bash
python -m pip install -e '.[dev,geometry,solver]'
garment-nesting nest "samples/FC_HH_Full_Pyjama.svg" \
  --fabric-width-in 60 --clearance-in 0.04 \
  --time-limit 30 --output-prefix trial
```

**60 inches here is only a sample input.** Enter your actual fabric width.
There is no fabric-length input; `open-dimension-y` minimizes the
**total length of fabric consumed**.

Outputs are `trial.instance.json` (solver input), `trial.manifest.json`
(piece-to-ID mapping), `trial.solution.json` (solver certificate) and
`trial.report.json` (validated placements, length consumed in inches,
utilization and counts). The height in the solver input is a generous internal
search ceiling, not a requested fabric length. A complete solution is reported
only after all required pieces pass an independent overlap/width check.

If you only want to create solver input without optimization, this also works
with Python 3.11 and the geometry dependencies:

```bash
garment-nesting prepare "samples/FC_HH_Full_Pyjama.svg" \
  --fabric-width-in 60 --output-prefix trial
```

The optimized editable CorelDRAW-compatible SVG is not yet generated; it is
the next integration step.

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
