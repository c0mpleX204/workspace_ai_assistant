# Project Workspace Chat Plan

## Goal

Merge the old free chat and course chat into one mental model:

- Projectless chat: normal conversation without local files.
- Project chat: a local workspace folder for each course/project, with indexed files available for retrieval.
- Companion chat stays separate for now.

## Current MVP

- Creating a course/project creates a local folder under `data/projects`.
- The backend returns `project_path` with each course/project.
- Uploaded files are saved into the project folder instead of the global upload folder.
- Searchable uploads include PDF, TXT/Markdown, common code/text files, DOCX, and PPTX.
- PPT files can be stored as project assets, but only PPTX is parsed for retrieval.
- Indexed references show their local file path as a path label.
- Unindexed files should stay as files until a future turn explicitly needs them.

## Next Steps

- Add lazy file parsing: when a user asks about an unindexed file/path, parse that file on demand.
- Add a project file browser that displays indexed and unindexed files without forcing parse.
- Add code-aware tools for reading file trees, opening files, and summarizing code modules.
- Unify the chat surface so the same composer can switch between projectless and project-bound context.
