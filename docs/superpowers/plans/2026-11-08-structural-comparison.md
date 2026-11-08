# Git structural comparison implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement and verify each task in this isolated feature checkout.

**Goal:** Resolve issue #3 with a local, evidence-backed comparison of committed Git snapshots.

**Architecture:** A bounded read-only Git adapter supplies immutable snapshots to a Python AST import extractor. A comparison model matches paths/renames and retains source evidence; a new React route shows one stable union graph, change focus, and revision-specific source/diffs. No LLM is required.

**Tech stack:** Existing Python 3.10+ standard-library service, installed Git, React/TypeScript/Vite; no new dependencies.

**Spec:** https://github.com/JueonPark/code-map/issues/3

## Global constraints

- Compare merge-base(base, head) to head; record requested refs and all resolved commit SHAs.
- Never checkout, alter the index/worktree, execute source, fetch, or call an AI provider.
- Inherit configured roots, source exclusions, 2,000 entries, 256 KiB/file, and 2 MiB/snapshot bounds. Explicit optional source subdirectory supports larger repositories.
- Python static imports only in the first extractor; other included text files remain visible as nodes with unsupported-analysis notices. Show unresolved/external imports and parse failures.
- Preserve deleted evidence, content-only modifications, directory grouping, and Git-detected rename identity. Never claim runtime effects.
- Existing path/ZIP analysis must keep working.

## Review focus

- Moved refs and dirty working trees: comparisons stay pinned; no source mutation (Task 1).
- Relative imports, src layouts, duplicate module names, from-import ambiguity: report gaps, never fabricate resolved targets (Task 1).
- Untrusted Git refs/config, binary objects, symlinks, excluded files, oversized snapshots: controlled errors with no execution or hidden source exposure (Task 1).
- Late async responses after a comparison switch: old evidence never appears under new metadata (Task 2).
- Deleted/renamed nodes, content-only changes, zero-change results: stable identity and navigable evidence (Tasks 1 and 2).

## Task 1: Snapshot, extractor, comparison API

**Files:** server/git_compare.py, server/python_imports.py, server/test_compare.py, server/app.py.

**Interfaces:** compare_repository(path, base, head, roots, source_root='') -> comparison including private snapshots; public_comparison removes private data; comparison_detail(comparison, node_id) -> before/after source and unified diff. POST /api/compare accepts path/base/head/sourceRoot; POST /api/compare/detail accepts id/nodeId. Store at most eight comparisons.

- [x] Write and run failing tests using real temporary Git histories for merge-base semantics, renames, added/removed edges, content-only changes, deletions, dirty-tree preservation, unsupported/unresolved content, and validation/limits.
- [x] Implement bounded Git object reads, Python AST imports with evidence, matching and diff detail; add protected HTTP routes and tests.
- [x] Verify: python -m unittest discover -s server -p 'test_*.py' -v. Expected: all tests pass (platform-specific symlink tests may skip on Windows).
- [x] Commit the backend and record results.

## Task 2: Review UI

**Files:** frontend/src/features/structural-compare/{index.tsx,model.ts,style.css}, routes/index.tsx, features/project-import/index.tsx, tests/compare-browser.cjs.

**Interfaces:** Consume public comparison metadata/nodes/edges/notices and detail responses from Task 1. Source ranges are 1-based inclusive, node IDs span both revisions, edge direction is importer -> imported.

- [x] Write and run a failing browser scenario for entry link, comparison form, graph/evidence navigation, view toggles, modified-only files, filters, errors, and comparison switching with an in-flight detail response.
- [x] Implement the accessible form and stable SVG union graph with file/directory navigation, change legend, changed-neighborhood focus, direct importers, and source/diff detail. Reuse the local request helper and app routing.
- [x] Verify browser scenario, production build, and targeted ESLint. Expected: pass; document existing unrelated typecheck failures.
- [x] Commit the UI and record results.

## Task 3: Real comparison, documentation, independent review, PR

**Files:** docs/structural-comparison.md, README.md, supporting regression tests if review requires them.

- [x] Run a real local repository commit comparison and record SHAs, observed structural changes, limitations, and reproduction commands.
- [x] Document setup, supported import resolution, limits, source-directory selection, and acceptance walkthrough.
- [x] Run the required suites/build; dispatch a fresh reviewer with this spec, plan, and complete diff. Reproduce and fix important findings with regression tests.
- [ ] Push a feature branch and create a PR with Closes #3 and truthful validation/limitations. Do not merge automatically.
