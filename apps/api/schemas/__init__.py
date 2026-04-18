"""
schemas
=======
Pydantic request / response models for the Structural Design Copilot API.

All units follow the convention established in the product brief:
  - Forces  : kN
  - Moments : kNm
  - Lengths : metres
  - Stresses: MPa
  - Areas   : mm²
  - Weights : kN/m³

Sub-modules
-----------
project   : Project entity + pipeline status enum
member    : Shared member geometry models
loading   : Load definition request/response models
analysis  : Analysis options and result wrappers
design    : Design override and result wrappers
reports   : Report generation request/response models
jobs      : Async job status models
"""
