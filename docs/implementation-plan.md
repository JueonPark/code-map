# Project import implementation

Implements issue #1: a common source snapshot for directory paths and ZIPs, file/exclusion preview, explicit approval, existing graph and question flows using the selected project, and project switching with cache reset.

- Python standard-library loopback service with configured filesystem roots, archive/path validation and bounded in-memory snapshots.
- React importer at the home route; include source list, provider readiness and disclosure before analysis.
- Server-side Responses API adapter; existing analysis prompt formats and graph screens are retained.
- Test imports before implementation, then provider payload and HTTP guards, then browser UI with mocked responses. Build and independent review before PR.

The separate checkout excludes the installed Sym-specific snapshot and unrelated local files. No actual source was sent to a paid AI endpoint during validation.
