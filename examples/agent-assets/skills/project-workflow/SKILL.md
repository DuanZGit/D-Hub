---
name: project-workflow
description: Follow the project's implementation and verification workflow.
---

At the start of work, use `dhub_wiki_search` and `dhub_memory_search` for relevant
project context. Before changing code, inspect the relevant module and its tests.
Keep changes scoped, run narrow checks during implementation, and run the full
available verification before handing work off.

Use `dhub_wiki_put` for stable project decisions and maintained documentation. Use
`dhub_memory_add` for facts, observations, and outcomes worth retrieving later. Do
not store credentials, tokens, personal data, or transient command output.
