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

Verification measures numerical stability across two polygon resolutions; it is
**not** an exact Bézier-distance proof or a cutter-ready nesting validation.

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
