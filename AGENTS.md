# Development instructions

- Make small, scoped changes. Inspect only relevant modules and tests before editing.
- Do not modify original input SVG files to improve nesting results.
- Do not introduce mirroring. Only 0° and 180° rotations are allowed.
- Treat both width and length as independently enforceable hard limits.
- Do not silently omit required pattern instances or change their quantities.
- Keep original SVG curves and text separate from approximate solver polygons.
- Solver output is untrusted until independently checked for quantity, geometry, bounds, clearance and rotation.
- Distinguish `NOT_FOUND` from `PROVEN_INFEASIBLE`.
- Add focused tests for every new behavior; do not label smoke tests as geometry validation.
- Avoid unrelated refactors. Report commands run, tests passed/failed, and any unverified claims.
