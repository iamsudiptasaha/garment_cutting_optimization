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

## Stable input / processor / output boundaries

```text
input/                            Source SVG files (not modified)
src/garment_nesting/input/        SVG parsing and inventory
src/garment_nesting/processor/    PackingSolver adapter, optimization, validation
src/garment_nesting/geometry/     Processor's polygon utilities
src/garment_nesting/output/       Exact-path SVG export and continuous PNG preview
output/                           Generated SVG, PNG and JSON (ignored by Git)
```

Input and export modules are intended to remain stable while we tune the
nesting algorithm. Legacy `importers` and `solvers` imports still work.

## Phase 3: fixed-width nesting in inches

Fabric width is entered in **inches**; source SVG millimetres are converted
automatically. Patterns must already follow the fabric length/grain direction
along SVG Y. The solver may rotate pieces only 0°/180° (or 0° with
`--one-way`). Mirroring is prohibited.

Requires Python 3.12 or 3.13 to execute PackingSolver on an Apple Silicon Mac:

```bash
python -m pip install -e '.[dev,geometry,solver,output]'
garment-nesting nest "samples/FC_HH_Full_Pyjama.svg" \
  --fabric-width-in 60 --clearance-in 0.04 \
  --time-limit 30 --output-prefix trial
```

**60 inches here is only a sample input.** Enter your actual fabric width.
There is no fabric-length input; `open-dimension-y` minimizes the
**total length of fabric consumed**.

Outputs are `trial.instance.json` (solver input), `trial.manifest.json`
(piece-to-ID mapping), `trial.solution.json` (solver certificate),
`trial.report.json` (validated lengths, wastage and placements),
`trial.nested.svg` (editable vector layout) and `trial.nested.pdf`
(true-size continuous PNG preview). The height in the solver input is a generous internal
search ceiling, not a requested fabric length. Fabric length consumed is
`max(piece_end_y) - min(piece_start_y)`, in inches, independent of any blank
space before the layout. Wastage is `(fabric_width_in * length_consumed_in -
 total_piece_area_sq_in) / (fabric_width_in * length_consumed_in) * 100`,
where the piece area is the sum of the actual polygon areas (not bounding
rectangles). A complete solution is reported only after all required pieces
pass an independent overlap/width check.

If you only want to create solver input without optimization, this also works
with Python 3.11 and the geometry dependencies:

```bash
garment-nesting prepare "samples/FC_HH_Full_Pyjama.svg" \
  --fabric-width-in 60 --output-prefix trial
```

The `nest` command now exports `output/nesting.nested.svg` and
`output/nesting.nested.png` in addition to its JSON files. It **does not**
redraw original shapes as polygons: the source Bézier paths and grouped
text are retained, with placement transforms applied to each group.

For a new input, place an SVG under `input/` and run:

```bash
python -m pip install -e '.[dev,geometry,solver,output]'
garment-nesting nest "input/your-pattern.svg" --fabric-width-in 36 --time-limit 30
```

For an already computed layout, regenerate the visual outputs *without*
running the solver again:

```bash
garment-nesting render "input/your-pattern.svg" \
  --manifest output/nesting.manifest.json \
  --report output/nesting.report.json
```

The PNG is one continuous scrollable image (no pages or cuts), intended for
sharing with floor operators. It defaults to 72 preview pixels per inch
(`--preview-ppi` is configurable), and is automatically scaled down only
when needed to respect image-size limits. If a very long image would become
unreadable, export fails rather than silently reducing its resolution further.
The editable SVG remains the full-length, physically accurate cutting master.
All fabric measurements in reports remain in inches or square inches.


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
