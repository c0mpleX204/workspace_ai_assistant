# Code Citations

Use this skill when the user asks about implementation details, bugs, source
files, functions, or code behavior.

Return citations with `target.kind = "code"`. Prefer exact line ranges over
whole files. The host application will open the file and jump to the referenced
line.

Citation requirements:

- `target.path`: project-relative or absolute file path.
- `target.line_start`: first relevant line.
- `target.line_end`: last relevant line when known.
- `summary`: short explanation of why this code is relevant.

