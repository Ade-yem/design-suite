# Standalone Geometry Parser & Viewer

This is a standalone CAD geometry parser and 2D canvas drawing sandbox. It enables uploading DXF drawings (and reference PDF sheets), parsing them using the complete vision parser pipeline (including deterministic heuristics and LLM-based classification), persisting the resulting JSON locally to a cache file, and displaying them dynamically in an interactive HTML5 canvas viewport.

---

## 1. System Components

### A. Python FastAPI Backend (`backend/`)
* **`main.py`**: Serves file upload endpoints, dispatches parsing requests to the parser pipeline, and saves the parsed result to a local cache file `parsed_geometry.json` (queried via `GET /api/parsed`).
* **`parser_pipeline.py`**: The complete multi-stage parsing pipeline copied from the core agent system:
  1. **Beams (Deterministic)**: Extracted directly from DXF LINE entities and nearest text attributes.
  2. **Columns (LLM / Heuristic Fallback)**: Closed rectangular/circular sections classified by Gemini for section sizing and label sequencing.
  3. **Slabs + Voids (LLM / Heuristic Fallback)**: PDF-grounded boundary polygon extraction using column/beam centrelines as visual guidelines.
* **`dxf_parser.py`**: Interacts with the `ezdxf` library to extract lines, polylines, layers, text, and blocks.
* **`pdf_parser.py`**: Interacts with `PyMuPDF` (`fitz`) to extract text annotations from reference sheets.

### B. React + Vite Frontend (`frontend/`)
* **`src/App.tsx`**: Side-by-side IDE layout rendering controls, staged files, entity inspect list, warnings, raw JSON code viewer, and coordinate displays.
* **`src/components/CanvasViewport.tsx`**: CAD viewport rendering members with pan, infinite zoom, gridlines, coordinate markers, and select/hover events.
* **`src/lib/canvas-drawing.ts`**: Normalization and coordinate transforms, shape drawing routines (beams, columns, slabs, voids), dot grids, and priority hit-testing.
* **`src/index.css`**: Vanilla CSS design system for dark mode styling, custom scrollbars, layout divisions, and transitions.

---

## 2. LLM Configuration & Fallback
The parser pipeline uses LangChain and Gemini for column, slab, and void detection.
* To run parsing with LLMs active, set the `GEMINI_API_KEY` environment variable:
  ```bash
  export GEMINI_API_KEY="your-gemini-api-key"
  ```
* If `GEMINI_API_KEY` is not set, or if the LLM call fails, the pipeline automatically falls back to the deterministic spatial heuristics, extracting columns and beams directly.

---

## 3. Quick Start

### Step 1: Run the Backend
Ensure the workspace virtual environment is used to run the uvicorn server:
```bash
# Navigate to the backend directory
cd backend

# Start the server (runs on port 8001)
../../venv/bin/uvicorn main:app --reload --port 8001
```

### Step 2: Run the Frontend
Use `pnpm` to start the Vite developer server:
```bash
# Navigate to the frontend directory
cd frontend

# Start the dev server
pnpm dev
```
