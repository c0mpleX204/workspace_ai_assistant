# Document and Slide Citations

Use this skill when the user asks about uploaded materials, PDFs, Word
documents, or slide decks.

Return citations with:

- `target.kind = "pdf"` for PDFs.
- `target.kind = "slide"` for PPT/PPTX.
- `target.kind = "document"` for DOCX or generic course material.
- `target.document_id` when the file is in the material index.
- `target.page_no` for PDF pages or slide numbers.

The host application opens the material preview and jumps to the page when the
viewer supports it.

