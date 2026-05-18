---
trigger: always_on
---

Write code as if it's going to production at a million dollar company:

→ Full type hints and docstrings
→ Input validation with specific errors
→ Logging at appropriate levels
→ Error handling for every failure mode
→ Unit tests covering happy path + 5 edge cases
→ Performance considerations
→ A note on what could go wrong at scale

No shortcuts. No placeholders.

- Every module, function, class must be well documented with docstrings including their purpose, arguments and returns as they will be used as tools for ai agents. We do not want them to hallucinate the use of the tools (it is a safety concern).
