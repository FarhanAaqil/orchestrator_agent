# NOT SUPPORTED: Job Search Agent

## Status
- **Status**: Quarantined / Experimental
- **Supported in v2**: No
- **Covered by tests**: No
- **Included in Docker**: No

## Reason
Job searching via RemoteOK, Remotive, and RSS feeds relies on external public feeds without formal SLA or authentication guarantees. In v2, career workflows focus on structured cover-letter generation and ATS analysis handled natively in orchestrator_core/agents/career_agent.py.

## Usage
Kept strictly as a reference implementation. Do not import in orchestrator_core/.
