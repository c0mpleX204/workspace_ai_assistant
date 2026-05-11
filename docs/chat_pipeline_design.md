# Chat Pipeline Compression Design

## Purpose

The chat flow should support both projectless chat and project-bound learning/tool chat without adding every possible context to every request.

## Pipeline

1. `Turn Intake`
   - Keep the raw user message unchanged for final answering.
   - Attach mode flags: projectless, project-bound, retrieval, web, attachments.
   - Load local session state from `data/conversations/{user_id}/{scope}/{session_id}.json`.

2. `Route Decision`
   - Decide whether this is plain chat, retrieval chat, lazy file parsing, or a heavier tool task.
   - Avoid retrieval when the user is plainly chatting and no project files are selected.

3. `Query Rewrite`
   - Use the fast model to rewrite only the search query from raw input plus the last few turns.
   - Use the rewritten query for RAG/web search.
   - Keep the raw input in the final prompt so the answer still follows the user's wording.

4. `Context Acquisition`
   - If selected/indexed docs exist: retrieve chunks and include path labels.
   - If the user names an unindexed file/path: parse it on demand, then retrieve.
   - If web search is requested: search with the rewritten query.
   - Do not scan or parse the whole project automatically.

5. `Context Compression`
   - Split context into fixed slots:
     - system/persona
     - route instruction
     - short conversation summary
     - relevant memory
     - retrieved file chunks
     - web results
     - recent turns
   - Each slot has its own token/char budget.
   - Drop or summarize lower-priority slots before touching raw user input.

6. `Answer Generation`
   - Generate from compressed prompt.
   - Cite retrieved chunks with title, page/slide if available, and path label.
   - If project context is insufficient, say that clearly and answer from general knowledge only when appropriate.

7. `Post Turn`
   - Persist recent messages and rolling summary to local conversation storage.
   - Store references and trace metadata for debugging.

## Local Conversation Storage

Current implementation stores ordinary/project chat sessions as JSON under `data/conversations`.

- `ordinary`: normal projectless chat sessions.
- `projects`: project/course-bound sessions such as `course_{course_id}_{session_id}`.
- Each file keeps recent `messages`, `compressed_summary`, title, and timestamps.
- The front end can reload a project chat through `GET /chat/sessions/{session_id}`.

## Compression Priority

Keep:

- System contract.
- Current raw user input.
- Most relevant retrieved chunks.
- Last 2-4 turns.

Compress:

- Older turns into a rolling summary.
- Long memory lists into top-k relevant items.
- Web snippets into short source cards.

Drop:

- Unselected project files.
- Unindexed files not mentioned by the user.
- Repeated references from the same file unless they add new content.
