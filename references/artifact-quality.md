# Artifact quality contract

The generated page must be:

- one self-contained UTF-8 HTML file with embedded CSS and JavaScript;
- usable offline with no CDN, web font, iframe, remote script, or stylesheet dependency;
- responsive from narrow mobile layouts through desktop;
- keyboard navigable with visible focus, semantic landmarks, and accessible labels;
- printable and readable with reduced motion;
- titled and headed with the query-specific walkthrough title;
- visibly labeled `EVIDENCE` or `ESTIMATED` near the top and in metadata;
- organized as a ten-phase stage rail plus a substep/action rail;
- complete against the semantic feature IDs and interaction invariants in
  `feature-parity-inventory.json`;
- stateful rather than decorative: navigation, traversal, runner, experiment, context,
  failure-injection, and scenario controls must change visible output;
- explicit about query-specific no-op phases;
- complete for the evidenced physical plan;
- ordered so execution stack and heap zones appear before runtime components;
- safe against model-provided HTML/script injection.

Every claim/action/operator must link to exact Azure DevOps lines pinned to the current source
workspace HEAD. The query must never appear in repository fixtures except as synthetic data.

The output path is:

```text
<Documents>\Bookmarks\<stable-query-derived-slug>\<slug>.html
```

Use the OneDrive Documents folder when present, otherwise the local Documents folder. After the
page exists, publication may be attempted best-effort to `Favorites bar → Imported`. The page is
a successful artifact even when the companion is absent, unsupported, unhealthy, or fails.
Report `published` only when `CompanionResult.ok` is exactly boolean `true`; otherwise report
`skipped` or `failed` with the warning. Never preflight, block, ask, or prompt for publication.
