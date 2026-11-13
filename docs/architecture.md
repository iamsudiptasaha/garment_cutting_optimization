# Architecture contract (initial)

1. SVG importer reads grouped original vector shapes and native text.
2. Geometry layer creates solver polygons while preserving source shapes and IDs.
3. Solver adapter accepts instances, allowed rotations {0, 180}, optional clearances and independent width/length bounds.
4. Independent validator checks original-geometry collisions, bounds, counts and transforms.
5. Exporter transforms original SVG objects and emits a placement manifest.

The specific solver API and geometric tolerances are not decided in Phase 0.
