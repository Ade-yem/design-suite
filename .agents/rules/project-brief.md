---
trigger: always_on
---

This is information about this project for you as a project manager and lead developer

# Product Brief: AI-Driven Structural Design Copilot

## 1. Executive Summary

**Objective:** To automate the transition from architectural drawings (DXF) to finalized structural engineering details using a multi-agent AI system.
**Core Value Prop:** Reducing the "drafting-to-calculation" bottleneck by allowing an AI to interpret geometry, run verified engineering tools, and draft the results—all while keeping the human engineer in a supervisory "confirm/edit" role.

---

## 2. System Architecture & Workflows

The project is built on an **Agentic Pipeline** where three distinct AI agents handle specific stages of the project lifecycle.

### Stage 1: The Vision & Parsing Agent (The "Eyes")

- **Input:** DXF/PDF file upload.
- **Process:** The agent converts the vector data into a standardized **Structural JSON Schema**.
- **Responsibility:** Identifying geometric entities (lines, polylines, blocks) and classifying them as structural members (Columns, Beams, Slabs, Load-bearing walls).
- **PM Note:** This stage requires a "Human-in-the-Loop" gate. The system must pause and ask the user to verify the parsed geometry on the Canvas before proceeding to math.

### Stage 2: The Designer Agent (The "Brain")

- **Input:** Verified Structural JSON + User-defined Design Codes (e.g., ACI, Eurocode).
- **Process:** This agent does **not** "guess" math. It acts as an orchestrator that formats data for **Hard-Coded Design Tools** (Python scripts).
- **Responsibility:** Calculating required member sizes, reinforcement areas, and checking code compliance (Shear, Moment, Deflection).
- **Output:** A "Designed Member JSON" containing physical properties and reinforcement schedules.

### Stage 3: The Drafting Agent (The "Hands")

- **Input:** Designed Member JSON.
- **Process:** Translates numerical design data into visual coordinates for drawing.
- **Responsibility:** Generating 2D structural details (Sections and Elevations) via the **HTML5 Canvas API**.
- **Output:** An interactive visual drawing and an exportable DXF file.

---

## 3. Product Features & User Interface

The UI is a **Side-by-Side Integrated Development Environment (IDE)**.

- **Left Panel (Conversational AI):** \* Threaded chat history.
  - Status logs for each agent (e.g., _"Designer Agent is running deflection checks..."_).
  - Actionable "Confirm" buttons for each phase.
- **Right Panel (Interactive Canvas):** \* **Layer Management:** Toggle between Architectural (Original) and Structural (AI-Generated) views.
  - **Direct Manipulation:** User can click, drag, or edit labels on the drawing.
  - **Zoom/Pan:** Standard CAD-style navigation.
- **Central Data Sync:** Any change made in the **Chat** (e.g., "Change beam B1 to 300x600") must instantly update the **Canvas**, and vice versa.

---

## 4. Technical Stack Requirements

- **Frontend:** React.js (State management) + Konva.js or Fabric.js (Canvas rendering).
- **Backend:** Python (FastAPI) – Ideal for handling DXF parsing libraries (ezdxf) and engineering math.
- **AI Models:** GPT-4o or Claude 3.5 Sonnet (for reasoning and JSON orchestration).
- **Data Format:** GeoJSON-inspired custom schema for structural members.

---

## 5. Success Metrics & Quality Control

| Feature              | Success Criteria                                                                           |
| :------------------- | :----------------------------------------------------------------------------------------- |
| **Parsing Accuracy** | >90% detection of primary structural members from a clean DXF.                             |
| **Safety Gate**      | 100% of designs must be verified by the user before the "Drafting Agent" begins.           |
| **Performance**      | Canvas rendering must handle up to 5,000 entities without lag.                             |
| **Compliance**       | Calculation outputs must match industry-standard benchmarks (e.g., Excel/SAP2000 results). |

---

## 6. Key Project Risks (For PM Oversight)

1.  **Hallucination Risk:** AI might invent beams that don't exist. **Mitigation:** The "Verification Gate" UI is mandatory.
2.  **Scale/Unit Issues:** DXF files often have inconsistent units (mm vs. meters). **Mitigation:** Agent 1 must explicitly ask the user to "Confirm Scale" upon upload.
3.  **Code Compliance:** Engineering codes are complex. **Mitigation:** Initially limit the scope to one specific material (e.g., Reinforced Concrete).
