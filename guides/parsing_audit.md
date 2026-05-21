Parsing Pipeline Audit
  
  Root Cause #1 — Wrong Unit Conversion (Critical)

  The DXF file has $INSUNITS = 1 (inches) in its header, but the drawing is physically modelled in
  millimetres. The raw $EXTMIN/$EXTMAX confirm this: the floor plan spans 23.38 m × 34.88 m in raw
  drawing units — only sensible as mm.

  The parser trusts $INSUNITS = 1 and blindly applies a × 25.4 (inch→mm) factor. Every coordinate in
  the output is therefore 25.4× too large. Concretely:

  ┌─────────────────────────────────┬──────────────────────┐
  │   What the extractor produces   │  What it should be   │
  ├─────────────────────────────────┼──────────────────────┤
  │ Column section: 5715 × 5715 mm  │ 225 × 225 mm ✓       │
  ├─────────────────────────────────┼──────────────────────┤
  │ Beam span (e.g. 1B1): 76 200 mm │ 3 000 mm = 3.0 m ✓   │
  ├─────────────────────────────────┼──────────────────────┤
  │ Beam 1B11 span: 93 345 mm       │ 3 675 mm = 3.675 m ✓ │
  ├─────────────────────────────────┼──────────────────────┤
  │ Beam 1B2 span: 31 115 mm        │ 1 225 mm = 1.225 m ✓ │
  └─────────────────────────────────┴──────────────────────┘

  Every single number in res.txt is exactly 25.4× its correct value. The spans are not "wrong" in
  structure — they are just reported in phantom inches-as-millimetres.

  Fix — The unit resolver in dxf_parser.py:_resolve_units must cross-validate $INSUNITS against
  $EXTMIN/$EXTMAX. A building measuring thousands of metres is impossible; this should trigger a
  fallback to factor = 1.0 with a warning:

  # In _resolve_units, after resolving factor from $INSUNITS:
  extmin = doc.header.get("$EXTMIN", Vec3(0, 0, 0))
  extmax = doc.header.get("$EXTMAX", Vec3(0, 0, 0))
  implied_width_m = abs(extmax.x - extmin.x) * factor / 1000
  if implied_width_m > 300 and factor > 1.0:
      # Header unit is almost certainly wrong — building cannot be >300 m
      factor = 1.0
      warning = f"$INSUNITS={raw} implies {implied_width_m:.0f} m width. Overriding factor to 1.0
  (mm). VERIFY."

  ---
  Root Cause #2 — BeamText Layer Misclassified as beam_candidate
  
  The layer name BeamText matches the regex r"beam" → beam_candidate. This layer holds 90 TEXT 
  entities carrying the authoritative labels and sections (e.g. 1B1 225x450). These get passed as
  geometry candidates to the LLM.

  The consequence: the 347 "beam candidates" sent to the LLM contain 257 geometry entities plus 90
  text entities masquerading as shapes. This pollutes the candidate list and confuses the LLM on which
   entries are geometry vs. annotation.

  Fix — In _prepare_candidates_summary (parser.py:166), TEXT/MTEXT entities must be excluded from the
  geometry candidate list regardless of layer hint:

  # Skip text entities — they are annotations, not geometry candidates
  if ent.get("dxf_type") in ("TEXT", "MTEXT"):
      continue

  The text entities should instead be used exclusively as the nearest_text pool for the geometry
  candidates — which is already how the function works, but the filter is missing.

  ---
  Root Cause #3 — 76 Columns Found, Only 2 Output
  
  With the × 25.4 bug, all 76 column LWPOLYLINE entities appear as 5715 mm × 5715 mm blocks. The LLM
  receives 76 candidates all with identical, implausible dimensions and only classifies 2 as columns —
   it probably rejects the rest as non-structural due to the absurd size. Once Root Cause #1 is fixed,
   these will read as 225 mm × 225 mm and all 76 should be correctly classified.

  There is a secondary issue: the column "geometry" is the bay-zone outline, not just the section. The
   centroid of each 225 mm × 225 mm square IS the column position, which is correct. The b and h
  values (section dimensions) also become correct at 225 mm. No structural interpretation changes are
  needed here beyond fixing the factor.

  ---
  Root Cause #4 — Beam Spans Are Edge-Line Lengths, Not Centre-to-Centre Spans
  
  The Beam layer holds pairs of parallel lines representing the two long edges of each beam in plan.
  The LLM is given the bounding-box width/height of each LINE entity as the span. This conflates:


  The text entities should instead be used exclusively as the nearest_text pool for the geometry
  candidates — which is already how the function works, but the filter is missing.

  ---
  Root Cause #3 — 76 Columns Found, Only 2 Output

  With the × 25.4 bug, all 76 column LWPOLYLINE entities appear as 5715 mm × 5715 mm blocks. The LLM
  receives 76 candidates all with identical, implausible dimensions and only classifies 2 as columns —
   it probably rejects the rest as non-structural due to the absurd size. Once Root Cause #1 is fixed,
   these will read as 225 mm × 225 mm and all 76 should be correctly classified.

  There is a secondary issue: the column "geometry" is the bay-zone outline, not just the section. The
   centroid of each 225 mm × 225 mm square IS the column position, which is correct. The b and h
  values (section dimensions) also become correct at 225 mm. No structural interpretation changes are
  needed here beyond fixing the factor.

  ---
  Root Cause #4 — Beam Spans Are Edge-Line Lengths, Not Centre-to-Centre Spans

  The Beam layer holds pairs of parallel lines representing the two long edges of each beam in plan.
  The LLM is given the bounding-box width/height of each LINE entity as the span. This conflates:

  - Edge-line length (total run of the beam across the drawing)
  - Clear span (distance between column faces)

  A beam that runs edge-to-edge across three bays will have one LINE entity spanning all three bays.
  The LLM has no column-position data to split this into individual spans.

  Once the unit bug is fixed the lengths become: 3.0 m, 3.675 m, 2.1 m, 1.425 m, etc. — these are
  structurally plausible single spans in a close-column secondary beam grid. But the pipeline would
  still be wrong for multi-bay beam runs.

  Fix — After fixing units, add a span-splitting step in _prepare_candidates_summary: for each LINE
  candidate, project all column centroids onto the line direction, find those that fall within the
  line's extent, and split the beam into column-to-column spans. This is deterministic and does not
  require the LLM.

  ---
  Root Cause #5 — No Slabs in the DXF; No Void Concept Anywhere
  
  The DXF contains zero slab entities. The layer inventory has no slab-hint layer. The drawing
  convention on this file is "floor beam plan" only — slabs are implied and would appear in a separate
   slab drawing or in the PDF notes.

  There is also no representation of voids anywhere in the DXF or in the pipeline schema.

  Fix — Slabs and voids must be extracted from the PDF. The current LLM prompt does not explicitly ask
   for this. The prompt should be split: one prompt for the DXF candidates (beams + columns), one
  prompt directed specifically at the PDF asking for slab panels, slab types, void locations, and
  openings.

  ---
  Root Cause #6 — LLM Prompt Does Not Use the PDF Strategically

  The PDF is base64-encoded and appended as a file block, but the prompt text only talks about DXF
  candidates. The LLM sees a visual floor plan PDF but receives no instruction to read it for
  structural context. In practice the LLM is ignoring the PDF and working only from the JSON candidate
   list.

  Fix — Split into two LLM calls:

  1. DXF geometry call — existing candidates JSON, focused on beams and columns from DXF geometry.
  Short, structured prompt, small candidate list (after filtering TEXT entities).
  2. PDF layout call — dedicated prompt that asks the LLM to look at the PDF and extract: slab panels
  (type, thickness, span direction, dimensions), openings/voids (location and size), any column
  section schedule in the drawing notes, and any information that contradicts the DXF-extracted
  geometry.

  ---
  Root Cause #7 — _fallback_members_heuristics Uses Bbox as Column Section
  
  The fallback at parser.py:243 directly uses round(w) and round(h) as column b and h. With the inch
  bug unfixed this produces 5715 mm columns; even after the fix it would produce correct 225 mm
  columns — but only for future drawings that happen to draw column sections at true scale, which is
  not universal.

  ---
  Is the DXF Parser Feasible?

  Yes, but it must be repositioned. The DXF parser is good at three specific things:

  ┌────────────────────────────┬─────────────────────────────────────────────┐
  │        DXF strength        │                 Use it for                  │
  ├────────────────────────────┼─────────────────────────────────────────────┤
  │ Exact member positions     │ Column centroids, beam grid layout          │
  ├────────────────────────────┼─────────────────────────────────────────────┤
  │ Layer-encoded member types │ Discriminating beams from columns from axes │
  ├────────────────────────────┼─────────────────────────────────────────────┤
  │ Text labels                │ Member IDs (1B1 etc.), section annotations  │
  └────────────────────────────┴─────────────────────────────────────────────┘

  The DXF parser is not the right tool for:
  - Section schedules (often only in PDF or title block)
  - Slab geometry (usually a separate drawing or PDF)
  - Voids / openings (architectural, not structural)
  - Structural intent (primary vs secondary beams, continuity)
  
  Recommended architecture:

  DXF (deterministic)          PDF (vision LLM)
  ─────────────────            ──────────────────
  Column positions         +   Section schedules
  Beam grid geometry           Slab panels + voids
  Member label text            Notes / overrides
                      ↓
           Reconciliation LLM
           (merge, resolve conflicts, output final member list)

  The current "send 423 raw candidates to a single LLM call" approach is inherently fragile at scale.
  Separating geometric extraction (deterministic, from DXF) from semantic extraction (PDF vision LLM)
  and using the LLM only for reconciliation makes each step auditable and correctable.

  ---
  Prioritised Fix List

  ┌─────┬─────────────────────────────────────────────┬───────────────────────────────┬────────────┐
  │  #  │                     Fix                     │            Impact             │ Complexity │
  ├─────┼─────────────────────────────────────────────┼───────────────────────────────┼────────────┤
  │ 1   │ Cross-validate $INSUNITS against            │ Fixes all numeric outputs     │ Low        │
  │     │ $EXTMIN/$EXTMAX in _resolve_units           │ immediately                   │            │
  ├─────┼─────────────────────────────────────────────┼───────────────────────────────┼────────────┤
  │     │ Filter TEXT/MTEXT from geometry candidates  │ Reduces candidate noise,      │            │
  │ 2   │ in _prepare_candidates_summary              │ fixes misclassified BeamText  │ Low        │
  │     │                                             │ layer                         │            │
  ├─────┼─────────────────────────────────────────────┼───────────────────────────────┼────────────┤
  │ 3   │ Add column-centroid-based span splitting    │ Correct clear spans for       │ Medium     │
  │     │ for beam LINE entities                      │ multi-bay beam runs           │            │
  ├─────┼─────────────────────────────────────────────┼───────────────────────────────┼────────────┤
  │ 4   │ Add second LLM call for PDF: extract slabs, │ Fills the slab/void gap       │ Medium     │
  │     │  voids, section schedules                   │ entirely                      │            │
  ├─────┼─────────────────────────────────────────────┼───────────────────────────────┼────────────┤
  │ 5   │ Revise LLM prompt to reference column       │ Allows LLM to use structural  │ Low        │
  │     │ positions explicitly                        │ context for span calculation  │            │
  ├─────┼─────────────────────────────────────────────┼───────────────────────────────┼────────────┤
  │ 6   │ Cap the candidate list sent to the LLM      │ Prevents prompt overflow on   │ Low        │
  │     │ (deduplicate, limit to top N)               │ large drawings                │            │
  └─────┴─────────────────────────────────────────────┴───────────────────────────────┴────────────┘

  Fix #1 alone will make all the numbers correct. Fixes #1 + #2 should immediately produce 76 columns
  at 225×225 mm and 90 beams with accurate spans. Fixes #3–#6 are needed to get slabs, voids, and
  correct multi-span beams.