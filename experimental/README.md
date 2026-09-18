# Experimental Modules — Quarantine Directory

This directory contains unmaintained, scraping-dependent, or prototype modules from the v1 architecture that are deliberately excluded from the supported orchestrator_core v2 runtime.

## Quarantine Policy & Architectural Boundaries

1. **Zero Core Ingestion**: Modules under experimental/ must **never** be imported or referenced by any file in orchestrator_core/. This boundary is verified by static CI checks on every commit.
2. **Untested**: Code in this directory is not covered by the automated pytest suite or CI matrix.
3. **Container Exclusion**: All files in experimental/ are omitted from production Docker images via .dockerignore.
4. **Reference Implementation Only**: These modules are kept strictly for developer reference, historical context, and potential future standalone services.

## Quarantined Components

- linkedin_agent/: Web scraping-dependent LinkedIn automation.
- job_search_agent/: RemoteOK, Remotive, and RSS job aggregator.
- github_agent/: Legacy GitHub repository and issue management agent.
- project_manager_agent/: Legacy task tracking and deadline agent.
- info_agent/: Static documentation helper agent.
- oice_io/: System-dependent audio I/O (pyttsx3, SpeechRecognition) helpers.
