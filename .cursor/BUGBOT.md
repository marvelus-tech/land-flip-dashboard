# land-flip-dashboard — Bugbot rules

## Secrets (blocking)

- No API keys, tokens, or private URLs in committed HTML/JS/JSON.
- Builder/contact data in the repo is business data — do not add unrelated PII or credentials.

## Dashboard

- Avoid `innerHTML` with scraped or user-supplied strings; prefer `textContent` or sanitize.
- CSV export and table render paths should handle empty/malformed rows without throwing.
- Keep mobile layout usable (no horizontal overflow on small viewports for main tables).

## Deploy

- `gh-pages` branch is the published site — flag changes that break relative asset paths or `docs/` vs root deploy layout.
