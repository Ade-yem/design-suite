---
trigger: always_on
---

This is information about this project for you as a project manager and lead developer

---

# Product Brief: AI-Driven Structural Design Copilot

## 1. Executive Summary
**Objective:** To automate the transition from architectural drawings (DXF) to finalized structural engineering details using a multi-agent AI system.
**Core Value Prop:** Reducing the "drafting-to-calculation" bottleneck by allowing an AI to interpret geometry, run verified engineering tools, and draft the results—all while keeping the human engineer in a supervisory "confirm/edit" role.

---

## 2. System Architecture & Agentic Workflow
The project utilizes a **StateGraph-driven pipeline** to ensure a rigorous, iterative design process.

### Stage 1: The Vision & Parsing Agent (The "Eyes")
* **Input:** DXF/PDF file upload.
* **Process:** Converts vector data into a standardized **Structural JSON Schema**.
* **Responsibility:** Identifies geometric entities (lines, polylines, blocks) and classifies them as structural members like columns, beams, and slabs.
* **PM Note:** This stage requires a **Human-in-the-Loop** gate. The system must pause for user verification of the parsed geometry on the Canvas before proceeding.

### Stage 2: The Analyst Agent (The "Global Physics")
* **Input:** Verified Structural JSON.
* **Process:** Assembles the **GlobalMatrixSolver** for 2D frame analysis.
* **Responsibility:** Performs load takedown and calculates global reactions, displacements, and internal force envelopes (Shear $V$, Moment $M$, Axial $N$).
* **Technical Detail:** Uses a 2D frame element model (Euler-Bernoulli) to handle nodal loads and member UDLs.

### Stage 3: The Designer Agent (The "Local Material")
* **Input:** Analysis results + Design Codes (e.g., BS 8110, Eurocode 2).
* **Process:** Orchestrates data for hard-coded Python design scripts.
* **Responsibility:** Executes iterative reinforcement design (e.g., iterative effective depth calculation for beams).
* **Output:** A **Designed Member JSON** containing reinforcement schedules and code-compliance logs.

### Stage 4: The Drafting Agent (The "Hands")
* **Input:** Designed Member JSON.
* **Process:** Translates numerical design data into visual coordinates.
* **Responsibility:** Generates 2D structural details (Sections/Elevations) via the **HTML5 Canvas API**.

---

## 3. User Interface: The Structural IDE
The frontend is a **Side-by-Side Integrated Development Environment**.

* **Left Panel (Conversational AI):**
    * Threaded chat history and status logs for each agent (e.g., "Analyst is calculating moment envelopes").
    * Actionable "Confirm" buttons to pass the "Safety Gates" between agents.
* **Right Panel (Interactive Canvas):**
    * **Layer Management:** Toggle between Architectural (original DXF) and Structural (AI-generated) views.
    * **Direct Manipulation:** Users can click and edit member properties or manually adjust rebar on the drawing.
* **Central Data Sync:** Changes in the chat (e.g., "Increase beam depth") must instantly trigger a re-analysis on the Canvas.

---

## 4. Technical Stack
* **Frontend:** React.js + Konva.js/Fabric.js for Canvas rendering.
* **Backend:** FastAPI (Python).
* **Core Libraries:** `ezdxf` (parsing), `numpy` (matrix solver), and specialized design suites (e.g., BS 8110, EC2).
* **Orchestration:** LangGraph for managing agent states and iterative loops.

---

## 5. Success Metrics & Safety Gates
| Feature | Success Criteria |
| :--- | :--- |
| **Parsing Accuracy** | >90% detection of primary structural members. |
| **Safety Gate** | 100% of designs must be verified by the user before drafting begins. |
| **Compliance** | Outputs must match industry benchmarks (e.g., manual BS 8110 calcs). |
| **Performance** | Matrix solver must return results for typical 2D frames in < 2 seconds. |

---

## 6. Project Roadmap & Key Risks
1.  **Iterative Loop Implementation:** The PM must ensure the workflow allows the Designer to send feedback back to the Analyst if a member fails.
2.  **Scale/Unit Normalization:** Agent 1 must explicitly confirm units (mm vs. m) to prevent catastrophic calculation errors.
3.  **Scope Control:** Focus initially on Reinforced Concrete (BS 8110/EC2) before expanding to Steel or Timber.