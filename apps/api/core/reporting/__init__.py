"""
Output & Reporting Layer
========================
Transforms Design Suite JSON outputs into professional engineering documents.

This package is a **rendering engine, not a calculation engine**.
It never performs or modifies calculations — it only formats and presents
data produced by the upstream Design Suite core.

Public API
----------
- ``normalizer``   : Validates and assembles the Report Data Model
- ``calc_sheet``   : Module 1 — Calculation Sheet Engine
- ``rebar_schedule``: Module 2 — Reinforcement Schedule Engine
- ``quantities``   : Module 3 — Material Quantity Engine
- ``compliance``   : Module 4 — Compliance Report Engine
- ``summary``      : Module 5 — Project Summary Engine
- ``pdf_export``   : PDF export via WeasyPrint
- ``renderer``     : Jinja2 HTML template renderer
"""
