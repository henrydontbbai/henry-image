# Engineering Diagram Routing

Raster image generation is not reliable for exact engineering drawings. Use deterministic output when the request includes real dimensions, tolerances, manufacturing, CAD-like diagrams, 3D printing, exact labels, or multiple views that must agree.

## Route to Deterministic Output

Prefer deterministic output for requests mentioning:

- 3D printing, CNC, manufacturing, vendor communication, CAD, STL, STEP, OpenSCAD, blueprint, schematic;
- exact dimensions or tolerances;
- front/side/top views that must match;
- exact labels or dimension arrows;
- repeated corrections about geometry, cutouts, cable routing, sealed faces, or structural feasibility.

Preferred deliverables:

- SVG: clean 2D front/side/top views.
- PDF: vendor communication sheet.
- OpenSCAD: simple parameterized 3D concept.
- Markdown spec: dimensions, materials, tolerances, cable routing, open questions.
- Raster concept image: optional preview only.

## 3D Printing Workflow

For “draw this for a 3D printing vendor”:

1. Identify the required precision level:
   - concept preview;
   - dimensioned communication diagram;
   - printable CAD-like model.
2. If dimensions matter, gather or verify authoritative object dimensions.
3. Produce a deterministic dimension sheet before or alongside any raster concept image.
4. Clearly label raster output as a concept preview, not a printable CAD file.

## Stop Rule

After two failed raster iterations involving dimension-critical or structural correctness issues, stop image generation and switch to deterministic SVG/PDF/OpenSCAD/spec output.

Examples of stop-rule triggers:

- top view does not match side view;
- hidden cable path appears exposed;
- sealed faces become hollow;
- exact dimensions are garbled;
- generated labels are unreadable or wrong;
- object proportions drift away from real product dimensions.

## Vendor Spec Checklist

For 3D-printing communication, include:

- authoritative device dimensions;
- required clearances and tolerances;
- material and finish;
- contact surfaces and padding;
- cable-bend radius or cable-channel size;
- visible exterior constraints;
- hidden internal routing constraints;
- open questions for the vendor.
