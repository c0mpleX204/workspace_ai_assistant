# Agent Skills

This directory contains optional agent skills. A skill teaches the agent how to
find, read, or cite a specific kind of external context, but it must not decide
how the UI opens that context. The host application owns navigation.

## Contract

Every skill should return citations using the shared platform shape:

```json
{
  "citation_id": "ref-1",
  "type": "code",
  "summary": "What this source supports",
  "target": {
    "kind": "code",
    "path": "client/src/App.jsx",
    "line_start": 120,
    "line_end": 145,
    "page_no": null,
    "document_id": null,
    "url": null
  }
}
```

The current built-in platform handlers support:

- `code` / `text`: open the project editor and jump to `line_start`.
- `pdf` / `slide` / `document`: open the material preview and use `page_no`.
- `web`: open a URL when a future web citation viewer is added.

