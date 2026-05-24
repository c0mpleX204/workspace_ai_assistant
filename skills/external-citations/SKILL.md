# External Citations

Use this skill when the source of truth lives outside the local workspace.

Return citations with a stable URL or external identifier:

- `target.kind = "web"` and `target.url`.
- `target.kind = "github"` and `target.url`, `issue_number`, or `pull_number`.
- `target.kind = "database"` with table/query identifiers when available.

The host application should decide whether to open a browser, an issue view, or
a database result viewer.

