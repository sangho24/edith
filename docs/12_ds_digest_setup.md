# ds-digest setup

ds-digest publishes a GitHub Pages HTML archive, not `latest.json`.

Set this in `.env`:

```bash
EDITH_DS_DIGEST_URL=https://sangho24.github.io/ds-digest/
```

Use the archive root URL with the trailing slash. Edith reads `index.html`, picks the newest
`YYYY-MM-DD.html` link, and parses that page automatically. A direct date URL such as
`https://sangho24.github.io/ds-digest/2026-06-07.html` also works.

The older JSON path remains supported for compatibility when `EDITH_DS_DIGEST_URL` ends in `.json`.
