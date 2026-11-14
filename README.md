# Garment Nesting

A standalone Python project for nesting labelled CorelDRAW-exported SVG garment patterns.

## Scope
- Preserve original vector paths and internal text labels.
- Allow **only 0° and 180° rotation**; no mirroring.
- Support width-only, length-only, and simultaneous width/length bounds.
- Never silently drop required pattern instances.
- Validate exported geometry independently of the solver.
- Report `NOT_FOUND` separately from mathematically proven infeasibility.

## Local GUI and Windows/macOS desktop builds (foundation)

For local development on a Mac or Windows PC, in the existing virtual environment:

~~~bash
python -m pip install -e ".[dev,geometry,solver,output,app]"
python -m garment_nesting.app dev
~~~

Open http://127.0.0.1:8080. Python edits reload the local GUI.
After a code update use `git pull origin main` and restart the command.
The default packaged application opens a small **Start Server / Stop Server**
desktop window; pressing Start exposes the browser GUI to the trusted LAN.
The GUI inventories and validates multiple SVG uploads and provides editable
per-pattern inclusion, copies (0–10,000), extra keep-out margin,
and allowed rotations (0°, 180°, or both), with live piece totals and immediate
table rendering after upload. Zero copies are valid and do not produce solver
instances. Fabric inputs include width, selvedges, end margins, base gap,
an optional maximum length, and an optimizer time budget.
These inputs are validated and previewable but are currently browser-session
state, not yet consumed by the existing PackingSolver CLI. Algorithm selection, persistent job storage, model
comparison and selected-result export are upcoming stages.

Each push to `main` automatically builds a zipped Windows x64 app and
macOS Apple Silicon/Intel apps as GitHub Actions artifacts.
See [desktop development and deployment](docs/runbooks/local-desktop.md)
for detailed steps and current security/release limitations.

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
Original paths and labels remain unchanged. The current solver validates approximate polygon placements but does not yet
certify the exact original SVG curve envelopes. Clearance is configurable.

## Stable input / processor / output boundaries

```text
input/                            Source SVG files (not modified)
src/garment_nesting/input/        SVG parsing and inventory
src/garment_nesting/processor/    PackingSolver adapter, optimization, validation
src/garment_nesting/geometry/     Processor's polygon utilities
src/garment_nesting/output/       annotated SVG export and continuous PNG/JPEG previews
output/                           Generated SVG, PNG, JPEG and JSON (ignored by Git)
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
`trial.nested.svg` (editable annotated vector layout),
`trial.nested.png` (one lossless long image) and
`trial.nested.jpg` (one JPEG for phone sharing) and
`trial.nested.html` (one offline zoomable vector viewer). The height in the solver input is a generous internal
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

The `nest` command now exports `output/nesting.nested.svg`,
`output/nesting.nested.png`, `output/nesting.nested.jpg` and
`output/nesting.nested.html` alongside JSON. It **does not**
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

The output SVG keeps original Bézier curves, group IDs and text labels. It has
a separate `fabric-guide` layer with a clearly outlined fabric rectangle,
dimension brackets, fabric width and **length consumed** in inches, wastage,
utilization, and piece count. Its canvas includes annotation margins **outside**
the precisely measured fabric rectangle: use `fabric-boundary` as the fabric
measurement, rather than the larger annotated page size.

The PNG and JPEG show the **same single continuous strip**, never separate
pages. Both render at **5000 pixels wide by default** (`--preview-width-px`
can be set to 6000 or another value, subject to memory limits). Text/lines are vector rendered
at the target resolution; JPEG uses quality 95 with no chroma subsampling.
The image is for viewing and sharing, not physical-scale cutting.
For extremely long layouts, an explicit error is returned if one high-quality
image would exceed the image-size limit; there is no silent quality reduction.
A larger file in MB does not guarantee legibility: messaging apps may shrink
long images before showing them. For reliable close inspection, open the one
`nested.html` file in a browser and press **+** to zoom; it retains every SVG
curve and label, scrolls as one continuous strip and works offline.
To avoid WhatsApp recompressing the operator JPEG, share it as a document.

To rerender a saved solution without running the solver again:

```bash
python -m garment_nesting.cli render "samples/FC_HH_Full_Pyjama.svg" \
  --manifest output/nesting.manifest.json \
  --report output/nesting.report.json \
  --preview-width-px 5000
```

On macOS, CairoSVG requires Homebrew's Cairo library. If the command-line
launcher cannot find it, run `brew install cairo`, export
`DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix cairo)/lib"`, and invoke
`python -m garment_nesting.cli`.


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
