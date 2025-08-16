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

---

**Question**: Is using a custom template tag (`dict_extras.py`) the right way to handle dynamic dictionary lookups in templates?

**Context**: Need to display form responses where question text is the dictionary key: `{{ responses_dict|lookup:question.question_text }}`. Django templates don't support `{{ dict[variable_key] }}` syntax.

**Alternative approaches**:

1. Custom template tag (current implementation)
2. Process data in view and restructure for template
3. Use template context processors
4. Custom template filter vs template tag

**Answer**:
