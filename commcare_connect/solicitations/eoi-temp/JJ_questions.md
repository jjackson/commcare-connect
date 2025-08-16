# Dev Team Questions

**Quick Question**: What's the preferred way to load real/specific data (not fake generated data) in this codebase?

**Context**: Need to load actual EOI data from past campaigns (CCC-CHC, KMC) for testing/demos.

**Options**:
1. YAML + management command (Cursor's recommendation)
2. JSON fixtures 
3. Python data files
4. CSV import

**Answer**:

---

**Question**: How to show timestamps in user's local timezone?

**Context**: Currently shows UTC time (5:10 PM when local time is 11:00 AM).

**Answer**: