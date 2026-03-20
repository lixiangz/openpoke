# Take-Home Assignment

## Task 1: Fix Agent Overload

When conversation history or the agent roster grows large, the system hits context-window limits and degrades. I addressed this across several areas:

- **Context windowing** in the interaction agent loop — drops the oldest messages when estimated tokens exceed a threshold
- **Semantic agent selection** — embeds agent descriptions and selects the most relevant subset to include in the prompt instead of dumping all of them
- **Smarter summarization** — added a character-based trigger so large email payloads get summarized before they bloat the context

## Task 2: Natural-Language Email Rules

Users can now create email rules through chat (e.g. "star anything from alice@example.com"). The system:

- Parses natural language into structured conditions and actions via the execution agent
- Evaluates rules against incoming emails in the background watcher
- Executes matched actions (star, archive, label, notify) through the existing Gmail integration
- Persists rules in SQLite with full CRUD exposed as agent tools

Business impact: changing openpoke from "tool used daily" to "infrastructure that's depended on"

Potential next steps:

- Context-free grammar validation
- Auto-reply / auto-forward actions
- Rule suggestions based on user behavior
- Rule conflict detection

Other ideas considered:

- Attachment reader
- Follow up tracker
- Daily briefing
- Contact relationship context
- Cross thread queries

## Small Changes

- Add unit tests to ensure expected behavior
- Add configurable .env variables to reduce costs when testing in dev
