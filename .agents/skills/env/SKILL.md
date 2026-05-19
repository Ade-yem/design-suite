---
name: environment
description: Instructions for activating the Python virtual environment before running scripts.
---

# Environment

To ensure the correct dependencies and Python interpreter are used, you must activate the virtual environment in the same shell session where you execute your commands.

## When to use this skill
- Use this whenever you need to execute, test, or investigate Python scripts in the backend of this project.

## How to use it
Always prepend your Python commands with the virtual environment activation. 

**Example:**
```bash
source venv/bin/activate && python path/to/script.py