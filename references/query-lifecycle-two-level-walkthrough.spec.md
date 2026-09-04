# Kusto Query Lifecycle — Two-Level Interactive Walkthrough
## Implementation-Grade As-Built Specification

---

## 1. Scope and status

This document is a **descriptive as-built specification** of the single-file HTML application
`query-lifecycle-two-level-walkthrough.html`. It is **not** an aspirational redesign, a proposal,
or a set of requirements for a future version.

Rules of interpretation:

- **Everything described here is current, observed behaviour.** It was derived by exhaustive reading
  of the source (HTML, CSS, JavaScript, and the embedded data payload) and by direct measurement of
  the rendered page in a Chromium engine.
- **Observed defects are normative.** Where the implementation contains a bug, a contradiction, a
  dead code path, an unused CSS rule, or a layout overflow, that behaviour is documented as the
  current contract. A reimplementation that "fixes" it silently would diverge from the canonical
  artifact.
- **Only items explicitly labelled `CAVEAT` are flagged as candidates for change.** Those carry a
  suggested remediation, but the remediation is advisory and is *not* part of the specification.
- **Source is authoritative over screenshots.** Where a screenshot and the source disagree, the
  source governs; the reconciliation is recorded in §19.
- Line citations use 1-based line numbers matching `Get-Content` indexing of the canonical file.

---

## 2. File identity and macro layout

| Property | Value |
|---|---|
| Canonical path | `C:\Users\Raz Ronen\OneDrive - Microsoft\Documents\Bookmarks\query-lifecycle-two-level-walkthrough\query-lifecycle-two-level-walkthrough.html` |
| Size | **427,809 bytes** |
| Line count | **6,741** lines (`Get-Content`) |
| SHA-256 | `E92B4E92EC7D6A002515901A6E47E43651927860D7EA4A6EADF9017C83993740` |
| Last modified | 2026-09-03 20:54:05 |
| Document type | `<!doctype html>`, `<html lang="en">` |
| Title | `Kusto Query Lifecycle: Two-Level Interactive Walkthrough` |
| Viewport meta | `width=device-width, initial-scale=1` |
| Charset | `utf-8` |

### 2.1 Macro regions

| Region | Lines |
|---|---|
| `<!doctype>` + `<head>` preamble | 1–6 |
| `<style>` — the entire stylesheet, one inline block | 7–2124 |
| `</head>`, `<body>` open | 2125–2126 |
| Static body DOM | 2126–2904 |
| `<script>` — the entire application, one inline block, `"use strict"` | 2905–6739 |
| `</body></html>` | 6740–6741 |

### 2.2 Zero external dependencies

The file is fully self-contained and offline-capable. Verified absent: `<img>`, `<svg>`, `<canvas>`,
`<iframe>`, `<video>`, `<audio>`, `<form>`, `<select>`, `<textarea>`, `<link rel>`, `<script src>`,
`@import`, any `url()` in CSS, `fetch`, `XMLHttpRequest`, `WebSocket`, `import()`, `eval`,
`navigator.*`, `document.cookie`.

Typography uses only system stacks:
- UI: `"Segoe UI", system-ui, sans-serif` at `15px/1.52`
- Code: `ui-monospace, SFMono-Regular, Consolas, monospace`

The only network traffic the page can ever generate is a user-initiated navigation from one of its
outbound `target="_blank"` source links (§8).

### 2.3 Sibling files (not referenced by the page)

Two Microsoft Edge bookmark descriptors sit beside the HTML. Neither is loaded or read by the page.

| File | Bytes | Purpose |
|---|---|---|
| `kusto-query-lifecycle-two-level-interactive-walkthrough-edge-command.json` | 408 | `upsertBookmark` v1 → `Favorites bar / Imported`, name `Kusto Query Lifecycle - Two-Level Interactive Walkthrough` |
| `kusto-query-lifecycle-two-level-interactive-walkthrough-html-edge-command.json` | 413 | identical, name suffixed `.html` |

Both point at the canonical HTML via a `file:///` URL.

---

## 3. Information architecture

### 3.1 The two-level model

- **Level 1** — 10 lifecycle *stages*, held in the `stages` array (L4585–4731). Displayed 1-based
  (`Stage N`), stored 0-based in `stageIndex`.
- **Level 2** — the *substeps* inside the selected stage, held in `stages[i].steps`. **45 substeps
  total** across the 10 stages.

Throughout this document, `S<stage>.<substep>` denotes the **display** (1-based) coordinate, and
`"<i>-<j>"` denotes the **internal key** (0-based) used by every lab lookup map.

### 3.2 Stage matrix

| # | idx | `short` | `kind` | `title` | steps | traversal `mode` | `order` length |
|---|---|---|---|---|---|---|---|
| 1 | 0 | Syntax | text → syntax tree | Syntax parsing | 4 | construction order | 11 |
| 2 | 1 | Semantic | syntax → bound tree | Semantic analysis and binding | 5 | depth-first visitor | 18 |
| 3 | 2 | Relop | bound tree → logical plan | CSL-to-Relop translation | 4 | depth-first translation | 20 |
| 4 | 3 | Preparation | normalize execution metadata | Relop preparation | 4 | pass-specific walks | 20 |
| 5 | 4 | Initial optimize | logical rewrite | Initial Relop optimization | 5 | repeated Relop walks | 21 |
| 6 | 5 | Partial queries | execute planning-time subqueries | Partial-query evaluation | 4 | collector traversal | 14 |
| 7 | 6 | Final optimize | placement + distribution | Final Relop optimization and distribution | 5 | multi-pass traversal | 18 |
| 8 | 7 | Physical plan | logical → executable nodes | Physical-plan construction | 5 | builder visitor | 17 |
| 9 | 8 | Serialize | managed → native boundary | Serialization and C++ handoff | 3 | object-graph serialization | 10 |
| 10 | 9 | Execute | C++ host + Rust kernel | C++ and Rust execution | 6 | pull-based iterator traversal | 15 |

**Verified dimensional invariant** — for every stage `i`:

```
stages[i].steps.length
  === preciseLinks[i].length
  === treeBehaviors[i].length
  === traversalCatalog[i].focuses.length
```

All 10 stages satisfy this. Total 45 in each of the four parallel arrays.

### 3.3 Complete substep matrix

Columns: display coordinate · internal key · title · runner · traversal focus index · walk badge ·
change badge · network beacon resolution.

#### Stage 1 — Syntax (`construction order`, default beacon `none` / "No HTTP")

| Coord | Key | Title | Runner | Focus | Walk badge | Change badge | Beacon |
|---|---|---|---|---|---|---|---|
| S1.1 | `0-0` | Accept and validate text | compiler `syntax`, 3 actions | 0 | No tree walk | No tree change | inherit |
| S1.2 | `0-1` | Apply syntax-affecting flags | compiler `syntax`, 3 actions | 0 | No tree walk | No tree change | inherit |
| S1.3 | `0-2` | Build the syntax tree | compiler `syntax`, 4 actions | 5 | Builds tree | Creates syntax tree | inherit |
| S1.4 | `0-3` | Gate on diagnostics | compiler `syntax`, 4 actions | 10 | Root/result check | No structural change | inherit |

Call paths: `DatabaseQueryService.CreateLanguageProvider → CslQueryLanguageProvider.Translate` ·
`Translate → ApplyFeatureFlagsToClientRequestProperties` · `Translate → SyntaxPass` ·
`SyntaxPass → syntaxResult.HasErrors → Translate(statementList, ...)`

#### Stage 2 — Semantic (`depth-first visitor`, default beacon `none` / "No HTTP yet")

| Coord | Key | Title | Runner | Focus | Walk badge | Change badge | Beacon |
|---|---|---|---|---|---|---|---|
| S2.1 | `1-0` | Create semantic context | compiler `semantic`, 4 | 0 | Full visitor walk | Annotates tree | **override** `possible` / "May fetch" |
| S2.2 | `1-1` | Resolve local entities | compiler `semantic`, 4 | 6 | Branch visitor walk | Annotates local nodes | inherit |
| S2.3 | `1-2` | Resolve remote scope and schema | compiler `semantic`, 4 | 10 | Branch visitor walk | Annotates remote nodes | **override** `possible` / "May fetch" |
| S2.4 | `1-3` | Bind operators and join | compiler `semantic`, **5** | 15 | Post-order binding | Annotates operators | inherit |
| S2.5 | `1-4` | Gate semantic errors | compiler `semantic`, 4 | **18** *(out of range — see §18.3)* | No full walk | No structural change | inherit |

#### Stage 3 — Relop (`depth-first translation`, default beacon `none` / "No HTTP")

| Coord | Key | Title | Runner | Focus | Walk badge | Change badge |
|---|---|---|---|---|---|---|
| S3.1 | `2-0` | Validate result shape | compiler `relop`, 4 | 0 | Statement iteration | No tree change |
| S3.2 | `2-1` | Translate pipe operators | compiler `relop`, **5** (+4 mappings) | 3 | Full translation walk | Builds new Relop tree |
| S3.3 | `2-2` | Create remote leaf | compiler `relop`, 4 | 12 | Targeted translation | Creates remote boundary |
| S3.4 | `2-3` | Return RelopQuery | compiler `relop`, 4 | 19 | No tree walk | Packages existing root |

#### Stage 4 — Preparation (`pass-specific walks`, default beacon `none` / "No HTTP")

| Coord | Key | Title | Runner | Focus | Walk badge | Change badge |
|---|---|---|---|---|---|---|
| S4.1 | `3-0` | Create preparation PassManager | **— none —** | 0 | No tree walk | No tree change |
| S4.2 | `3-1` | Assign execution semantics | pass-lab, 4 passes | 5 | Several pass walks | Metadata and structural rewrites |
| S4.3 | `3-2` | Prepare catalog work | pass-lab, 3 passes | 12 | Conditional pass walks | No change for example |
| S4.4 | `3-3` | Return prepared Relop | **— none —** | 19 | No tree walk | Repackages root |

#### Stage 5 — Initial optimize (`repeated Relop walks`, default beacon `none` / "No HTTP")

| Coord | Key | Title | Runner | Focus | Walk badge | Change badge |
|---|---|---|---|---|---|---|
| S5.1 | `4-0` | Run GenericOptimizationPhase | pass-lab, **22 passes** | 0 | Many full walks | Simplifies structure |
| S5.2 | `4-1` | Establish initial remote placement | pass-lab, 1 pass | 9 | Depth-first custom walk | Moves remote boundary |
| S5.3 | `4-2` | Run pre-distribution remoting #2 | pass-lab, 1 pass | 9 | Depth-first custom walk | Usually confirms structure |
| S5.4 | `4-3` | Expose work, then remoting #3 | pass-lab, 3 passes | 16 | Several full walks | May replace subtrees |
| S5.5 | `4-4` | Finalize initial optimization | pass-lab, 3 passes | 20 | Cleanup walks | Removes/replaces nodes |

#### Stage 6 — Partial queries (`collector traversal`, default beacon `none` / "No HTTP for this query")

| Coord | Key | Title | Runner | Focus | Walk badge | Change badge | Beacon |
|---|---|---|---|---|---|---|---|
| S6.1 | `5-0` | Collect partial-query operators | **— none —** | 0 | Collector walk | No tree change | inherit |
| S6.2 | `5-1` | Take the no-op path for this query | **— none —** | 13 | No second walk | No change for example | inherit |
| S6.3 | `5-2` | Understand the optional evaluation path | pass-lab, **29 passes** | 5 | Separate subtree execution | Main tree unchanged initially | **override** `possible` / "Conditional" |
| S6.4 | `5-3` | Substitute and re-optimize | pass-lab, 6 passes | 10 | Targeted replacement + walks | Replaces partial node/data | inherit |

#### Stage 7 — Final optimize (`multi-pass traversal`, default beacon `none` / "No HTTP")

| Coord | Key | Title | Runner | Focus | Walk badge | Change badge |
|---|---|---|---|---|---|---|
| S7.1 | `6-0` | Run post-substitution rewrites | pass-lab, **23 passes** | 0 | Many pass walks | Folds/replaces subtrees |
| S7.2 | `6-1` | Retry remoting after substitution | pass-lab, 3 passes | 10 | Depth-first custom walk | May expand remote island |
| S7.3 | `6-2` | Prepare graph operators | pass-lab, 1 pass | 0 | Conditional graph walk | No change for example |
| S7.4 | `6-3` | Freeze placement and distribute | pass-lab, 11 passes | 14 | Multiple distribution walks | Creates distributed structure |
| S7.5 | `6-4` | Finish final phases | pass-lab, 15 passes | 17 | Cleanup/analysis walks | Final logical cleanup |

#### Stage 8 — Physical plan (`builder visitor`, default beacon `none` / "No HTTP")

| Coord | Key | Title | Runner | Focus | Walk badge | Change badge | Beacon |
|---|---|---|---|---|---|---|---|
| S8.1 | `7-0` | Create builder context | **physical-lab**, 5 actions | 0 | No tree walk | No tree change | inherit |
| S8.2 | `7-1` | Walk and lower the tree | **physical-lab**, 8 actions | 2 | Full builder walk | Builds separate physical tree | inherit |
| S8.3 | `7-2` | Create the physical hash join | **physical-lab**, 7 actions | 8 | Custom two-child walk | Creates HashJoin | inherit |
| S8.4 | `7-3` | Generate the remote query node | **physical-lab**, 7 actions | 12 | Remote-subtree walk | Creates RemoteQueryNode | **override** `none` / "No HTTP" |
| S8.5 | `7-4` | Finalize and package QueryPlan | **pass-lab**, 17 passes | 16 | Many physical pass walks | Finalizes physical tree | inherit |

#### Stage 9 — Serialize (`object-graph serialization`, default beacon `none` / "No external HTTP")

| Coord | Key | Title | Runner | Focus | Walk badge | Change badge | Beacon |
|---|---|---|---|---|---|---|---|
| S9.1 | `8-0` | Serialize the physical tree | boundary-lab, 6 actions | 0 | Physical graph walk | No mutation | inherit |
| S9.2 | `8-1` | Serialize query context | boundary-lab, 5 actions | 5 | Context serialization | No operator-tree change | inherit |
| S9.3 | `8-2` | Submit through managed processor | boundary-lab, 7 actions | 9 | No tree walk | No tree change | **override** `none` / "No external HTTP" |

#### Stage 10 — Execute (`pull-based iterator traversal`, default beacon `none` / "No HTTP at this substep")

| Coord | Key | Title | Runner | Focus | Walk badge | Change badge | Beacon |
|---|---|---|---|---|---|---|---|
| S10.1 | `9-0` | Deserialize native operators | execution-lab, 7 events / 3 scenarios | 0 | Recursive parse/build | Builds C++ operator tree | inherit |
| S10.2 | `9-1` | Construct the Rust-backed join | execution-lab, 7 / 3 | 2 | Iterator construction walk | Builds runtime iterators | inherit |
| S10.3 | `9-2` | Enter Rust | execution-lab, 7 / 3 | 3 | Pull traversal | Changes runtime state | inherit |
| S10.4 | `9-3` | Pull C++ children through callbacks | execution-lab, 8 / 4 | 6 | Pull traversal | No structural change | **override** `imminent` / "HTTP imminent" |
| S10.5 | `9-4` | Execute the remote right child | execution-lab, 8 / 4 | 8 | No operator-tree walk | Transfers remote data | **override** `active` / "HTTP active" |
| S10.6 | `9-5` | Stream results and complete | execution-lab, 7 / 4 | 14 | Return/unwind path | Changes iterator state | **override** `none` / "HTTP response consumed" |

### 3.4 Running example

A single KQL query threads the entire walkthrough. It is displayed verbatim in the artifact card's
`<details class="example">` (L2883–2898):

```kusto
set query_join_in_shard_engine=true;

TelemetryEvents
| take 2
| project LocalEventId=EventId,
          payment_type="CSH"
| join kind=inner hint.remote=left (
    cluster('help.kusto.windows.net')
      .database('Samples').Trips
    | where payment_type == "CSH"
    | take 2
    | project payment_type, trip_id
) on payment_type
| project LocalEventId, trip_id,
          payment_type
| take 10
```

The stage-overview card carries a permanent static note (L2176): *"The bounded local/remote join is
used throughout. Stage 6 explicitly shows why it is a no-op for this query and what would happen if a
`toscalar()` were present."*

---

## 4. Static DOM inventory

### 4.1 Authored tree

```
aside#network-beacon.network-beacon.none      [aria-live=polite, aria-label]   2127–2134
│  ├─ div.network-top > span.network-label + span#network-state
│  ├─ p.network-route#network-route
│  └─ p.network-purpose#network-purpose
div.shell                                                                      2135–2903
├─ header                                                                      2136–2145
│  ├─ div > h1 + p.subtitle
│  └─ div.level-key  (Level 1 / Level 2 legend, 2×2 grid)
├─ section.level-one                       [aria-labelledby=level-one-heading] 2147–2153
│  ├─ div.section-label > h2#level-one-heading + span#journey-progress
│  └─ nav#stage-strip.stage-strip          [aria-label="Query lifecycle stages"]
└─ main#workspace.workspace                                                    2155–2902
   ├─ aside.card.stage-overview                                                2156–2178
   │  ├─ div.stage-overview-header
   │  │  ├─ div.stage-badge#stage-badge
   │  │  ├─ span.stage-compact#stage-compact
   │  │  └─ button.stage-toggle#stage-toggle [aria-expanded, aria-controls]
   │  └─ div.stage-overview-body#stage-overview-body
   │     ├─ h2#stage-title
   │     ├─ p.subtitle#stage-purpose
   │     ├─ div.ownership  (4 cells: #stage-input #stage-output #stage-owner #stage-not)
   │     ├─ div.handoff > b + span#stage-handoff
   │     ├─ div.stage-nav > button#previous-stage + button#next-stage
   │     └─ div.note  (static running-example note)
   ├─ section.center                                                           2180–2867
   │  ├─ section.card.level-two            [aria-labelledby=level-two-heading] 2181–2192
   │  │  ├─ div.section-label > h2#level-two-heading + span
   │  │  ├─ nav#substep-strip.substep-strip [aria-label="Steps inside selected stage"]
   │  │  └─ div.walk-controls > button#previous-step + input#step-slider + button#next-step
   │  ├─ section#compiler-lab.compiler-lab                                     2194–2236
   │  ├─ section#physical-lab.physical-lab                                     2238–2277
   │  ├─ section#boundary-lab.boundary-lab                                     2279–2308
   │  ├─ section#execution-lab.execution-lab                                   2310–2368
   │  ├─ article.card.step-detail                                              2370–2826
   │  │  ├─ div.step-heading > div(#step-badge,#step-title,#step-summary) + span.count#step-count
   │  │  ├─ div.detail-grid > 4 × section.detail-box (.action .why .observe .next)
   │  │  ├─ a.source-link#source-link
   │  │  ├─ section#additional-context.additional-context                      2386–2418
   │  │  │  └─ table.context-table  (3 cols × 4 rows, preparation passes)
   │  │  └─ section#optimization-additional-context.additional-context         2419–2825
   │  │     ├─ table.context-table  (4 cols × 22 rows, GenericOptimizationPhase)
   │  │     └─ section.pass-lab   ◄── RELOCATED AT RUNTIME (§7.2)              2453–2824
   │  │        └─ details#physical-plan-deep-dive [hidden]                     2503–2823
   │  │           ├─ div.physical-fidelity-grid (metrics + expanded hierarchy)
   │  │           ├─ table.physical-map  (5 correspondence rows)
   │  │           └─ details.physical-raw > pre  (full .show queryplan JSON)   2572–2820
   │  ├─ article.card.call-card > h2 + div.call-path#call-path                 2828–2831
   │  └─ article.card.traversal-card                                           2833–2866
   │     ├─ div.traversal-head > div(h2,#traversal-summary) + span#traversal-mode
   │     ├─ div.substep-tree-summary > #substep-walk + #substep-change + #substep-tree-detail
   │     └─ div.traversal-layout
   │        ├─ div.walk-tree#walk-tree
   │        └─ div.traversal-side
   │           ├─ 4 × div.traversal-fact (#traversal-current #traversal-movement
   │           │                          #traversal-return #traversal-next)
   │           ├─ div.traversal-controls (#traversal-previous #traversal-play
   │           │                          #traversal-slider #traversal-next-button)
   │           └─ div.traversal-legend (v / c / r swatches)
   └─ aside.card.artifact-card                                                 2869–2901
      ├─ div.artifact-card-header > h2 + button#artifact-toggle
      └─ div.artifact-body#artifact-body
         ├─ p.artifact-status#artifact-status
         ├─ div.artifact-label "Before" + pre#artifact-before
         ├─ div.artifact-arrow "↓"
         ├─ div.artifact-label "After this substep" + pre#artifact-after
         └─ details.example > summary + pre > code   (running example query)
```

### 4.2 Runtime DOM order of `.center`

`initializePassTable()` (L5353–5367) executes once at bootstrap and moves `.pass-lab` out of
`#optimization-additional-context` and inserts it immediately **before** `.step-detail`:

```
level-two → compiler-lab → physical-lab → boundary-lab → execution-lab
          → pass-lab → step-detail → call-card → traversal-card
```

`.center > .pass-lab { margin-top: 0; box-shadow: var(--shadow) }` (L560–563) exists precisely to
restyle the relocated node as a peer card.

Consequences that a reader of the raw HTML would otherwise mis-model:
- `details#physical-plan-deep-dive` travels with `.pass-lab` and is therefore a sibling of
  `.step-detail` at runtime, not a descendant.
- `optimizationTableRows()` uses the child combinator
  `#optimization-additional-context > .context-table-wrap .context-table tbody tr` (L5314), which
  continues to resolve correctly after the move.

### 4.3 Element ID inventory

- **167** `id` attributes in the static body.
- **166** distinct ids read through `$(id)`.
- **14** ids are created at runtime by `innerHTML` templates inside the boundary lab and then read
  back: `boundary-node-picker`, `boundary-view-tabs`, `boundary-plan-view`,
  `boundary-before-node-source`, `boundary-after-node-source`, `boundary-toggle-grid`,
  `boundary-context-json`, `boundary-quiz-result`, `boundary-failures`, `boundary-failure-source`,
  `boundary-debug-guard`, `boundary-debug-interop`, `boundary-debug-parser`, `boundary-debug-root`.
- **8** static ids are never passed to `$()`; they exist only as ARIA targets or CSS hooks:
  `level-one-heading`, `level-two-heading`, `additional-context-heading`,
  `optimization-additional-context-heading`, `stage-overview-body`, `artifact-body`,
  `boundary-primary-source`, `boundary-secondary-source`. (The last two *are* used, indirectly, via
  `setBoundarySource(elementId, …)`.)

---

## 5. Visible regions and components

### 5.1 Network beacon — `aside#network-beacon`

HTML L2127–2134 · CSS L37–119 · render `renderNetwork()` L6513–6525.

Fixed overlay: `position: fixed; right:16px; bottom:14px; z-index:100;
width: min(390px, calc(100vw - 28px)); padding:11px 13px; border:2px solid var(--line);
border-radius:12px; background: rgba(8,19,33,.97); box-shadow: 0 14px 40px rgba(0,0,0,.46);
backdrop-filter: blur(12px)`.

Three text slots plus a state pill. The pill carries a `::before` dot (`8×8px`, `border-radius:50%`,
`background: currentColor`).

| State class | Border | Pill background / colour | Additional |
|---|---|---|---|
| `none` | `rgba(117,220,142,.48)` | `rgba(117,220,142,.12)` / `--green` | — |
| `possible` | `rgba(255,199,102,.7)` | `rgba(255,199,102,.14)` / `--amber` | — |
| `imminent` | `rgba(255,140,175,.72)` | `rgba(255,140,175,.14)` / `--pink` | — |
| `active` | `#ff5877` | `rgba(255,88,119,.18)` / `#ff6f89` | background `rgba(40,10,22,.98)`; `box-shadow: 0 0 0 4px rgba(255,88,119,.14), 0 14px 42px rgba(0,0,0,.5)`; `animation: networkPulse 1.25s ease-in-out infinite` (L116–119: spread ring animates 3px → 8px → 3px) |

`renderNetwork` replaces the whole class list: `beacon.className = \`network-beacon ${state}\``.

**Resolution algorithm** (L6514–6519):

```js
override = networkOverrides[`${stageIndex}-${stepIndex}`]     // may be undefined
base     = stageNetworkDefaults[stageIndex]                   // 4-tuple, always defined
state   = override?.state   ?? base[0]
label   = override?.label   ?? base[1]
route   = override?.route   ?? base[2]
purpose = override?.purpose ?? base[3]
```

Field-by-field `??` merge — an override may supply any subset. Eight overrides exist
(`1-0`, `1-2`, `5-2`, `7-3`, `8-2`, `9-3`, `9-4`, `9-5`); all eight happen to supply all four fields.

`active` is reachable at **exactly one substep, S10.5 (`9-4`)** — the managed
`ExecuteCrossClusterQuery` submission. This is the single point in the whole walkthrough that claims
a real outbound cross-cluster HTTP request.

The static HTML ships the `none` state pre-rendered (`No HTTP` / `Local process only` / *"This
substep performs in-memory parsing, analysis, planning, or native calls only."*), which is
overwritten on the first `render()`.

### 5.2 Header

`header` is a `display:flex; justify-content:space-between; gap:28px` card. Left: `h1` at
`clamp(1.55rem, 3vw, 2.18rem)` plus `p.subtitle`. Right: `.level-key`, an `auto 1fr` grid with amber
`<b>` labels and muted `<span>` descriptions, `min-width: 260px` (relaxed to `0` at ≤520px).

Below 820px, `header { flex-direction: column }`.

### 5.3 Level-1 stage strip — `nav#stage-strip`

CSS L185–238 · render `renderStages()` L6387–6399.

`display:grid; grid-template-columns: repeat(10, minmax(125px,1fr)); gap:7px; overflow-x:auto;
padding: 2px 2px 8px`.

Each entry is a `button.stage-button` (`min-height:91px; padding:10px 9px; text-align:left;
background: var(--surface3)`) built with `innerHTML`:

```html
<span class="num">{index+1}</span>
<span class="name">{stage.short}</span>
<span class="kind">{stage.kind}</span>
```

- `.num` — `24×24px` circular badge, `background:#233c5c; color: var(--blue); font-weight:850`.
- `.selected` — `border-color: var(--amber)`, `background: rgba(255,199,102,.11)`,
  `box-shadow: inset 0 0 0 1px rgba(255,199,102,.18)`; `.num` inverts to amber fill on `#172033`.
- `.visited:not(.selected)::after` — a green `✓` at `top:7px; right:8px`.

Visitation is tracked by `const visited = new Set([0])` (L5310); `selectStage` adds to it (L6669).
`selectStep` does **not**. Stage 1's tick therefore depends entirely on the seed value, because
`selectStage(0)` is never called for the initial render.

After render, `requestAnimationFrame(() => scrollChildOnAxis(strip, strip.children[stageIndex], "x"))`
centres the selected chip.

`#journey-progress` displays `Stage N of 10`.

### 5.4 Stage overview — `aside.card.stage-overview`

`position: sticky; top: 12px; padding: 18px` (L260–264).

`renderStageOverview()` (L6401–6415) writes:

| Element | Content |
|---|---|
| `#stage-badge` | `Stage {n} · {stage.kind}` |
| `#stage-compact` | `S{n}` (hidden unless collapsed) |
| `#stage-title` | `stage.title` (`1.45rem`) |
| `#stage-purpose` | `stage.purpose` |
| `#stage-input` / `#stage-output` / `#stage-owner` / `#stage-not` | the four ownership fields |
| `#stage-handoff` | `stage.handoff` |
| `#previous-stage` `.disabled` | `stageIndex === 0` |
| `#next-stage` `.disabled` | `stageIndex === 9` |

`.ownership > div` — bordered `var(--surface2)` cards with uppercase blue `<b>` labels.
`.handoff` — `border-left: 4px solid var(--cyan)` on `rgba(79,224,208,.08)`.
`.stage-nav` — `1fr 1fr` grid (collapses to `1fr` at ≤520px).
`.note` — pink-tinted static running-example note.

**Collapse** (`toggleStageOverview()` L6376–6385):

```js
collapsed = card.classList.toggle("collapsed");
$("workspace").classList.toggle("stage-collapsed", collapsed);
$("stage-toggle").textContent = collapsed ? "+" : "−";
$("stage-toggle").setAttribute("aria-expanded", String(!collapsed));
$("stage-toggle").title = collapsed ? "Expand stage overview" : "Collapse stage overview";
```

Collapsed CSS (L281–288): `padding:10px`; header becomes a centred column; `.stage-badge` and
`.stage-overview-body` are `display:none`; `.stage-compact` becomes `display:block`.

### 5.5 Level-2 substep rail — `section.card.level-two`

CSS L339–437 · render `renderSubsteps()` L6417–6464.

`nav#substep-strip { display:flex; gap:7px; overflow-x:auto; margin-top:10px; padding-bottom:5px }`.

Each entry is a `div.substep-card` (`flex: 0 0 auto; flex-direction: column; min-width:155px;
max-width:205px`) containing a button and an anchor:

```html
<button class="substep [done] [selected]">
  <small>Substep {j+1}</small>
  <b>{step[0]}</b>
  <span class="substep-behavior">
    <span class="walk">{treeBehaviors[i][j][0]}</span>
    <span class="change">{treeBehaviors[i][j][1]}</span>
    {runnerCount}
  </span>
</button>
<a class="substep-code-link" href=… target="_blank" rel="noopener noreferrer">
  {codeLocationLabel(preciseLinks[i][j])}
</a>
```

`runnerCount` precedence (L6428–6438) — **first match wins**:

| Order | Lab present | Markup |
|---|---|---|
| 1 | `passLabs[key]` | `<span class="pass-count">run {n} pass|passes</span>` (green) |
| 2 | `physicalLabs[key]` | `<span class="manual-count">run {n} actions</span>` (blue) |
| 3 | `compilerLabs[key]` | `<span class="manual-count">run {n} actions</span>` |
| 4 | `boundaryLabs[key]` | `<span class="manual-count">explore {n} actions</span>` |
| 5 | `executionLabs[key]` | `<span class="manual-count">run {n} runtime events</span>` |
| — | none | `""` — no badge at all |

Button states: `.done` when `index < stepIndex` (green border); `.selected` when
`index === stepIndex` (cyan border + `rgba(79,224,208,.1)`).

`.walk-controls` — `grid-template-columns: auto minmax(130px,1fr) auto; gap:8px`.
`input#step-slider` has `min="0"`, no static `max`; `renderSubsteps` sets
`slider.max = steps.length - 1` and `slider.value = stepIndex`. `accent-color: var(--cyan)`.

### 5.6 Step detail — `article.card.step-detail`

`renderStep()` L6466–6511, `padding: 20px`.

| Element | Source |
|---|---|
| `#step-badge` | `Stage {i+1} · Substep {j+1}` |
| `#step-title` | `step[0]` (`1.38rem`) |
| `#step-summary` | `step[1]` |
| `#step-action` | `step[1]` — **the identical string, rendered twice** |
| `#step-why` | `step[2]` |
| `#step-observe` | `step[3]` |
| `#step-next` | `step[4]` |
| `#step-count` | `{j+1} / {steps.length}`, `font-variant-numeric: tabular-nums` |
| `#source-link` | `Open {codeLocationLabel(preciseLinks[i][j])}` |

`.detail-grid` is `1fr 1fr; gap:9px` (single column ≤820px). Each `.detail-box` has
`min-height:120px` and a 4px left border keyed to semantics:

| Box | id | Left border |
|---|---|---|
| `.action` "What happens now" | `#step-action` | `--cyan` |
| `.why` "Why this exists" | `#step-why` | `--amber` |
| `.observe` "What to inspect while debugging" | `#step-observe` | `--purple` |
| `.next` "What comes next" | `#step-next` | `--green` |

Two conditional context sections (`display:none` → `.visible` at L487–493):

| Section | Visible when | Content |
|---|---|---|
| `#additional-context` | `stageIndex === 3 && stepIndex === 1` (**S4.2**) | Static 3-column, 4-row table: `BestEffortAssignerPass`, `QueryResultTruncation`, `ExecuteAndCacheOptimizerPass`, `TableReferenceRowStoreNormalizationPass` |
| `#optimization-additional-context` | `stageIndex === 4 && stepIndex === 0` (**S5.1**) | Static 4-column, 22-row table of the GenericOptimizationPhase schedule; two-way bound to the pass lab (§6.2.6) |

`.context-table` is `min-width: 760px` inside `.context-table-wrap { overflow-x:auto }`; first column
is cyan monospace `white-space: nowrap`.

### 5.7 Method path — `article.card.call-card`

`#call-path` is a wrapping flex row rebuilt on every `renderStep`. For each string in `step[5]`:

```js
target = methodTargets[method] || preciseLinks[stageIndex][stepIndex];
link.textContent = `${method} ↗`;
link.title = `Open ${codeLocationLabel(target)}`;
```

An `<i>→</i>` separator (cyan, `font-style: normal`) precedes every entry after the first.

**Verified:** all 45 call-path arrays resolve entirely within `methodTargets`. The
`|| preciseLinks[…]` fallback is unreachable with the shipped data.

### 5.8 Traversal card — `article.card.traversal-card`

`renderTraversal()` L6579–6612 · `renderTraversalNode()` L6538–6577.

Header: `h2` "How the tree is traversed here", `#traversal-summary` = `definition.summary`, and a
purple pill `#traversal-mode` = `definition.mode`.

`.substep-tree-summary` — `auto auto 1fr` grid on a cyan-tinted panel:
`#substep-walk` (cyan badge), `#substep-change` (amber badge), `#substep-tree-detail` (paragraph).
All three come from `treeBehaviors[stageIndex][stepIndex]`.

`.traversal-layout` — `minmax(330px,1.15fr) minmax(250px,.85fr); gap:12px` (single column ≤820px).

**Left: `#walk-tree`** — `min-height:430px; overflow:auto; padding:12px; background: var(--surface3)`.
Nested `<ul>/<li>` with CSS connector lines (`ul ul::before` vertical rule at `left:-12px`,
`li::before` 12px horizontal stub at `top:17px`; suppressed for the root `li`).

Each node row is a `minmax(0,1fr) 28px` grid: `button.walk-node` + `a.walk-node-source` (`↗`).

Node state (L6544–6553):

```js
activeId            = definition.order[traversalIndex]
previousOccurrences = count of node.id within order[0 .. traversalIndex-1]
activeOccurrence    = count of node.id within order[0 .. traversalIndex]
appearsAgain        = order.slice(traversalIndex+1).includes(node.id)
isCurrent   = node.id === activeId
isReturning = isCurrent && previousOccurrences > 0
isVisited   = !isCurrent && activeOccurrence > 0
```

| Class | Visual |
|---|---|
| base | `border-left: 4px solid #496681; background:#122238; color: var(--muted); min-width:285px; padding-left:34px` |
| `.visited` | green left border, `--ink` text, `opacity:.78`; badge becomes `✓` on `rgba(117,220,142,.18)` |
| `.current` | amber border both sides, `rgba(255,199,102,.14)`, `transform: translateX(5px)`, `box-shadow: 0 0 0 2px rgba(255,199,102,.12)`; badge inverts to amber fill |
| `.returning` | blue border both sides, `rgba(84,185,255,.12)` |

`transition: transform .16s, background .16s, border-color .16s, opacity .16s`.

`button.dataset.order` = `firstOrderPosition(order, node.id)` — the **first** 1-based occurrence.
Rendered through `.walk-node::before { content: attr(data-order) }`, but **replaced by `✓` once the
node is `.visited`**, so the ordinal is legible only for not-yet-reached nodes.

The kind label gains the suffix `" · returns later"` when `appearsAgain && isVisited`.

Clicking a node seeks forward first, then wraps to the first occurrence (L6555–6557):

```js
next  = order.findIndex((id, index) => index >= traversalIndex && id === node.id);
first = order.indexOf(node.id);
setTraversal(next >= 0 ? next : first);
```

Source link resolution: `treeNodeReferences[node.id] ?? treeCodeReferences[node.kind] ??
preciseLinks[stageIndex][stepIndex]`. **Verified: every tree node id has a `treeNodeReferences`
entry, so only the first branch is ever taken.**

**Right: `.traversal-side`** — four `.traversal-fact` panels:

| Panel | Content |
|---|---|
| Current operation | `{i+1}/{len}: {kind} — {name}` + `" (return/unwind visit)"` or `" (first entry)"` |
| How Visit moves | `definition.movement` |
| Return / unwind | `definition.unwind` |
| Next node | `{nextNode.kind} — {nextNode.name}` or *"Traversal complete; return the resulting root/artifact."* |

Then `.traversal-controls` (`auto auto 1fr auto`): `←`, `▶`/`❚❚`, `input#traversal-slider`
(`accent-color: var(--amber)`), `→`. Then `.traversal-legend`: green = already visited,
amber = current, blue = returning.

After render, an rAF callback vertically centres `.walk-node.current` **only if**
`walkTree.scrollHeight > walkTree.clientHeight` (L6607–6611).

### 5.9 Artifact transformation — `aside.card.artifact-card`

`position: sticky; top:12px; padding:18px`.

| Element | Content |
|---|---|
| `#artifact-status` | `{stage.title} · {step[0]}` |
| `pre#artifact-before` | `step[6]`, rendered through `renderLinkedTreeBlock` |
| `.artifact-arrow` | `↓`, cyan, `1.25rem` |
| `pre#artifact-after` | `step[7]`, rendered through `renderLinkedTreeBlock` |
| `details.example` | Static running-example query, `pre` capped at `max-height:320px` |

Global `pre` styling (L2028–2038): `overflow:auto; padding:13px; border:1px solid var(--line);
border-radius:9px; background:#081321; color:#d9ecff; font: .77rem/1.52 ui-monospace…;
white-space: pre`.

**Collapse** (`toggleArtifactCard()` L6365–6374) mirrors the stage-overview toggle, adding
`.artifact-collapsed` to `#workspace`, hiding the `h2` and `#artifact-body`, and centring the header.

---

## 6. Runner engines

Exactly one lab is visible per substep. This is guaranteed **by data construction, not by guard
logic**: `renderStep` invokes all five renderers unconditionally (L6504–6508) and each self-hides
when `currentXxxLab()` returns `null`. Verified exhaustively — **no substep key appears in more than
one lab map.**

| Family | Container | Keys | Count | Visibility mechanism |
|---|---|---|---|---|
| Compiler | `#compiler-lab` | `0-0…0-3`, `1-0…1-4`, `2-0…2-3` | 13 | `lab.className = \`compiler-lab${config ? \` visible ${config.kind}\` : ""}\`` — **full class-list replacement** (L5426) |
| Pass | `.pass-lab` | `3-1`, `3-2`, `4-0…4-4`, `5-2`, `5-3`, `6-0…6-4`, `7-4` | 15 | `classList.toggle("visible", Boolean(config))` |
| Physical | `#physical-lab` | `7-0…7-3` | 4 | `classList.toggle("visible", …)` |
| Boundary | `#boundary-lab` | `8-0`, `8-1`, `8-2` | 3 | `classList.toggle("visible", …)` |
| Execution | `#execution-lab` | `9-0…9-5` | 6 | `classList.toggle("visible", …)` |

Lookup helpers (L5317–5335) are all of the form
`return xxxLabs[\`${stageIndex}-${stepIndex}\`] ?? null;`.

### 6.1 Compiler lab

HTML L2194–2236 · data `compilerLabs` L4011–4493 · render `renderCompilerLab()` L5423–5519.

#### 6.1.1 Kind variants

`config.kind` drives border colour, radial-gradient tint, badge colour, and `h4` colour:

| kind | Accent | Border | Badge / `h4` | Substeps |
|---|---|---|---|---|
| `syntax` | `--blue` | `rgba(84,185,255,.48)` | blue | S1.1–S1.4 |
| `semantic` | `--purple` | `rgba(188,132,255,.5)` | purple | S2.1–S2.5 |
| `relop` | `--green` | `rgba(117,220,142,.5)` | green | S3.1–S3.4 |

Background is `radial-gradient(circle at 96% 0, <accent .12–.14>, transparent 28%), rgba(5,18,29,.92)`.

#### 6.1.2 Schema

```ts
CompilerLab = {
  kind: "syntax" | "semantic" | "relop",
  heading: string,     // becomes #compiler-lab-heading verbatim
  badge: string,
  intro: string,
  initial: string,     // the "before" pane for action index 0
  actions: Array<{ title, detail, source, state }>,
  experiment: {
    heading, intro,
    options: Array<[id, label, outcome]>,
    mappings?: Array<[from, to]>
  }
}
```

`renderCompilerLab` dereferences `config.experiment.options.length` at L5431 **before** any
existence check — a lab without `experiment` would throw. All 13 supply one.

#### 6.1.3 Rendering

- `#compiler-lab-heading` = `config.heading` (**not** the substep title — this is the only lab family
  besides execution that keeps its own heading).
- `#compiler-lab-intro`, `#compiler-lab-badge` (pill, monospace `800 .69rem`).
- `.compiler-controls`: `#compiler-reset`, `#compiler-previous`, `#compiler-next`, `#compiler-apply`.
- `nav#compiler-action-rail`: numeric chips `1..N`, `min-width:36px`, `title = "{n}. {action.title}"`,
  classes `selected` (blue) / `applied` (green). rAF-centred horizontally.
- `.compiler-action`: `#compiler-action-title` = `"{n}. {title}"`, `#compiler-action-detail`,
  `a#compiler-action-source` = `Open {codeLocationLabel(source)}`.
- `#compiler-progress` (innerHTML):
  `Cumulative progress: <b>{applied+1} / {N} actions applied</b>. Previewing action {n}.`
- `.compiler-workspace`: `minmax(310px,1fr) minmax(310px,1fr); gap:9px` (single column ≤850px).
  Panel headings vary by kind (L5444–5453):

  | kind | Before heading | After heading |
  |---|---|---|
  | `syntax` | Parser input before this action | Parser artifact after this action |
  | `semantic` | Binding state before this action | Binding state after this action |
  | `relop` | Logical artifact before this action | Logical artifact after this action |

- Before state = `compilerActionIndex === 0 ? config.initial : actions[compilerActionIndex-1].state`.
  After state = `actions[compilerActionIndex].state`. Both rendered via `renderPhysicalState` with
  the LCS diff (`diff-removed` on the before pane, `diff-added` on the after pane).
- `.compiler-experiment`: `#compiler-experiment-heading`, `#compiler-experiment-intro`, a wrapping
  row of option buttons (`.selected` = amber), `#compiler-experiment-output`
  (`<b>{label}: </b>{outcome}`), and `#compiler-mapping-grid`.
- **`#compiler-mapping-grid` renders only when `config.experiment.mappings` exists *and* the selected
  option id is exactly `"map"`** (L5508). Only `2-1` (S3.2) qualifies; its option ids are
  `csl | map | relop` and its four mappings are `CslLimitOperator→Limiter`,
  `CslProjectOperator→Projection`, `CslFilterOperator→Selection`, `CslJoinOperator→InnerEquiJoin`.
  Both sides go through `appendTreeLinkedText`, so each operator name becomes a source link.

#### 6.1.4 Per-lab dimensions

| Key | Coord | kind | Actions | Experiment options | Mappings |
|---|---|---|---|---|---|
| `0-0` | S1.1 | syntax | 3 | 3 (`example` / `limit` / `oversized`) | — |
| `0-1` | S1.2 | syntax | 3 | 3 (`original` / `effective` / `late`) | — |
| `0-2` | S1.3 | syntax | 4 | 4 (`valid` / `pipe` / `paren` / `command`) | — |
| `0-3` | S1.4 | syntax | 4 | 4 (`clean` / `diagnostic` / `nohash` / `depth`) | — |
| `1-0` | S2.1 | semantic | 4 | 4 (`full` / `remote` / `plugins` / `schema`) | — |
| `1-1` | S2.2 | semantic | 4 | 4 (`present` / `missing` / `hidden` / `scalar`) | — |
| `1-2` | S2.3 | semantic | 4 | 4 (`cache` / `prefetch` / `provider` / `blocked`) | — |
| `1-3` | S2.4 | semantic | **5** | 4 (`valid` / `types` / `missing` / `hint`) | — |
| `1-4` | S2.5 | semantic | 4 | 4 (`clean` / `name` / `pattern` / `permission`) | — |
| `2-0` | S3.1 | relop | 4 | 4 (`tuple` / `wide` / `graph` / `none`) | — |
| `2-1` | S3.2 | relop | **5** | 3 (`csl` / `map` / `relop`) | **4** |
| `2-2` | S3.3 | relop | 4 | 4 (`full` / `scope` / `tuple` / `unwrap`) | — |
| `2-3` | S3.4 | relop | 4 | 4 (`root` / `metadata` / `lifetime` / `complete`) | — |

### 6.2 Pass lab

HTML L2453–2824 · render `renderPassLab()` L6224–6317.

#### 6.2.1 Pass object schema

```ts
Pass = {
  name: string,
  changes: boolean,     // drives the CHANGES/NO CHANGE badge and chip colour
  before: string,       // tree text entering the pass
  after: string,        // tree text after the pass
  walk: string[],       // ordered visit tokens, matched against tree lines by substring
  rule: string,         // rule/result explanation
  optimizes: string,    // "what it optimizes" prose
  source: string        // ADO deep link
}
```

Built either as literals (`phasePasses`, L3427–3450) or through the factory
`scheduledPass(name, line, file, tree = PASS_TREE_REMOTED, options = {})` (L3531–3542), whose
defaults are:

```
changes   ?? false
before    ?? tree
after     ?? tree
walk      ?? DEFAULT_PASS_WALK                       (10 tokens, L3414–3425)
rule      ?? "This scheduled pass visits its applicable nodes, but no rule
              changes the illustrated query tree."
optimizes ?? passPurpose[name] ?? `Runs ${name} at its source-defined position in this phase.`
source    ?? src(file, line, options.endLine ?? line)
```

`passPurpose` (L3466–3529) supplies one-line purposes for 58 named passes.

#### 6.2.2 Shared tree constants

Logical trees (L3342–3412, L3452–3464), each an ASCII tree over the running example:

| Constant | Shape |
|---|---|
| `PASS_TREE_INITIAL` | `Limiter(take 10) → Projection(final) → InnerEquiJoin` with both branch projections above their limiters; remote side `Selection → RemoteQueryOperator → TableReference(Trips)` |
| `PASS_TREE_PROJECTIONS_PUSHED` | branch projections pushed below `take 2`; remote projection pushed below the selection |
| `PASS_TREE_LIMITERS_PUSHED` | final `Projection` above `Limiter(take 10)`; local `Projection` above `Limiter(take 2)` |
| `PASS_TREE_GENERIC_REWRITE` | remote `Projection` above `Selection` |
| `PASS_TREE_FULL_PROJECTION` | `Limiter(take 10)` back on top; remote `Selection` above `Projection` |
| `PASS_TREE_REMOTED` | `RemoteQueryOperator` hoisted above `Limiter(take 2) → Selection → Projection → TableReference(Trips)` |
| `PASS_TREE_DISTRIBUTED` | local branch replaced by `SubQueryMerge → StagedSubquery → Limiter → Projection → TableReference` |

Physical trees (L3645–3727), used only by `7-4`:
`PHYSICAL_TREE_INITIAL` → `PHYSICAL_TREE_PREJOIN` (adds `CreatePrejoinFilter: true`,
`PrejoinFilterClosureSlot`, and a probe-side `PrejoinFilterNode`) → `PHYSICAL_TREE_NORMALIZED_PREJOIN`
(replaces the wrapper with `IteratorScan` + `__prefilter(ClosureSlot, payment_type)`).

`DEFAULT_PASS_WALK` = `["Limiter(take 10)", "Projection(final", "InnerEquiJoin", "Projection(left",
"Limiter(take 2)", "TableReference(TelemetryEvents)", "Projection(right", "Selection(payment_type",
"RemoteQueryOperator", "TableReference(Trips)"]`.

#### 6.2.3 Pass-set composition

| Key | Coord | `label` | Passes | Composition |
|---|---|---|---|---|
| `3-1` | S4.2 | RelopPreparationPhase | 4 | `preparationPasses` (L3549–3554), all on `PASS_TREE_INITIAL` |
| `3-2` | S4.3 | CatalogQueryPhase (conditional) | 3 | `catalogPasses` (L3556–3567), all skipped for this query |
| `4-0` | S5.1 | GenericOptimizationPhase | **22** | `phasePasses`; **5 have `changes:true`** — #2 `PropagateProjectionsLightPass`, #7 `PropagateLimiterPass`, #8 `GenericOptimizationPass`, #9 `PropagateProjectionsPass`, #14 `RemotingPass` |
| `4-1` | S5.2 | Initial RemotingPass | 1 | `[phasePasses[13]]` — the same `RemotingPass` object as #14 above |
| `4-2` | S5.3 | PreDistributionOptimizationPhase · remoting #2 | 1 | `scheduledPass("RemotingPass", 19, preDistributionFile)` |
| `4-3` | S5.4 | PreDistributionOptimizationPhase · remaining passes | 3 | `PropagateProjectionsPass`, `ForkOptimizationPass`, `RemotingPass` |
| `4-4` | S5.5 | FinalCleanupPhase | 3 | `FinalCleanupPass`, `PropagateProjectionsPass`, `VoidOperatorsEliminationPass` |
| `5-2` | S6.3 | Conditional partial-source OptimizeQuery pipeline | **29** | `partialSourcePasses` = `[...phasePasses]` + 7 (L3625–3634) |
| `5-3` | S6.4 | Non-final PostSubqueryResultSubstitutionPhase | 6 | `nonFinalSubstitutionPasses` (L3636–3643) |
| `6-0` | S7.1 | PostQueryResultSubstitutionOptimizationPhase | **23** | `postQueryPasses` from `postQueryPassSpecs` (L3569–3582) |
| `6-1` | S7.2 | Post-substitution placement decisions | 3 | `postQueryPasses.filter(p => ["RemotingPass","CostBasedOptimizationPass","JoinOptimizationPass"].includes(p.name))` |
| `6-2` | S7.3 | GraphPreparationPhase | 1 | `GraphMatchPreparationPass` |
| `6-3` | S7.4 | QueryDistributionPhase | 11 | `distributionPasses`; only `QueryDistributionPass.Staged` sets `changes:true` and advances the running `distributionTree` to `PASS_TREE_DISTRIBUTED` (L3591–3603) |
| `6-4` | S7.5 | Join filtering + PostSubqueryResultSubstitutionPhase | 15 | `finishingPasses` on `PASS_TREE_DISTRIBUTED` |
| `7-4` | S8.5 | QueryPlanFinalizer physical pass pipeline (includes conditional candidates) | 17 | `physicalPasses`; `AddPrejoinFiltersPass` and `NormalizePrejoinFiltersPass` set `changes:true` |

#### 6.2.4 Rendering

- `#pass-lab-heading` = `"Run this pass yourself"` when `passes.length === 1`, else
  `"Run the {n} passes yourself"`.
- `lab.querySelector(".pass-lab-head p")` — **the first `<p>` only** — is replaced with
  `"{config.label}: select a pass, walk its tree visit node by node, then apply it to advance the
  cumulative tree."`
  The **second `<p>` (L2458) is static and always rendered**, under every one of the 15 pass labs.
  It reads: *"The marks are derived from rule matching against the illustrated tree at the pinned
  commit. These labs cover source-defined `Pass<T>` schedules; compiler methods such as `SyntaxPass`
  and the semantic visitor remain in the traversal panel because they are not pass-manager queues. To
  confirm feature-flag-dependent runtime details, enable the existing ReportPassResult dump hook while
  debugging."*
- `#pass-lab-mark` — `CHANGES THIS TREE` (`.pass-mark.changes`, green fill on `#06110a`) or
  `NO STRUCTURAL CHANGE` (`.pass-mark.same`, outlined).
- `nav#pass-rail` — `button.pass-chip` (`width:36px; height:32px`). Classes: `.changes`
  (green border+text), `.selected` (cyan border, `rgba(79,224,208,.14)`, white text), `.applied`
  (`::after { content: "✓" }`). `title = "{n}. {name}: changes tree|no structural change"`.
  `rail.setAttribute("aria-label", \`${config.label} passes\`)` — the only dynamic ARIA update
  in the file.
- `#pass-lab-title` = `"{n}. {pass.name}"`.
- `#pass-lab-explanation` = one of two fixed strings keyed on `pass.changes`.
- `#pass-lab-optimizes` resolution chain (L6262–6264):
  `pass.optimizes ?? passPurpose[pass.name] ?? genericRow?.cells[1].textContent ??
  \`Runs ${pass.name} at this source-defined point in the phase.\``,
  where `genericRow` is non-null only at S5.1. `linkCodeReferences` is then run over its parent.
- `#pass-lab-source` = `pass.source ?? codeReferences[pass.name] ?? preciseLinks[i][j]`.
- `.pass-diff-legend` — static swatches: `removed` `#ff6b6b`, `added` `--green`,
  `current` `--amber`.
- `.pass-tree-grid` — `1fr 1fr; gap:10px` (single column ≤850px), `pre#pass-tree-before` and
  `pre#pass-tree-after` (`min-height:292px`). Rendered by `renderPassTree`, which wraps each line in
  a `<span>`, adds the diff class when the line is not in the unchanged set, and adds `.active-line`
  when the line **contains** the current walk token.
  The after pane receives `activeToken` **only when `pass.changes` is true** (L6273) — otherwise it
  shows no active-line highlight.
- `.pass-walk` — `#pass-walk-status` (innerHTML)
  `Tree visit <b>{k} / {n}</b> — current node: <b>{token}</b>`; controls `#pass-node-previous`,
  `input#pass-node-slider`, `#pass-node-next`; `#pass-rule` = `pass.rule` on a purple-bordered panel.

#### 6.2.5 Physical deep dive — `details#physical-plan-deep-dive`

`hidden` unless `stageIndex === 7 && stepIndex === 4` (**S8.5**), L6276–6285. When shown:

```js
$("physical-detail-selected-pass").textContent = `Selected physical pass: ${pass.name}`;
$("physical-detail-selected-purpose").textContent =
  `${pass.optimizes ?? passPurpose[pass.name] ?? "This pass checks or rewrites the
    execution-ready physical tree."} ${pass.rule}`;
linkCodeReferences(physicalDetail);
physicalDetail.querySelectorAll("pre").forEach(pre => renderLinkedTreeBlock(pre, pre.textContent));
```

The re-linkification is idempotent because the linkified block's `textContent` equals the original
text.

Contents:
- Summary line: *"Expand the full plan behind the compact physical tree — 20 operators · 13 scalar
  nodes · schemas and bindings."*
- Two `.physical-distinction` callouts, the first stating that the attached `.show queryplan`
  document is the **detailed logical Relop input entering Stage 8**, not the serialized C# physical
  `QueryPlanNode` output.
- `.physical-source-strip` listing 13 exact source anchors.
- `.physical-fidelity-grid` — metrics (`20` operator nodes / `13` scalar nodes / `6` bindings) plus
  a `<pre>` of the expanded operator hierarchy.
- `table.physical-map` — 5 rows mapping `.show queryplan` node → C# lowering path → compact physical
  representation → information retained at runtime.
- `details.physical-raw` — the complete `.show queryplan` JSON (L2572–2820), including the full
  51-column `Trips` source schema.

#### 6.2.6 Two-way binding with the 22-row optimization table

`initializePassTable()` (L5353–5367) prepares the table once:

```js
optimizationTableRows().forEach((row, index) => {
  row.classList.add("pass-row");
  row.dataset.passIndex = index;
  if (row.cells.length === 3) row.insertCell();          // adds the 4th "This example" cell
  row.addEventListener("click", event => {
    if (event.target.closest("a")) return;               // do not hijack inline code links
    selectPass(index);
  });
});
```

`renderPassLab` then writes back (L6303–6316):

```js
optimizationTableRows().forEach((row, index) => {
  if (stageIndex !== 4 || stepIndex !== 0) { row.classList.remove("selected"); return; }
  row.classList.toggle("selected", index === passIndex);
  const status = passes[index];
  const cell = row.cells[3];
  cell.textContent = "";
  const badge = document.createElement("span");
  badge.className = `pass-mark ${status.changes ? "changes" : "same"}
                     ${index <= appliedPassThrough ? "applied" : ""}`;
  badge.textContent = status.changes ? "CHANGES" : "NO CHANGE";
  cell.appendChild(badge);
});
```

`.pass-row:hover td` → `rgba(84,185,255,.06)`; `.pass-row.selected td` → `rgba(79,224,208,.09)`;
`.pass-mark.applied` gains `box-shadow: 0 0 0 2px rgba(79,224,208,.35)`.

Because this block sits **after** the `if (!config) return;` early exit (L6228), leaving S5.1 for a
substep without a pass lab removes `.selected` but leaves the 4th-cell badges in place. The section
is hidden in that state, so the staleness is not observable.

### 6.3 Physical lab

HTML L2238–2277 · data `physicalLabs` L3772–4009 · render `renderPhysicalLab()` L5541–5594.

```ts
PhysicalLab = {
  mode: string,          // pill text
  intro: string,
  inputLabel: string,    // <summary> of the input-contract details
  input: string,         // the input contract body
  outputLabel: string,   // suffixed onto "After selected action · "
  initial: string,
  actions: Array<{ name, detail, state, source }>
}
```

| Key | Coord | `mode` | Actions | Input contract |
|---|---|---|---|---|
| `7-0` | S8.1 | `CONTEXT ASSEMBLY` | 5 | Available query-scoped inputs (9 lines) |
| `7-1` | S8.2 | `VISITOR + UNWIND` | 8 | `PASS_TREE_DISTRIBUTED` |
| `7-2` | S8.3 | `JOIN ASSEMBLY` | 7 | Logical `InnerEquiJoin` contract |
| `7-3` | S8.4 | `REMOTE KQL COMPILATION` | 7 | Remote logical island |

Rendering specifics:
- `#physical-lab-heading` is **overwritten** with `Run “{stages[i].steps[j][0]}” yourself` (L5550);
  the static heading text never appears.
- `#physical-lab-intro` = `config.intro + " Select an action to preview its effect; Apply commits it
  to your cumulative progress."`
- `details.physical-input-contract` is collapsed by default; `<summary id="physical-input-label">`
  carries `config.inputLabel`, `pre#physical-input-state` carries `config.input` (rendered without
  diff classes).
- `#physical-output-label` = `"After selected action · {config.outputLabel}"`.
- `.physical-state-grid` is deliberately **asymmetric**: `.8fr 1.25fr` (single column ≤850px).
- Chips are `.physical-action-chip` (`min-width:38px; height:32px`); `.applied::after
  { content: " ✓" }` — note the **leading space**, unlike `.pass-chip.applied::after { content: "✓" }`.
- Two actions of `7-3` (L3968–3993) are raw object literals rather than `physicalAction(...)` calls,
  so their `source` points at `RelOpToCsl.cs` (484–503 and 492–503) instead of
  `InitialQueryPlanBuilder.cs`. Their field shape is otherwise identical.

### 6.4 Boundary lab

HTML L2279–2308 · data `boundaryLabs` L4495–4532 · render `renderBoundaryLab()` L5940–5968.

```ts
BoundaryLab = {
  badge: string,
  intro: string,
  actions: Array<{ title, lane: "C#" | "Interop" | "C++", detail, source }>
}
```

| Key | Coord | `badge` | Actions | Lane distribution |
|---|---|---|---|---|
| `8-0` | S9.1 | `PLAN → JSON → UTF-8` | 6 | all `C#` |
| `8-1` | S9.2 | `REQUEST → CONTEXT BYTES` | 5 | all `C#` |
| `8-2` | S9.3 | `C# → INTEROP → C++` | 7 | `C#` ×4, `Interop` ×1, `C++` ×2 |

#### 6.4.1 Common chrome

- `#boundary-lab-heading` overwritten with `Run “{substep title}” yourself`.
- `#boundary-lab-badge` = `config.badge`; static default `MANAGED → NATIVE` never survives.
- `#boundary-stage-status` = `Action {k} of {n} · {action.title}`.
- `#boundary-primary-heading` is chosen by **`stepIndex`**, not by lab key (L5954–5958):
  `0 → "Node → JSON → bytes explorer"`, `1 → "Plan vs. request context experiment"`,
  else `"Managed-to-native handoff simulator"`.
- `setBoundarySource("boundary-primary-source", action.source, "Open current action at")`.
- `renderBoundaryRail(config)` — chips with `.selected` (purple) and `.complete`
  (`index < boundaryActionIndex`, green). Clicking a chip calls `stopBoundaryPlay()` first.
- `renderBoundaryLanes(config)` (L5638–5664) — three fixed lanes:

  | key | Title | Subtitle | Placeholder when empty |
  |---|---|---|---|
  | `csharp` | C# managed | Build and serialize | "Ready at the managed query-plan boundary." |
  | `interop` | Interop boundary | Transfer ownership | "Waiting for the payload." |
  | `cpp` | C++ native | Parse and execute | "Waiting for the payload." |

  A lane displays the `detail` of the **last action at or before `boundaryActionIndex`** whose lane
  matches. `.active` when the current action's lane matches; `.completed` when the lane has prior
  actions but is not active (green heading).
  Lane key mapping: `lane => lane === "C#" ? "csharp" : lane === "C++" ? "cpp" : "interop"`.

#### 6.4.2 Body A — `stepIndex === 0`, `renderBoundaryPlanLab` (L5685–5774)

`boundaryPlanNodes` (L4534–4541):

| Name | NodeId | `fields` |
|---|---|---|
| `BatchNode` | 0 | `DefaultOperator: 0`, `Operators: ["ConsumerNode#1"]` |
| `ConsumerNode` | 1 | `DataSet: "PrimaryResult"`, `Source: "IteratorLimiter#2"` |
| `IteratorLimiter` | 2 | `Skip: 0`, `Take: 10`, `Source: "IteratorProjector#3"` |
| `IteratorProjector` | 3 | `ProjectedElements: [0,3,1]`, `Source: "HashJoin#4"` |
| `HashJoin` | 4 | `Flavor: "Inner"`, `BuildKeys:[1]`, `ProbeKeys:[0]`, `ShouldRunInRustJoinEngine: true` |
| `RemoteQueryNode` | **6** | `TargetScope: "help/Samples"`, `QueryParameters: null`, `Result: ["payment_type","trip_id"]` |

**NodeId 5 is intentionally skipped** — it represents the elided local build subtree.

Three views bound to `boundaryView`:

| View | Content |
|---|---|
| `object` | Hand-built ASCII tree: `{name} (QueryPlanNode)` / `├─ NodeId: {id}` / one line per field with `└─` on the last. Rendered through `renderLinkedTreeBlock` |
| `json` | `JSON.stringify({NodeType, NodeId, ...fields}, null, 2)`, also linkified |
| `bytes` | `formatHex(utf8Bytes(json))` as **plain text** — no links |

`formatHex(bytes, limit = 192)` (L5625–5636) emits 16 bytes per row:
`{offset:04x}  {hh hh …, padEnd(47)}  |{ascii}|`, printable range 32–126 else `.`, and appends
`… {n} more bytes` when truncated.

`.boundary-byte-grid` shows three cells: `SELECTED EXCERPT` (bytes of the selected node's JSON),
`COMPLETE SAMPLE` (bytes of a synthetic 10-key plan envelope built at L5694–5705 with `QueryType`,
`RootOperator`, `IsCrossCluster`, `StorageLocators`, `NodeLocators`, `TablePolicies`,
`TotalRowCount`, `AccumulatedPartialQueryState`, `SharedDataStore`, `ObjectsStorageId`), and
`ENCODING = UTF-8`.

Secondary panel: `What the serializer adds` — the NodeId position-index card
(`NodeId {n} → [startByte, endByte)`), the 10 named top-level parts as chips, and two breakpoint
cards linking `BeforeNodeSerialization` (`EncodedQueryPlan.cs:769–778`) and `AfterNodeSerialization`
(`:780–789`).

`renderBoundaryPlanLab(config)` accepts `config` but never reads it.

#### 6.4.3 Body B — `stepIndex === 1`, `renderBoundaryContextLab` (L5787–5863)

Four checkboxes bound to `boundaryContextOptions`:

| key | Label | Value shown | Default |
|---|---|---|---|
| `timeout` | Server timeout | `00:02:00` | **false** |
| `crossCluster` | Cross-cluster query | `true` | **true** |
| `deferPartialFailures` | Defer partial failures | `true` | **true** |
| `activity` | Activity lineage | `request-scoped` | **true** |

`buildBoundaryContext()` (L5776–5785) always emits `ClientRequestId: "KWE.QueryLifecycle;7f42"` and
`IsCrossClusterQuery: boundaryContextOptions.crossCluster`, then conditionally adds `ServerTimeout`,
`DeferPartialQueryFailures`, and `ActivityContext: { ActivityId: "3e787d90-…",
ParentActivityId: "root" }`.

Byte grid: `PLAN BUFFER` = `utf8Bytes(JSON.stringify(boundaryPlanNodes)).length` — **constant**;
`CONTEXT BUFFER` = live; `PLAN REBUILT? = No`.

Live diff against the minimal baseline `{ClientRequestId, IsCrossClusterQuery: false}`, rendered as
`+ {key}: {json}` lines, or `"No request-scoped differences."` when empty.

**Quiz** — *"If `servertimeout` changes, which payload changes?"* with `Plan` / `Context` / `Both`:

| `boundaryQuizAnswer` | `#boundary-quiz-result` text | class |
|---|---|---|
| `""` | `Choose an answer.` | `""` |
| `"context"` | `Correct. It is request context, so the operator tree and serialized plan stay unchanged.` | `correct` (green) |
| `"plan"` / `"both"` | `Not quite. The timeout is request-scoped and belongs only to SerializedContext.` | `incorrect` (pink) |

This renderer **ignores `config` entirely**; the 5 actions of `8-1` drive only the rail, lanes,
status line, and `#boundary-primary-source`.

#### 6.4.4 Body C — `stepIndex === 2`, `renderBoundaryHandoffLab` (L5865–5938)

Renders the interop call as a `.boundary-call` block:
`m_dataEngineQuery.ExecuteQuery(` / `callback` / `serializedContext` / `serializedPlan` / `);`

`.boundary-current-action` shows `ACTION {k} · {lane}` plus the action title and detail.

Four failure injections keyed by `boundaryFailure`:

| key | Title | Result | Source |
|---|---|---|---|
| `none` | Healthy handoff | ExecuteQuery receives all three arguments; native parsing succeeds and a stream source returns to managed code. | `DataEngineQueryProcessor.cs:115–123` |
| `unfinalized` | Unfinalized RootOperator | Stopped in C# before serialization: `RootOperator.NodeId` is negative, so the finalized-plan guard throws. | `DataEngineQueryProcessor.cs:87–94` |
| `malformed` | Malformed plan JSON | Transferred across interop, then rejected by RapidJSON with an error code and byte offset. | `QueryPlanDeserializer.cpp:2793–2813` |
| `invalidRoot` | Missing RootOperator | JSON parses, but `ParseQueryPlan` cannot reconstruct the required RootOperator and the native plan is invalid. | `QueryPlanDeserializer.cpp:2451–2494` |

Secondary panel: a 4-step debugger map (`DataEngineQueryProcessor.cs:91` finalization guard,
`:117` interop call, `QueryPlanDeserializer.cpp:2801` JSON parser, `:2457` root reconstruction) and a
`.boundary-native-map` grid: `SerializedPlan → ParseQueryPlan`,
`RootOperator JSON → ParseQueryPlanNode`, `SerializedContext → execution context`,
`DataEngineQueryCallback ↔ managed services`.

#### 6.4.5 Play mode

`toggleBoundaryPlay()` (L5984–6003):

```js
if (boundaryTimer) { stopBoundaryPlay(); renderBoundaryLab(); return; }
if (boundaryActionIndex === config.actions.length - 1) boundaryActionIndex = 0;   // rewind
boundaryTimer = setInterval(() => {
  if (boundaryActionIndex >= config.actions.length - 1) { stopBoundaryPlay(); renderBoundaryLab(); return; }
  boundaryActionIndex++; renderBoundaryLab();
}, 1100);
renderBoundaryLab();
```

Button label (L5967): `Pause` while running, `Replay` at the last action, else `Play` — the static
`▶ Play` glyph is destroyed on the first render.

Play is halted by: rail chip click (L5676), prev/next (L5979), reset (L6006), and
`resetPassLabState()` (L6348) — i.e. any stage or substep change.

### 6.5 Execution lab

HTML L2310–2368 · data `executionLabs` L5043–5281 · render `renderExecutionLab()` L6113–6197.

#### 6.5.1 Factories

```js
EF = (kind, title, detail) => ({ kind, title, detail })                       // stack frame
EO = (op, zone, id, title, detail) => ({ op, zone, id, title, detail })       // memory event
EA = (lang, title, detail, why, source, stack, stackEffect, heapEffect,
      memory, active, live, pull, ownership, breakpoint) => ({ … })           // 14 positional args
```

Verified value domains across all 44 execution actions:

| Field | Domain |
|---|---|
| `action.lang` | `cpp` \| `rust` \| `csharp` |
| `frame.kind` | `cpp` \| `csharp` \| `rust` \| `abi` |
| `event.op` | `add` \| `update` \| `release` |
| `event.zone` | `managed` \| `borrowed` \| `cpp` \| `rust` |
| `action.active`, `action.live[]` | keys of `executionComponents` — **no dangling references** |

`executionComponents` (L5028–5037):

| key | Title | Detail |
|---|---|---|
| `managed` | Managed query call | C# owns the outer request and callback |
| `deserialize` | Plan deserializer | C++ reconstructs the executable graph |
| `cppJoin` | C++ join shell | Owns child iterators and the Rust handle |
| `rustJoin` | Rust hash join | Owns build/probe state and output collectors |
| `build` | Local build child | Supplies EventId/payment_type rows |
| `remote` | Remote probe child | Runs help/Samples and decodes its stream |
| `stream` | Managed remote stream | Carries serialized remote result frames |
| `output` | Result adapters | Expose Rust frames to the surrounding C++ plan |

#### 6.5.2 Lab dimensions

| Key | Coord | `heading` | Events | Scenarios |
|---|---|---|---|---|
| `9-0` | S10.1 | Deserialize the native operator graph | 7 | 3 |
| `9-1` | S10.2 | Construct the Rust-backed join iterator | 7 | 3 |
| `9-2` | S10.3 | Enter Rust and materialize join state | 7 | 3 |
| `9-3` | S10.4 | Pull C++ children through Rust callbacks | 8 | 4 |
| `9-4` | S10.5 | Execute the remote right child | 8 | 4 |
| `9-5` | S10.6 | Stream joined frames and complete | 7 | 4 |

Each lab also carries a `base` object seeding the four memory zones before any event is folded.

#### 6.5.3 Component order (top to bottom)

1. `#execution-lab-heading` = `config.heading`; `#execution-lab-badge` = `"{n} RUNTIME EVENTS"`
   (overwrites the static `RUNTIME`).
2. `.execution-controls` — `#execution-reset`, `#execution-previous`, `#execution-next`,
   `#execution-apply`.
3. `nav#execution-action-rail` — chips `min-width:38px`, `.selected` pink, `.applied` green.
4. `input#execution-slider` — `min=0`, `step=1`, `max = actions.length - 1`,
   `accent-color: var(--pink)`, full width.
5. `#execution-language-lanes` — three lanes:

   | id | class | Title | Detail |
   |---|---|---|---|
   | `csharp` | `managed` | Managed C# | Request, callback, credentials, streams |
   | `cpp` | `cpp` | C++ Engine | Plan graph, iterators, decoder, RAII |
   | `rust` | `rust` | Rust V3 | Hash table, probe, collectors, frames |

   Active detection: `action.lang === id || (action.lang === "abi" && (id === "csharp" || id === "cpp"))`
   (L6165). The `abi` branch is **unreachable** with the shipped data. An active lane prefixes `● `
   and appends ` · ACTIVE`, and gains `border-color: var(--pink)` plus an inset ring.
6. `.execution-action-card` — `#execution-action-title` = `"{n}. {title}"`,
   `#execution-action-detail`, `a#execution-action-source`, and three `.execution-effect` boxes:
   `why` (amber, `#execution-action-why`), stack (blue, `#execution-stack-effect`),
   `heap` (green, `#execution-heap-effect`).
7. `#execution-progress` — two distinct strings:
   - executed: `Executed through event {k} of {n}. This snapshot includes every cumulative memory
     transition through the selected event.`
   - preview: `Previewing event {k} of {n}. Execute it to mark this event—and any required earlier
     events—complete.`
8. Static `.execution-memory-note` disclaimer (L2342) about conceptual frames, JIT/native inlining,
   allocator arenas, and borrowed pointers.
9. `.execution-runtime-grid` — `minmax(270px,.72fr) minmax(390px,1.28fr)` (single column ≤850px):
   - **Active call stack** — `action.stack` rendered top-first; index 0 gets the `TOP · ` prefix and
     `box-shadow: 0 0 0 1px var(--pink)`. Frame left border: `csharp`/default blue, `cpp` amber,
     `rust` green; **`abi` has no rule and therefore falls back to blue**.
     `#execution-stack-depth` = `"{n} conceptual frames · top first"`.
   - **Heap and live query state** — four zones in fixed order with fixed labels:
     `managed` → "Managed heap / state", `borrowed` → "Temporary / borrowed views",
     `cpp` → "C++ heap / RAII state", `rust` → "Rust heap / owned state". Zone heading colours:
     blue / purple / amber / green. Empty zone → `"Nothing allocated in this zone yet."`
     `#execution-heap-count` = `"{live} live · {released} released"`.
10. `#execution-components` — `repeat(6, minmax(0,1fr))` (3 cols ≤850px, 1 col ≤520px) over all 8
    components:

    | Status | Condition | Text prefix | Style |
    |---|---|---|---|
    | `active` | `id === action.active` | `ACTIVE · ` | pink border, `rgba(255,140,175,.08)` |
    | `waiting` | `action.live.includes(id)` | `LIVE / WAITING · ` | `rgba(255,199,102,.45)` border |
    | `off` | otherwise | `NOT LIVE · ` | `opacity:.4; border-style: dashed` |

11. `.execution-scenario` — heading `"Change the condition · {config.heading}"`; fixed intro
    *"Switch a condition to see how control flow, failure propagation, or lifetime changes without
    pretending that it changes the source-backed baseline timeline above."*; scenario buttons
    (`.selected` amber); `#execution-scenario-output` = `<b>{label}:</b> {text}`.
12. `.execution-ownership` — `repeat(3, minmax(0,1fr))` (1 col ≤850px):
    `#execution-pull-direction`, `#execution-ownership-now`, `#execution-next-breakpoint`.

#### 6.5.4 Memory fold

`executionMemoryAt(config, through)` (L6016–6036):

```js
state = {};
["managed","borrowed","cpp","rust"].forEach(zone => {
  state[zone] = new Map((config.base[zone] ?? []).map(([id,title,detail]) =>
    [id, { id, title, detail, status: "live" }]));
});
config.actions.slice(0, through + 1).forEach(action => {
  action.memory.forEach(event => {
    if (event.op === "add")    state[event.zone].set(event.id, { …, status: "live" });
    else if (event.op === "update") { const cur = state[event.zone].get(event.id) ?? { id: event.id };
                                      state[event.zone].set(event.id, { ...cur, title, detail, status: "mutated" }); }
    else if (event.op === "release"){ const cur = state[event.zone].get(event.id) ?? { id: event.id };
                                      state[event.zone].set(event.id, { ...cur, title, detail, status: "released" }); }
  });
});
```

Missing ids on `update`/`release` are defensively created from `{id}` alone. Insertion order in the
`Map` governs render order.

Visual encoding of `.execution-heap-object`:

| status | Style |
|---|---|
| `live` | default border, `#081522` background; pill green on `rgba(117,220,142,.1)` |
| `mutated` | amber border, `rgba(255,199,102,.05)`; pill amber |
| `released` | `opacity:.48; border-style: dashed`; `strong` gets `text-decoration: line-through`; pill pink |

`.execution-heap-object.current` is defined in CSS (L898) but **never applied** — no code path sets
that class.

`renderExecutionMemory` calls `executionMemoryAt(config, executionActionIndex)` — the heap reflects
the **previewed** event, not `appliedExecutionActionThrough`.

---

## 7. State model, transitions, and gating

### 7.1 Complete mutable state

Declared at L5283–5311. There is no other mutable application state anywhere in the file.

```js
let stageIndex = 0;
let stepIndex = 0;
let traversalIndex = 0;
let traversalTimer = null;
let passIndex = 0;
let passNodeIndex = 0;
let appliedPassThrough = -1;
let physicalActionIndex = 0;
let appliedPhysicalActionThrough = -1;
let compilerActionIndex = 0;
let appliedCompilerActionThrough = -1;
let compilerExperimentIndex = 0;
let boundaryActionIndex = 0;
let boundaryNodeIndex = 0;
let boundaryView = "object";
let boundaryTimer = null;
let boundaryQuizAnswer = "";
let boundaryFailure = "none";
let executionActionIndex = 0;
let appliedExecutionActionThrough = -1;
let executionScenarioIndex = 0;
let boundaryContextOptions = {
  timeout: false, crossCluster: true, deferPartialFailures: true, activity: true
};
const visited = new Set([0]);
const $ = id => document.getElementById(id);
```

### 7.2 Bootstrap

```js
initializePassTable();   // L6737 — one-time DOM surgery + table wiring
render();                // L6738
```

No `DOMContentLoaded` guard is required or present, because the `<script>` is the final element of
`<body>`.

`render()` (L6654–6659) is the only full-refresh entry point:

```js
renderStages();
renderStageOverview();
renderSubsteps();
renderStep();
```

`renderStep()` (L6466–6511) is the fan-out point, in this exact order:

```
write step fields → resolve #source-link
→ toggle #additional-context / #optimization-additional-context
→ write #artifact-status, #artifact-before, #artifact-after
→ rebuild #call-path
→ renderNetwork()
→ renderTraversal()
→ renderPassLab()
→ renderCompilerLab()
→ renderPhysicalLab()
→ renderBoundaryLab()
→ renderExecutionLab()
→ linkCodeReferences over .stage-overview, .step-detail, .traversal-card
```

### 7.3 Stage transition — `selectStage(index)` (L6661–6671)

```js
if (index < 0 || index >= stages.length) return;
stageIndex = index;
stepIndex = 0;
resetPassLabState();              // pass + physical + compiler + boundary state; stops boundary play
resetExecutionLabState();         // executionActionIndex=0, applied=-1, scenario=0
stopTraversal();
traversalIndex = traversalCatalog[index].focuses[0] ?? 0;
visited.add(index);
render();                          // full re-render
```

**No scroll preservation.** Combined with `html { scroll-behavior: smooth }` (L25), the viewport stays
where it was while the document height changes underneath.

### 7.4 Substep transition — `selectStep(index)` (L6673–6686)

```js
if (index < 0 || index >= stages[stageIndex].steps.length) return;
const scrollX = window.scrollX;
const scrollY = window.scrollY;
stepIndex = index;
resetPassLabState();
resetExecutionLabState();
stopTraversal();
traversalIndex = traversalCatalog[stageIndex].focuses[index] ?? 0;
renderSubsteps();                  // NOT renderStages / renderStageOverview
renderStep();
window.scrollTo(scrollX, scrollY);
requestAnimationFrame(() => window.scrollTo(scrollX, scrollY));
```

Two differences from `selectStage`: `visited` is not touched, and scroll position is restored twice
(synchronously and again on the next frame) to defeat the layout shift caused by lab swaps.

### 7.5 Reset helpers

`resetPassLabState()` (L6347–6363) — a state-only reset with **no render**:

```js
stopBoundaryPlay();
passIndex = 0; passNodeIndex = 0; appliedPassThrough = -1;
physicalActionIndex = 0; appliedPhysicalActionThrough = -1;
compilerActionIndex = 0; appliedCompilerActionThrough = -1; compilerExperimentIndex = 0;
boundaryActionIndex = 0; boundaryNodeIndex = 0; boundaryView = "object";
boundaryQuizAnswer = ""; boundaryFailure = "none";
boundaryContextOptions = { timeout:false, crossCluster:true, deferPartialFailures:true, activity:true };
```

`resetExecutionLabState()` (L6213–6217) — `executionActionIndex = 0;
appliedExecutionActionThrough = -1; executionScenarioIndex = 0;`

The user-facing `Reset` buttons wrap these and re-render:
`resetPassLab()` (L6340), `resetPhysicalLab()` (L5609), `resetCompilerLab()` (L5534),
`resetBoundaryLab()` (L6005), `resetExecutionLab()` (L6219).

Note that `resetPassLab()` is narrower than `resetPassLabState()` — it clears only
`passIndex`, `passNodeIndex`, `appliedPassThrough`.

### 7.6 Apply / Execute gating — three different contracts

| Lab | Guard | `disabled` when | Label progression |
|---|---|---|---|
| Pass (`applySelectedPass`, L6334) | `passIndex === appliedPassThrough + 1` | applied ∨ not-next | `Applied ✓` / `Apply pass {n}` / `Apply pass {k} first` |
| Compiler (`applyCompilerAction`, L5528) | `compilerActionIndex === appliedCompilerActionThrough + 1` | applied ∨ not-next | `Applied ✓` / `Apply action {n}` / `Apply action {k} first` |
| Physical (`applyPhysicalAction`, L5603) | `physicalActionIndex === appliedPhysicalActionThrough + 1` | applied ∨ not-next | `Applied ✓` / `Apply action {n}` / `Apply action {k} first` |
| **Execution** (`applyExecutionAction`, L6206) | **none** — `appliedExecutionActionThrough = Math.max(applied, current)` | **never disabled** | `Event executed ✓` / `Execute this event` |
| Boundary | no apply concept | — | `#boundary-play`: `Play` / `Pause` / `Replay` |

Where `k = applied + 2`, i.e. the 1-based index of the next legal action.

The execution lab therefore permits jumping to event 8 and marking it executed without touching
events 1–7, and its heap panel still reflects the *previewed* index. This asymmetry is current
behaviour.

### 7.7 "Apply" is a progress marker, not an accumulator

This is the single most significant semantic finding.

- `renderPassLab` uses `pass.before` / `pass.after` unconditionally (L6271–6273).
- `renderCompilerLab` derives "before" from `actions[i-1].state` (L5433), never from applied state.
- `renderPhysicalLab` does the same (L5556–5559).
- `renderExecutionMemory` folds through `executionActionIndex`, not `appliedExecutionActionThrough`.

**No lab's displayed artifact depends on any `applied*Through` variable.** The observable effects of
Apply are exactly four:

1. the chip gains `.applied` (green, plus `::after` tick on pass and physical chips);
2. the `.pass-mark.applied` ring appears on the optimization-table badges (S5.1 only);
3. the `{k} / {n} applied` counter advances;
4. the button label changes.

The UI copy claims otherwise — `"apply it to advance the cumulative tree"` (pass lab) and
`"Apply commits it to your cumulative progress"` (physical lab). The copy is aspirational; the
rendering is not.

### 7.8 Index clamping

Every renderer clamps its own index into range before use, making all state transitions
self-healing:

| Variable | Clamp site |
|---|---|
| `compilerActionIndex` | L5430 |
| `compilerExperimentIndex` | L5431 |
| `physicalActionIndex` | L5548 |
| `boundaryActionIndex` | L5948 |
| `executionActionIndex` | L6118 |
| `appliedExecutionActionThrough` | L6119 (`Math.min` only) |
| `executionScenarioIndex` | L6120 |
| `passIndex` | L6230 |
| `passNodeIndex` | L6232 |
| `traversalIndex` | L6582 |

### 7.9 Timers

| Timer | Interval | Start | Stop conditions | Rewind |
|---|---|---|---|---|
| `traversalTimer` | **850 ms** (L6645) | `toggleTraversal` | end of `order`; any manual traversal input (L6693/6694/6696); `stopTraversal` from `selectStage`/`selectStep` | if at last index, resets to 0 before playing (L6642) |
| `boundaryTimer` | **1100 ms** (L5993) | `toggleBoundaryPlay` | last action; chip click; prev/next; reset; `resetPassLabState` | same rewind semantics (L5992) |

`stopTraversal()` also resets `#traversal-play` text to `▶`; `toggleTraversal` sets it to `❚❚`.
There is no `setTimeout` anywhere. `requestAnimationFrame` is used 9 times: 8 rail-centring calls and
1 scroll restore.

---

## 8. Source-link subsystem

### 8.1 URL construction

```js
const COMMIT = "e6fd1fd059015c2db443ae044b72f3dfba2d3cf3";                       // L2908
const BASE   = "https://msazure.visualstudio.com/One/_git/Azure-Kusto-Service";   // L2909
const src = (path, line, end) =>                                                  // L2910–2911
  `${BASE}?path=/${path}&version=GC${COMMIT}&line=${line}&lineEnd=${end}` +
  `&lineStartColumn=1&lineEndColumn=200&lineStyle=plain&_a=contents`;
```

Every link in the document is pinned to that single commit. `path` is not URI-encoded; this is safe
only because all shipped paths are ASCII and contain no `&`, `#`, or space.

### 8.2 Label formatting

```js
function codeLocationLabel(url) {                                                  // L3016–3023
  const parsed = new URL(url);
  const path = parsed.searchParams.get("path") || "";
  const file = path.split("/").pop();
  const line = parsed.searchParams.get("line");
  const end  = parsed.searchParams.get("lineEnd");
  return `${file}:${line}${end && end !== line ? `–${end}` : ""} ↗`;
}
```

The range separator is an **en dash (U+2013)**, not a hyphen. When `line === lineEnd`, only the
single line number is shown.

### 8.3 Six link registries

| Registry | Lines | Keyed by | Consumers |
|---|---|---|---|
| `L` | 2913–2944 | 24 semantic aliases (`provider`, `semantic`, `relop`, `remoteLeaf`, `prepare`, `prepPasses`, `catalog`, `optimize`, `generic`, `predist`, `remoting`, `partialEntry`, `partialEval`, `finalOptimize`, `post`, `distribution`, `postSub`, `planCreator`, `planBuilder`, `joinPlan`, `remotePlan`, `serialize`, `managedEntry`, `deserialize`, `cppJoin`, `rustCreate`, `rustNext`, `callback`, `remoteNext`, `managedRemote`) | `stages[].steps[8]` — **which no renderer reads** |
| `preciseLinks[10][…]` | 2948–3014 | `[stage][step]` | `#source-link`, `a.substep-code-link`, and every fallback branch |
| `methodTargets` | 3025–3141 | method-name string | `#call-path` anchors |
| `codeReferences` | 3143–3179 | `{...methodTargets}` + 34 pass/type names | `linkCodeReferences` inline prose linking |
| `treeCodeReferences` | 3181–3224 | operator / node **type** name (44 entries) | `appendTreeLinkedText`; node-kind fallback in the walk tree |
| `treeNodeReferences` | 3226–3263 | traversal **node id** (36 entries) | `a.walk-node-source` |

### 8.4 Two text-linkification engines

#### 8.4.1 Tree linkification

```js
const treeCodeReferencePattern = new RegExp(                                       // L3265–3271
  `(?<![A-Za-z0-9_])(${Object.keys(treeCodeReferences)
      .sort((a, b) => b.length - a.length)          // longest-first — load-bearing
      .map(text => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
      .join("|")})(?![A-Za-z0-9_])`,
  "g");

function appendTreeLinkedText(root, text) {                                        // L3273–3289
  text.split(treeCodeReferencePattern).forEach(part => {
    const target = treeCodeReferences[part];
    if (!target) { root.appendChild(document.createTextNode(part)); return; }
    const link = document.createElement("a");
    link.className = "tree-code-link";
    link.href = target; link.target = "_blank"; link.rel = "noopener noreferrer";
    link.textContent = part;
    link.title = `Open ${codeLocationLabel(target)}`;
    root.appendChild(link);
  });
}

function renderLinkedTreeBlock(element, text) {                                    // L3291–3297
  element.textContent = "";
  text.split("\n").forEach((line, index, lines) => {
    appendTreeLinkedText(element, line);
    if (index < lines.length - 1) element.appendChild(document.createTextNode("\n"));
  });
}
```

Applied to: `#artifact-before`, `#artifact-after`, both pass trees (via `renderPassTree`), every
physical/compiler state pane (via `renderPhysicalState`), the boundary `object` and `json` views,
`#compiler-mapping-grid` cells, and every `<pre>` inside `#physical-plan-deep-dive`.

The `longest-first` sort is essential: without it, `HashJoin` would shadow
`ShardEngineHashJoinIterator`, `Limiter` would shadow `IteratorLimiter`, and so on.

The mechanism relies on `String.prototype.split(regexWithCapturingGroup)` interleaving the captured
delimiters into the result array.

#### 8.4.2 Prose linkification

```js
function linkCodeReferences(root) {                                                // L3307–3340
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (!node.nodeValue.trim() ||
          node.parentElement.closest("a, button, code, pre, script, style")) {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    }
  });
  … split on codeReferencePattern, emit a.inline-code-link, node.replaceWith(fragment)
}
```

Called from `renderStep` over `.stage-overview`, `.step-detail`, `.traversal-card` (L6509–6510), from
`renderPassLab` over `#pass-lab-optimizes`'s parent (L6265), and over `#physical-plan-deep-dive`
(L6283).

**Idempotence** is guaranteed by two facts: generated `<a>` elements are rejected by the walker
filter, and every dynamic text slot is reset with `textContent = …` before re-linking. Static content
inside `.stage-overview` (the `.note`) and the two `<table>` bodies is linkified exactly once and then
protected.

**Exclusions matter:** because `button` is in the reject list, walk-tree node labels are never
linkified; because `code` and `pre` are excluded, the running-example query and all raw JSON stay
plain.

### 8.5 Link hygiene

| Origin | `rel` |
|---|---|
| 7 statically authored anchors | `rel="noopener noreferrer"` |
| `appendTreeLinkedText`, `linkCodeReferences`, `#call-path`, `a.walk-node-source`, `a.substep-code-link` | `rel="noopener noreferrer"` |
| 7 anchors inside boundary-lab `innerHTML` templates (L5769–5770, 5900, 5922–5925) | **`rel="noreferrer"` only** |

All 14 use `target="_blank"`. The `noreferrer`-only cases are functionally equivalent in modern
browsers (`noreferrer` implies `noopener`) but are inconsistent with the rest of the file.

### 8.6 Verified link invariants

1. `preciseLinks` flattens to **45 URLs, all distinct** — no two substeps share a source anchor.
2. Every string in every `step[5]` call path resolves in `methodTargets` — the fallback is dead.
3. Every traversal tree node id resolves in `treeNodeReferences` — the `treeCodeReferences[kind]` and
   `preciseLinks` fallbacks are dead.
4. **Duplicate key defect:** `methodTargets["PassManager.Execute"]` is declared twice —
   L3062 (`RelationalEngine.cs:127–131`) and L3119 (`Common/PassManager.cs:58–88`). The later
   declaration wins. Substep **S4.4** (`3-3`) has `PassManager.Execute` in its call path and therefore
   links to `Common/PassManager.cs`, contradicting `preciseLinks[3][3]`
   (`RelationalEngine.cs:130–147`).

---

## 9. Navigation, keyboard, and accessibility

### 9.1 Statically bound listeners (L6688–6735)

| Group | Elements |
|---|---|
| Stage | `#previous-stage`, `#next-stage` |
| Substep | `#previous-step`, `#next-step`, `#step-slider` (`input`) |
| Traversal | `#traversal-previous`, `#traversal-next-button`, `#traversal-play`, `#traversal-slider` (`input`) — all except play call `stopTraversal()` first |
| Pass | `#pass-reset`, `#pass-previous`, `#pass-next`, `#pass-apply`, `#pass-node-previous`, `#pass-node-next`, `#pass-node-slider` |
| Physical | `#physical-reset`, `#physical-previous`, `#physical-next`, `#physical-apply` |
| Compiler | `#compiler-reset`, `#compiler-previous`, `#compiler-next`, `#compiler-apply` |
| Boundary | `#boundary-reset`, `#boundary-previous`, `#boundary-next`, `#boundary-play` |
| Execution | `#execution-reset`, `#execution-previous`, `#execution-next`, `#execution-apply`, `#execution-slider` |
| Toggles | `#stage-toggle`, `#artifact-toggle` |
| Global | one `document` `keydown` |

Dynamically bound per render: stage buttons, substep buttons, all five chip rails, walk-tree node
buttons, optimization table rows, compiler experiment buttons, execution scenario buttons, boundary
node-picker / view-tab / failure / quiz buttons, and the four boundary context checkboxes.

Total `addEventListener` call sites: 52.

### 9.2 Keyboard contract

```js
document.addEventListener("keydown", event => {                                    // L6723–6735
  if (event.target.matches("input, button")) return;
  if (event.key === "ArrowLeft")  selectStep(stepIndex - 1);
  if (event.key === "ArrowRight") selectStep(stepIndex + 1);
  if (event.key === "ArrowUp")   { event.preventDefault(); selectStage(stageIndex - 1); }
  if (event.key === "ArrowDown") { event.preventDefault(); selectStage(stageIndex + 1); }
});
```

Behavioural consequences, all current:

- **The bail-out disables arrow navigation after the first click.** Every interactive control in the
  page is an `<input>` or a `<button>`, and none of them blur on activation, so once the user clicks
  anything the guard short-circuits permanently until focus returns to `<body>`.
  The on-screen hint `"Use buttons, slider, or ←/→ keys"` (L2184) is therefore accurate only before
  the first interaction. **CAVEAT** — a narrower guard (`matches("input[type=range], input:not([type=range])")`
  or checking `event.target.closest("input")` only for sliders) would restore it.
- `ArrowLeft` / `ArrowRight` are **not** `preventDefault`ed, so they can additionally scroll a focused
  overflow container.
- `ArrowUp` / `ArrowDown` **are** `preventDefault`ed, suppressing vertical page scroll while
  navigating stages.
- No `Home`, `End`, `PageUp`, `PageDown`, `Escape`, `Space`, `Enter`, or number-key handling.

### 9.3 ARIA and semantics inventory

| Attribute | Count | Where |
|---|---|---|
| `aria-label` | 24 | `#network-beacon`, all six `nav` rails, all four `input[type=range]`, every `a.walk-node-source` |
| `aria-labelledby` | 9 | each `<section>` → its heading id |
| `aria-live="polite"` | 1 | `#network-beacon` only |
| `aria-expanded` | 4 | `#stage-toggle`, `#artifact-toggle` (static + JS-maintained) |
| `aria-controls` | 2 | `#stage-toggle → stage-overview-body`, `#artifact-toggle → artifact-body` |
| `role=` | **0** | — |
| `tabindex` | **0** | — |
| `alt=` | 0 | no images exist |
| `hidden` | 1 attribute | `details#physical-plan-deep-dive` |

Focus affordance is a single global rule: `:focus-visible { outline: 3px solid var(--amber);
outline-offset: 2px }` (L130–133). Disabled buttons use `cursor: not-allowed; opacity: .42` (L129).

Known accessibility gaps (current behaviour):

- No `aria-selected` or `aria-current` on any rail; selection is conveyed by colour and by the
  `title` attribute only.
- Range inputs have `aria-label` but no `aria-valuetext`, so a screen reader announces bare integers.
- Progress counters (`{k} / {n} applied`), `#pass-walk-status`, `#boundary-stage-status`,
  `#execution-progress` and the quiz result are **not** in live regions; the only `aria-live` region
  is the network beacon.
- Chip accessible names are just the ordinal number; the descriptive text lives in `title`.
- `#pass-rail` is the only element whose `aria-label` is updated at runtime (L6239).

---

## 10. Styling tokens and layout rules

### 10.1 Design tokens (`:root`, L8–23)

```css
--bg:       #07101d
--surface:  #101c2d      /* DECLARED BUT NEVER USED */
--surface2: #15253b
--surface3: #0b1727
--line:     #2a405d
--ink:      #f2f7ff
--muted:    #9eb2ca
--blue:     #54b9ff
--cyan:     #4fe0d0
--green:    #75dc8e
--amber:    #ffc766
--purple:   #bd94ff
--pink:     #ff8caf
--shadow:   0 18px 48px rgba(0,0,0,.28)
```

`body` (L26–36): `margin:0; min-height:100vh; padding-bottom:150px;` — the bottom padding reserves
space for the fixed beacon — with a layered background:

```css
radial-gradient(circle at 8% -5%, rgba(84,185,255,.18), transparent 33rem),
radial-gradient(circle at 95% 5%, rgba(189,148,255,.13), transparent 31rem),
var(--bg)
```

`* { box-sizing: border-box }` (L24) and `html { scroll-behavior: smooth }` (L25) are global.

**`--text` is referenced but never declared.** Four rules use it and therefore fall back to inherited
colour: `.execution-stack-frame b` (L859), `.execution-heap-object strong` (L896),
`.execution-component b` (L955), `.boundary-toggle b` (L1301).

### 10.2 Semantic colour language

| Meaning | Token |
|---|---|
| managed / C# / informational headings | `--blue` |
| structural headings, "walk" badges, pass-lab accent | `--cyan` |
| additive diff, applied state, "changes tree", Rust | `--green` |
| current traversal node, "change" badges, experiments/scenarios | `--amber` |
| boundary / interop / ownership | `--purple` |
| runtime execution, active network, incorrect answers | `--pink` |
| removed diff | `#ff6b6b` on `rgba(255,92,92,.2)`, text `#ffc4c4` |
| code surfaces | `#d9ecff` on `#081321` / `#07131f` / `#050f19` |

Lab identity: compiler-`syntax` blue · compiler-`semantic` purple · compiler-`relop` green ·
pass-lab cyan · physical-lab blue · boundary-lab purple · execution-lab pink.

### 10.3 Workspace grid

```css
.workspace {                                   /* L239–243 */
  display: grid;
  grid-template-columns: minmax(300px,.72fr) minmax(560px,1.45fr) minmax(300px,.75fr);
  gap: 12px;
  align-items: start;
}
.workspace.artifact-collapsed            { minmax(300px,.72fr) minmax(560px,1.45fr) 54px }
.workspace.stage-collapsed               { 54px minmax(560px,1.45fr) minmax(300px,.75fr) }
.workspace.stage-collapsed.artifact-collapsed { 54px minmax(560px,1.45fr) 54px }
```

`.shell { width: min(1580px, calc(100% - 26px)); margin: 13px auto 50px }` (L139–142).

`.card { border:1px solid var(--line); border-radius:14px; background: rgba(16,28,45,.96);
box-shadow: var(--shadow) }` (L254–259).

`.stage-overview, .artifact-card { position: sticky; top: 12px; padding: 18px }` (L260–264).

`.center { display: grid; gap: 12px }` (L335–338) — **no `grid-template-columns`**, which is the root
of the layout behaviour analysed in §15.

### 10.4 Diff and state line styling

Applied per-line to `<span>` elements inside `<pre>`:

| Class | Style |
|---|---|
| `.diff-removed` | `display:inline-block; width:100%; border-radius:3px; color:#ffc4c4; background: rgba(255,92,92,.2); border-left: 4px solid #ff6b6b` |
| `.diff-added` | same box, `color:#caffd5; background: rgba(117,220,142,.2); border-left: 4px solid var(--green)` |
| `.active-line` (pass trees only) | `outline: 2px solid var(--amber); outline-offset: -2px; border-radius:3px` |
| `.complete` (physical/compiler panes) | `color: var(--green)` — line contains `[✓]` |
| `.pending` | `color: var(--muted)` — line contains `[ ]` |
| `.current` | `display:inline-block; width:100%; color:#fff0b8; background: rgba(255,191,71,.16); border-left: 4px solid var(--amber)` |

`renderPhysicalState` state detection (L5414–5416) is deliberately asymmetric:

```js
if (line.includes("[✓]")) span.className = "complete";
else if (line.includes("[ ]")) span.className = "pending";
else if (line.trim().startsWith("→") || line.startsWith("READY:") || line.startsWith("RETURN"))
  span.className = "current";
```

`→` is matched after `trim()`; `READY:` and `RETURN` only at column 0.

`.diff-removed .tree-code-link, .diff-added .tree-code-link, .active-line .tree-code-link
{ color: inherit }` (L1476–1478) prevents link colour from fighting the diff colour.

### 10.5 LCS line diff

```js
function treeLineDiff(beforeTree, afterTree) {                                     // L5369–5395
  const before = beforeTree.split("\n");
  const after  = afterTree.split("\n");
  // (m+1)×(n+1) DP table filled backwards
  // forward walk emitting unchangedBefore / unchangedAfter index Sets
  // tie-break: lengths[i+1][j] >= lengths[i][j+1] ⇒ advance i (biases toward "removed")
  return { unchangedBefore, unchangedAfter };
}
```

Line-granular only; there is no intra-line diffing. Complexity `O(m·n)` on trees of ≤30 lines.

### 10.6 Fixed panel dimensions

| Selector | Constraint |
|---|---|
| `.compiler-state` | `min-height:220px; max-height:410px` |
| `.boundary-code` | `min-height:245px; max-height:440px` |
| `.physical-state-panel pre` | `min-height:235px` |
| `.pass-tree-panel pre` | `min-height:292px` |
| `.execution-stack`, `.execution-heap` | `min-height:305px` |
| `.walk-tree` | `min-height:430px` |
| `.physical-fidelity-panel pre` | `max-height:560px` |
| `.physical-raw pre` | `max-height:600px` |
| `details.example pre` | `max-height:320px` |
| `.boundary-lane` | `min-height:82px` |
| `.detail-box` | `min-height:120px` |
| `.stage-button` | `min-height:91px` |
| `.substep`, `.substep-card` | `min-width:155px`; `.substep-card` also `max-width:205px` |
| `.walk-node` | `min-width:285px` |
| `.context-table` | `min-width:760px` |
| `.pass-chip` | `36×32px` |
| `.compiler-action-chip` | `min-width:36px` |
| `.physical-action-chip`, `.execution-action-chip` | `min-width:38px` |

### 10.7 Auto-scroll helper

```js
function scrollChildOnAxis(container, child, axis) {                               // L5337–5351
  if (!container || !child) return;
  const horizontal = axis === "x";
  // centre `child` inside `container` using getBoundingClientRect deltas
  const target = current + childStart - containerStart - (containerSize - childSize) / 2;
  container.scrollTo(horizontal
    ? { left: Math.max(0, target), behavior: "smooth" }
    : { top:  Math.max(0, target), behavior: "smooth" });
}
```

Invoked (always inside `requestAnimationFrame`) for `#stage-strip`, `#substep-strip`, `#pass-rail`,
`#compiler-action-rail`, `#physical-action-rail`, `#boundary-action-rail`,
`#execution-action-rail` on the `"x"` axis, and for `#walk-tree` on the `"y"` axis — the latter only
when `walkTree.scrollHeight > walkTree.clientHeight`.

---

## 11. Responsive and print behaviour

### 11.1 Breakpoints

| Query | Lines | Effect |
|---|---|---|
| `max-width: 1180px` | 2074–2084 | `.workspace` → 2 columns `minmax(280px,.7fr) minmax(500px,1.3fr)`; `.artifact-collapsed` uses the **same** template (collapse no longer shrinks a column); `.stage-collapsed` (both variants) → `54px minmax(500px,1fr)`; `.artifact-card { position: static; grid-column: 1 / -1 }`; `.artifact-card.collapsed { justify-self: end }` |
| `max-width: 850px` | 1719–1730 | Single-column: `.pass-tree-grid`, `.physical-state-grid`, `.physical-fidelity-grid`, `.compiler-workspace`, `.execution-runtime-grid`, `.execution-ownership`, `.boundary-workspace`, `.boundary-lanes`, `.pass-lab-summary`. `.execution-components` → `repeat(3, minmax(0,1fr))` |
| `max-width: 820px` | 2085–2098 | `header { flex-direction: column }`; `.workspace` → `1fr` in **all four** variants; `.stage-overview { position: static }` and `.collapsed { justify-self: end }`; `.detail-grid`, `.traversal-layout`, `.substep-tree-summary` → `1fr`; `.substep-tree-summary p { padding-left: 0 }`; `.artifact-card { grid-column: auto }` |
| `max-width: 520px` | 2099–2112 | `.shell { width: calc(100% - 12px) }`; `.stage-nav`, `.walk-controls` → `1fr`; `.level-key { min-width: 0 }`; `.execution-language-lanes`, `.execution-effects`, `.execution-heap`, `.execution-components` → `1fr`; beacon → `right:7px; bottom:7px; width: calc(100vw - 14px)` |

The 850px block is authored between other rules in source order but has no cascade conflict, because
its selectors are disjoint from those in the 820px and 1180px blocks.

### 11.2 Print

```css
@media print {                                                                     /* L2113–2123 */
  body { background: #fff; color: #000; }
  .shell { width: 100%; }
  .card, header, .level-one { background: #fff; border-color: #bbb; box-shadow: none; }
  .stage-overview, .artifact-card { position: static; }
  button, input { display: none; }
}
```

Current print output, stated as behaviour rather than as a defect:

1. **`button, input { display: none }` removes every control.** That includes the whole
   `#stage-strip` (10 buttons), the whole `#substep-strip` (45 buttons across stages), every chip
   rail, every experiment / scenario / view-tab / failure / quiz button, all four sliders, and
   both collapse toggles.
2. **The entire `#walk-tree` disappears**, because each traversal node is a `<button>`. Only the
   `a.walk-node-source` `↗` anchors and the CSS connector lines survive, leaving an orphaned skeleton.
3. Only the **currently visible** lab prints; the other four remain `display: none`.
4. `color: #000` is set on `body` only. Every descendant rule still specifies light-on-dark values
   (`--muted`, `--ink`, `#d9ecff`), and dark `<pre>` backgrounds (`#081321`, `#07131f`, `#050f19`,
   `#122238`) are **not** reset — code panes print as dark blocks with light text.
5. `.network-beacon` retains `position: fixed` and its dark background.
6. There is no `page-break-before/after/inside` control anywhere in the stylesheet.

**CAVEAT** — a print-fit variant would need: a `button` allowlist (or `.walk-node { display:block }`),
a light-mode override for `pre` and the `--muted`/`--ink` tokens, un-hiding all five labs, and
`break-inside: avoid` on `.card`.

---

## 12. Empty, no-op, disabled, and error states

| Condition | Rendered behaviour |
|---|---|
| Substep with no lab (S4.1, S4.4, S6.1, S6.2) | All five renderers early-return. **No placeholder, message, or disabled shell is shown**; the substep chip also carries no runner badge |
| Compiler lab hidden | `className` reset to bare `"compiler-lab"` — the `kind` class is dropped, not merely the `visible` class |
| Other labs hidden | `.visible` removed; container stays `display: none` |
| Empty heap zone | `<p class="execution-stack-empty">Nothing allocated in this zone yet.</p>` |
| No context diff | `"No request-scoped differences."` |
| Quiz unanswered | `"Choose an answer."`, `className = ""` |
| Boundary lane with no reached action | `"Ready at the managed query-plan boundary."` (C#) / `"Waiting for the payload."` (Interop, C++) |
| Traversal at final index | `#traversal-next` → `"Traversal complete; return the resulting root/artifact."` |
| First / last index in any rail | prev / next `disabled` — stage, step, pass, pass-node, physical, compiler, boundary, execution, traversal |
| Apply already performed | `disabled` + `Applied ✓` |
| Apply out of sequence | `disabled` + `Apply pass|action {k} first` |
| Execute (execution lab) | **never disabled**; label toggles to `Event executed ✓` |
| Hex view beyond 192 bytes | `… {n} more bytes` |
| `mappings` present but option ≠ `"map"` | `#compiler-mapping-grid` emptied |
| Beacon before first render | Static `none` state pre-rendered in HTML, immediately overwritten |

**There is no genuine error path.** The file contains no `try` / `catch`, no user-input validation,
and no failure surface. The "failure injection" of `8-2`, the compiler "experiments", and the
execution "scenarios" are all descriptive text lookups against static data.

---

## 13. Persistence

**There is none.**

Verified zero occurrences of: `localStorage`, `sessionStorage`, `indexedDB`, `document.cookie`,
`history.pushState` / `replaceState`, `location.hash`, `URLSearchParams` on the page's own URL, or any
other state-serialisation mechanism.

Every reload restores the full initial state:

```
stageIndex = 0, stepIndex = 0, traversalIndex = traversalCatalog[0].focuses[0] = 0
visited = { 0 }
stage-overview expanded, artifact-card expanded
all applied*Through = -1, all *Index = 0
boundaryView = "object", boundaryFailure = "none", boundaryQuizAnswer = ""
boundaryContextOptions = { timeout:false, crossCluster:true,
                           deferPartialFailures:true, activity:true }
```

Deep-linking to a stage or substep is impossible; the URL never changes.

---

## 14. Data schemas and invariants

### 14.1 `stages[i]`

```ts
Stage = {
  short:   string,   // stage-strip .name
  kind:    string,   // stage-strip .kind and #stage-badge suffix
  title:   string,   // #stage-title
  purpose: string,   // #stage-purpose
  input:   string,   // #stage-input
  output:  string,   // #stage-output
  owner:   string,   // #stage-owner
  not:     string,   // #stage-not
  handoff: string,   // #stage-handoff
  steps:   Array<Step>
}
```

### 14.2 `Step` — a positional 9-tuple

**Verified: arity is exactly 9 for all 45 substeps.**

| Index | Meaning | Consumer |
|---|---|---|
| `[0]` | title | `#step-title`, `.substep b`, physical/boundary lab headings |
| `[1]` | summary / action | `#step-summary` **and** `#step-action` (rendered twice) |
| `[2]` | why | `#step-why` |
| `[3]` | observe | `#step-observe` |
| `[4]` | next | `#step-next` |
| `[5]` | `string[]` call path | `#call-path`, keys into `methodTargets` |
| `[6]` | artifact before | `#artifact-before`, linkified |
| `[7]` | artifact after | `#artifact-after`, linkified |
| `[8]` | an `L.*` URL | **never read by any renderer — dead field** |

### 14.3 `traversalCatalog[i]`

```ts
TraversalDefinition = {
  mode:     string,       // #traversal-mode pill
  summary:  string,       // #traversal-summary
  movement: string,       // "How Visit moves"
  unwind:   string,       // "Return / unwind"
  tree:     TreeNode,     // shared across stages
  order:    string[],     // visit sequence of node ids, may repeat
  focuses:  number[]      // one entry per substep: initial traversalIndex
}
TreeNode = { id: string, kind: string, name: string, children: TreeNode[] }   // built by T()
```

Four shared trees:

| Tree | Root id | Used by stages | Nodes |
|---|---|---|---|
| `languageTree` (L4735–4754) | `script` | 1, 2, 3 | script, take10, finalProject, join, localProject, localTake, telemetry, remoteProject, remoteTake, where, trips |
| `relopTree` (L4756–4775) | `limiter` | 4, 5, 6, 7, 8 | limiter, projection, innerJoin, leftProjection, leftLimiter, localTable, remoteQuery, rightProjection, rightLimiter, selection, remoteTable |
| `physicalTree` (L4777–4786) | `topnNode` | 9 | topnNode, projectorNode, hashJoinNode, localIterator, remoteNode, remoteKql |
| `executionTree` (L4788–4801) | `resultPull` | 10 | resultPull, cppJoin, rustJoin, buildPull, probePull, callbackNode, remoteIterator, managedTransport |

**Verified invariants:**
- Every id appearing in `order` exists in the corresponding `tree` — all 10 stages.
- Every node in every `tree` appears at least once in its `order` — no orphaned or unreachable nodes.
- `focuses.length === steps.length` for all 10 stages.

**Focus anomalies (current behaviour):**
- `traversalCatalog[1].focuses = [0, 6, 10, 15, 18]` but `order.length === 18`, so `focuses[4] = 18`
  is out of range. `selectStep(4)` assigns `traversalIndex = 18`; `renderTraversal` clamps it to 17
  at L6582. **S2.5 therefore opens on the final `script` unwind visit** — likely the intent, expressed
  as an off-by-one.
- Non-monotonic focus sequences are intentional and appear in stage 1 `[0,0,5,10]`,
  stage 5 `[0,9,9,16,20]`, stage 6 `[0,13,5,10]`, and stage 7 `[0,10,0,14,17]`.

### 14.4 `treeBehaviors[i][j]` — a 3-tuple

`[walkLabel, changeLabel, detail]` → `#substep-walk`, `#substep-change`, `#substep-tree-detail`, and
(for the first two) the `.substep-behavior` badges.

### 14.5 `networkOverrides` / `stageNetworkDefaults`

```ts
networkOverrides:      Record<`${i}-${j}`, Partial<{state, label, route, purpose}>>
stageNetworkDefaults:  Array<[state, label, route, purpose]>   // length 10, all fields required
```

### 14.6 Lab schema divergence

Field naming is **not** unified across the five runner families. A reimplementation must either
preserve the divergence or normalise it deliberately.

| Family | Title field | State field | Other required fields |
|---|---|---|---|
| Compiler | `title` | `state` | `kind`, `heading`, `badge`, `intro`, `initial`, `experiment` |
| Physical | **`name`** | `state` | `mode`, `intro`, `inputLabel`, `input`, `outputLabel`, `initial` |
| Boundary | `title` | — | `badge`, `intro`, `lane` per action |
| Execution | `title` | — | `lang`, `why`, `stack`, `stackEffect`, `heapEffect`, `memory`, `active`, `live`, `pull`, `ownership`, `breakpoint`; lab-level `heading`, `intro`, `base`, `scenarios` |
| Pass | **`name`** | `before` / `after` | `changes`, `walk`, `rule`, `optimizes`, `source` |

### 14.7 Duplicate-key audit

Object-literal key collisions were checked across all six registries and `passPurpose`:

| Object | Result |
|---|---|
| `methodTargets` | **1 collision** — `"PassManager.Execute"` at L3062 and L3119 |
| `codeReferences` (own additions) | none |
| `treeCodeReferences` | none |
| `treeNodeReferences` | none |
| `passPurpose` | none |

## 15. Live-browser layout measurements

All figures in this section are **measured**, not predicted. The measurement environment is a
Chromium 152 layout engine with device metrics overridden to the stated width, height, and device
scale factor; values are read from `getBoundingClientRect()`, `getComputedStyle()`,
`document.documentElement.clientWidth/scrollWidth`, and `document.elementFromPoint()`. They describe
**current behaviour**, not intent.

### 15.1 Summary of the finding

At the canonical viewport, the centre column's implicit grid column is **wider than the workspace
track that contains it**. The overflowing content extends to the right, underneath the sticky
artifact card, which — being a positioned element — paints on top of it. This is visible in the
canonical screenshot and is reproducible.

Reference figures at 1280×720, DPR 1.25, default state (Stage 1, substep 1):

| Metric | Value |
|---|---|
| `.center` computed `grid-template-columns` | **674.6px** |
| `#substep-strip` width | **641px** |
| `.center` border-box width | 602.92px (equal to the workspace track) |
| Overflow past `.center` | **71.68px** |
| Horizontal overlap of `.artifact-card` | **59.68px** |

### 15.2 Workspace track sizing, and environment variance

```
avail  = document.documentElement.clientWidth        // viewport minus classic scrollbar
shell  = min(1580px, avail − 26px)                   // .shell, L139–142
free   = shell − 2 × 12px                            // .workspace gap, L242
t1raw  = free × 0.72 / 2.92
if (t1raw < 300) {                                   // minmax(300px, .72fr) floor binds
  t1 = 300px
  t2 = (free − 300) × 1.45 / 2.20
  t3 = (free − 300) × 0.75 / 2.20
} else {
  t1 = free × 0.72 / 2.92
  t2 = free × 1.45 / 2.92
  t3 = free × 0.75 / 2.92
}
```

Two observed instantiations of the same rule:

| Environment | `avail` | Scrollbar | Computed `grid-template-columns` | Floor binds? |
|---|---|---|---|---|
| Physical display, DPR 1.25 | 1268 | 12 CSS px (15 device ÷ 1.25) | `300.33px 604.79px 312.88px` | no (`t1raw = 300.33 ≥ 300`) |
| Chromium 152, DPR 1.25, `clientWidth` 1265 | 1265 | 15 CSS px | `300px 602.925px 311.875px` | **yes** (`t1raw = 299.53 < 300`) |

The ~2px divergence between the two is entirely attributable to scrollbar width. **The `.center`
implicit column (674.6px) and `#substep-strip` (641px) are byte-identical in both**, because both are
min-content-derived and therefore independent of available width.

### 15.3 The overflow chain

Measured box geometry at 1280×720 / DPR 1.25 / Stage 1 substep 1:

| Box | left | width | right |
|---|---|---|---|
| `.shell` | 13 | 1238.8 | 1251.8 |
| `#workspace` | 13 | 1238.8 | 1251.8 |
| `.stage-overview` (sticky) | 13 | 300 | 313 |
| **`.center` border box** | **325** | **602.92** | **927.92** |
| **`.center` implicit column** | — | **674.60** | — |
| `.level-two` / `.step-detail` / `.call-card` / `.traversal-card` | 325 | **674.60** | **999.60** |
| `#substep-strip` | 341.8 | **641.00** | 982.8 |
| `.artifact-card` (sticky) | **939.92** | 311.88 | 1251.8 |

Mechanism, step by step:

1. `.center { display: grid; gap: 12px }` (L335–338) declares **no `grid-template-columns`**. It
   therefore has a single implicit column, sized to the largest **min-content contribution** among
   its visible children.
2. `.center`'s own border box remains pinned at the workspace track width (602.92px), but the
   implicit column resolves to 674.60px. `.center` has `overflow: visible`, so the column — and the
   `.card` children stretched to it — overflow the box to the right by **71.68px**.
3. Children therefore terminate at `x = 999.60`, while `.artifact-card` begins at `x = 939.92`,
   producing **59.68px of horizontal overlap**.
4. `.artifact-card` is `position: sticky` with `z-index: auto`. A positioned box paints after
   non-positioned in-flow block descendants, so it covers the intruding content. Its background is
   `rgba(16,28,45,.96)` — 96 % opaque — plus `box-shadow: 0 18px 48px rgba(0,0,0,.28)`, so the
   intruding content is faintly visible through it and under the shadow, exactly as the screenshot
   shows.

### 15.4 The min-content amplifiers

**Correction to the naïve reading of §10:** `overflow-x: auto` does *not* universally zero a box's
min-content contribution. It zeroes the **automatic minimum size** of **flex/grid *items*** only. A
block-level scroll container that is an ordinary normal-flow child of a block container still
propagates its full intrinsic min-content width. Three boxes in this file rely on the block path and
therefore amplify:

| Amplifier | Container context | Formula | Measured |
|---|---|---|---|
| `nav#substep-strip` (flex, `overflow-x:auto`, L340–346) — child of the block `.level-two` | block | `Σ card min-content + 7px × (n−1)`; card floor `min-width: 155px` (L352, L359) | 4 cards → **641**; `+32px` padding `+2px` border → **674.6** |
| `nav#pass-rail` (flex, `overflow-x:auto`, L1600–1605) — child of the block `.pass-lab` | block | `36px × n + 6px × (n−1) + 4px`, then `+32px` lab padding/border | 22 chips → **953.6**; 23 → **995.6**; 29 → **1247.6** |
| `.context-table-wrap` (`overflow-x:auto`, L503–507) wrapping `.context-table { min-width: 760px }` (L510) — child of the block `.additional-context` | block | `760 + 2 + 40 + 2` | **803.2** |

By contrast, `.walk-tree` (`overflow: auto`, containing `.walk-node { min-width: 285px }`) contributes
**0**, because it *is* a grid item of `.traversal-layout`; its automatic minimum size is zeroed and
the explicit track floor `minmax(330px, 1.15fr)` governs instead. A fourth, non-scrolling amplifier is
`.boundary-workspace { minmax(320px,.9fr) minmax(390px,1.1fr); gap:10px }` → `720 + 34 = 754`.

Direct consequence: **the substep rail and the pass rail never actually scroll horizontally at any of
these widths — they widen the page instead.** Their `overflow-x: auto` is defeated by the containing
block's intrinsic sizing.

### 15.5 Per-substep intrusion, 1280×720 / DPR 1.25

`.center` track = 602.92px; `.artifact-card` left edge = 939.92px.

| Substeps | `.center` implicit column | Overflow past `.center` | Overlap of `.artifact-card` | min-content driver | Horizontal document scrollbar |
|---|---|---|---|---|---|
| S1.1–S1.4, S3.1–S3.4, S4.1, S4.3, S4.4, S6.1, S6.2, S6.4 | **674.6** | 71.7 | 59.7 | `.level-two` — 4 substep cards | no |
| S2.1–S2.5, S7.2–S7.5, S8.1–S8.5 | **836.6** | 233.7 | 221.7 | `.level-two` — 5 substep cards | no |
| S9.1–S9.3 | **753.6** | 150.7 | 138.7 | `.boundary-lab` — `.boundary-workspace` floors | no |
| S4.2 | **803.2** | 200.3 | 188.3 | `.step-detail` — `.context-table { min-width: 760px }` | no |
| S5.2–S5.5 | **858.7** | 255.8 | 243.8 | `.level-two` — 5 cards, badges exceeding the 155px floor | no |
| S10.1–S10.6 | **998.6** | 395.7 | 383.7 | `.level-two` — 6 substep cards | **yes** (`scrollWidth` 1324) |
| **S5.1** | **953.6** | 350.7 | 338.7 | `.pass-lab` — 22 pass chips | **yes** (1278) |
| **S7.1** | **995.6** | 392.7 | 380.7 | `.pass-lab` — 23 pass chips | **yes** (1321) |
| **S6.3** | **1247.6** | 644.7 | 632.7 | `.pass-lab` — **29** pass chips | **yes** (1573) |

**S6.3 is the worst case in the document.** A horizontal document scrollbar is present on **12 of the
45 substeps** at 1280px.

Both reference figures reported for the canonical page (674.6 and 641) correspond to the **default
Stage 1 substep 1** state. The screenshot showing Stage 5 selected corresponds to the 953.6 / 338.7
row. Both are canonical; the intrusion is stage- and substep-dependent and varies by more than an
order of magnitude across the 45 substeps.

### 15.6 The overlap is not resolvable by widening the viewport

`.shell` is capped at `min(1580px, …)`, so the centre track is capped at
`(1580 − 24) × 1.45 / 2.92 = **772.7px**`. Measured identically at 1920px and 3840px:

| Substep | Centre track (capped) | `.center` min-content | Residual overflow | Residual overlap |
|---|---|---|---|---|
| S1.1 | 772.7 | 674.6 | **0** | **0** |
| S5.1 | 772.7 | 953.6 | 180.9 | 168.9 |
| S10.1 | 772.7 | 998.6 | 225.9 | 213.9 |
| S6.3 | 772.7 | 1247.6 | 474.9 | 462.9 |

**Any substep whose `.center` min-content exceeds 772.7px overlaps the artifact card at every
viewport width — 31 of the 45 substeps.** Only the 674.6px group clears it (from `avail ≳ 1418px`)
and the 753.6px group (from `avail ≳ 1560px`).

### 15.7 Breakpoint sweep (Stage 5 substep 1, DPR 1.25)

| Viewport | `avail` | `#workspace` columns | `.center` box | `.center` column | `.artifact-card` | `document.scrollWidth` |
|---|---|---|---|---|---|---|
| 1600 | 1585 | `378.4 762.2 394.2` | 762.15 | 953.6 | sticky | 1585 |
| 1400 | 1385 | `329.1 662.8 342.9` | 662.83 | 953.6 | sticky | 1385 |
| 1281 | 1266 | `300 604.0 312.4` | 603.99 | 953.6 | sticky | **1278** |
| **1280** | **1265** | **`300 602.925 311.875`** | **602.92** | **953.6** | sticky | **1278** |
| 1200 | 1185 | `300 560 300` — all three floors bind | 560 | 953.6 | sticky | 1278 |
| 1181 | 1166 | `300 560 300` | 560 | 953.6 | sticky | 1278 |
| **1180** | 1165 | `394.4 732.4` — media query fires | 732.42 | 953.6 | **static**, `grid-column: 1/-1` | 1373 |
| 1100 | 1085 | `366.4 680.4` | 680.42 | 953.6 | static | 1345 |
| 900 | 885 | `296.4 550.4` | 550.42 | 953.6 | static | 1275 |
| 821 | 806 | `280 500` — floors bind | 500 | 953.6 | static | 1258 |
| **820** | 805 | **`953.6px`** — 1-col media query; the single `1fr` resolves to min-content | 953.6 | 953.6 | static | 966 |
| 700 | 685 | `953.6px` | 953.6 | 953.6 | static | 966 |
| 600 | 585 | `953.6px` | 953.6 | 953.6 | static | 966 |
| 521 | 506 | `953.6px` | 953.6 | 953.6 | static | 966 |
| 520 | 505 | `953.6px` | 953.6 | 953.6 | static (`.shell` inset 6px) | 960 |
| 420 | 405 | `953.6px` | 953.6 | 953.6 | static | 960 |

Two further, independent overflow behaviours surfaced by the sweep:

1. **`avail` ≈ 1166–1215px:** all three `minmax` floors bind simultaneously
   (`300 + 560 + 300 + 24 = 1184px`) while `.shell` is only ~1140–1189px wide. **`#workspace` itself
   overflows `.shell`**, independently of the `.center` issue.
2. **Viewport ≤ 820px:** `.workspace { grid-template-columns: 1fr }` (L2087). A single `1fr` track
   floors at `auto`, i.e. min-content, so the workspace becomes **953.6px wide inside an 805px
   shell**. The whole document scrolls horizontally.

A horizontal document scrollbar is present at every tested width from 1280px down to 420px on
Stage 5 substep 1.

### 15.8 Occlusion and hit-testing

`document.elementFromPoint` inside the overlap band at 1280×720, Stage 5 substep 1:

| Point | Topmost element | Inside `.artifact-card` |
|---|---|---|
| (1000, 420) | `p.artifact-status` | yes |
| (1100, 500) | `pre` (artifact before/after) | yes |
| (1240, 600) | `aside.network-beacon` | no — the fixed beacon (`z-index: 100`) wins |
| (950, 300) | `nav.stage-strip` | no — above the workspace |

**The intruding `.center` content in the overlap band is neither readable nor clickable.** Every hit
test in the band resolves to the artifact card. Concretely, the right-hand 59.7px–632.7px of
`#substep-strip`, `.walk-controls`, `.detail-grid`, `#pass-rail`, `.pass-tree-grid`,
`.boundary-workspace` and the `a.substep-code-link` anchors are inert wherever they pass beneath the
artifact column.

Collapsing the artifact card via `#artifact-toggle` shrinks its track to 54px and recovers most — but
not all — of the band.

### 15.9 CAVEAT and candidate remediations

This section is the only part of §15 that is advisory rather than descriptive.

The behaviour above should be recorded in any reimplementation brief as a **known layout caveat**.
Minimal, surgical changes that would remove it while preserving all other documented behaviour, each
verifiable against the table in §15.5:

1. `.center { min-width: 0 }` — or `grid-template-columns: minmax(0, 1fr)` — so the implicit column
   can shrink below its content's min-content size.
2. `min-width: 0` on `.level-two`, `.pass-lab`, `.step-detail`, and `.boundary-lab`.
3. Wrap `#substep-strip` and `#pass-rail` in an explicitly `min-width: 0` grid item so their
   `overflow-x: auto` actually engages and the rails scroll as designed.
4. Raise or remove the `.shell` 1580px cap if the intent is for very wide viewports to resolve the
   overlap naturally.

Options 1–3 are behaviour-preserving for every other measurement in this document. Option 4 alters
`.shell` geometry at all widths and is therefore not equivalent.

---

## 16. Runner coverage — canonical matrix and omissions

Runner *absence* at four substeps and the mid-stage family switch at Stage 8 are **canonical data
facts**, not rendering failures. This section records them explicitly, in the 1-based numbering the
UI displays.

### 16.1 Substeps that render no specialized runner

| Display | Internal key | Substep title | What renders instead |
|---|---|---|---|
| **Stage 4, substep 1** | `3-0` | *Create preparation PassManager* | stage overview · substep rail · step detail · method path · traversal card · artifact card |
| **Stage 4, substep 4** | `3-3` | *Return prepared Relop* | ″ |
| **Stage 6, substep 1** | `5-0` | *Collect partial-query operators* | ″ |
| **Stage 6, substep 2** | `5-1` | *Take the no-op path for this query* | ″ |

Mechanics at these four substeps:

- All five lab containers evaluate to `display: none`.
- `renderStep` still calls all five renderers (L6504–6508); each returns early on a `null` config.
- **No placeholder, explanatory message, or disabled shell is presented.** The lab section is simply
  absent from the flow.
- The corresponding chip in `#substep-strip` carries **no runner-count badge**, because
  `renderSubsteps` emits the empty string when no lab key matches (L6438).
- Every other region (network beacon, traversal card, artifact card, call path, detail grid) behaves
  exactly as at any other substep.

These four omissions are semantically coherent with the content: `3-0` and `3-3` are pure
construction/packaging steps around a `PassManager`, and `5-0`/`5-1` are the collector scan and its
empty-result no-op — none of which has a pass queue, an action sequence, or a runtime timeline to
step through.

### 16.2 Stage 8 is the only stage that switches runner family mid-stage

| Display | Internal key | Runner family | Dimensions |
|---|---|---|---|
| Stage 8, substep 1 | `7-0` | **physical-lab** | 5 actions · mode `CONTEXT ASSEMBLY` |
| Stage 8, substep 2 | `7-1` | **physical-lab** | 8 actions · mode `VISITOR + UNWIND` |
| Stage 8, substep 3 | `7-2` | **physical-lab** | 7 actions · mode `JOIN ASSEMBLY` |
| Stage 8, substep 4 | `7-3` | **physical-lab** | 7 actions · mode `REMOTE KQL COMPILATION` |
| **Stage 8, substep 5** | `7-4` | **pass-lab** | **17 passes** · label *QueryPlanFinalizer physical pass pipeline (includes conditional candidates)* |

Substep 5 is additionally the **only** substep in the entire document that un-hides
`details#physical-plan-deep-dive` (guard at L6277: `stageIndex === 7 && stepIndex === 4`). Because the
deep-dive element lives inside `.pass-lab`, it travels with the node relocated by
`initializePassTable()` and therefore renders beneath the pass-tree grid rather than inside the
step-detail card.

The visual transition between substep 4 and substep 5 of Stage 8 is a full lab swap: the blue
physical-lab panel disappears and the cyan pass-lab panel appears in a different position in the
`.center` flow (pass-lab sits after execution-lab and before step-detail; physical-lab sits third).

### 16.3 Complete canonical runner map — all 45 substeps

| Display stage | Family | Per-substep runner |
|---|---|---|
| **Stage 1** Syntax | compiler-lab (`syntax`) | 1 → 3 actions · 2 → 3 · 3 → 4 · 4 → 4 |
| **Stage 2** Semantic | compiler-lab (`semantic`) | 1 → 4 · 2 → 4 · 3 → 4 · 4 → **5** · 5 → 4 |
| **Stage 3** Relop | compiler-lab (`relop`) | 1 → 4 · 2 → **5** + 4 mappings · 3 → 4 · 4 → 4 |
| **Stage 4** Preparation | pass-lab (partial) | **1 → none** · 2 → 4 passes · 3 → 3 passes · **4 → none** |
| **Stage 5** Initial optimize | pass-lab | 1 → **22 passes** · 2 → 1 · 3 → 1 · 4 → 3 · 5 → 3 |
| **Stage 6** Partial queries | pass-lab (partial) | **1 → none** · **2 → none** · 3 → **29 passes** · 4 → 6 passes |
| **Stage 7** Final optimize | pass-lab | 1 → **23 passes** · 2 → 3 · 3 → 1 · 4 → 11 · 5 → 15 |
| **Stage 8** Physical plan | physical-lab **+ pass-lab** | 1 → 5 actions · 2 → 8 · 3 → 7 · 4 → 7 · **5 → 17 passes** |
| **Stage 9** Serialize | boundary-lab | 1 → 6 actions · 2 → 5 · 3 → 7 |
| **Stage 10** Execute | execution-lab | 1 → 7 events / 3 scenarios · 2 → 7/3 · 3 → 7/3 · 4 → 8/4 · 5 → 8/4 · 6 → 7/4 |

### 16.4 Coverage summary

| Metric | Value |
|---|---|
| Substeps with a runner | **41 of 45** |
| Substeps with no runner | **4** — S4.1, S4.4, S6.1, S6.2 |
| compiler-lab substeps | 13 (Stages 1–3, complete) |
| pass-lab substeps | 15 (Stages 4–7 partial, plus S8.5) |
| physical-lab substeps | 4 (S8.1–S8.4) |
| boundary-lab substeps | 3 (Stage 9, complete) |
| execution-lab substeps | 6 (Stage 10, complete) |
| Stages using exactly one family | 9 |
| Stages mixing families | **1** — Stage 8 |
| Substep keys appearing in more than one lab map | **0** (verified exhaustively) |

Because no key collides, the "hide all, show one" render contract holds **by data construction**, not
by defensive logic. A reimplementation that adds a lab entry for an existing key would render two
labs simultaneously; nothing in the code prevents it.

---

## 17. JavaScript function inventory

| Function | Lines | Responsibility |
|---|---|---|
| `src(path, line, end)` | 2910–2911 | ADO deep-link URL builder, pinned to `COMMIT` |
| `codeLocationLabel(url)` | 3016–3023 | `"{file}:{line}–{end} ↗"` label |
| `appendTreeLinkedText(root, text)` | 3273–3289 | Tree-type linkification of one text run |
| `renderLinkedTreeBlock(element, text)` | 3291–3297 | Line-by-line linkified `<pre>` writer |
| `linkCodeReferences(root)` | 3307–3340 | `TreeWalker`-based prose linkification |
| `scheduledPass(name, line, file, tree, options)` | 3531–3542 | Pass factory with 6 defaults |
| `physicalAction(name, detail, line, endLine, state)` | 3763–3770 | Physical-action factory |
| `T(id, kind, name, children)` | 4733 | Traversal tree-node factory |
| `EF(kind, title, detail)` | 5038 | Execution stack-frame factory |
| `EO(op, zone, id, title, detail)` | 5039 | Execution memory-event factory |
| `EA(…14 args)` | 5040–5041 | Execution action factory |
| `$(id)` | 5311 | `document.getElementById` shorthand |
| `optimizationTableRows()` | 5313–5315 | Array of the 22 optimization `<tr>` rows |
| `currentPassLab()` | 5317–5319 | `passLabs[key] ?? null` |
| `currentPhysicalLab()` | 5321–5323 | `physicalLabs[key] ?? null` |
| `currentCompilerLab()` | 5325–5327 | `compilerLabs[key] ?? null` |
| `currentBoundaryLab()` | 5329–5331 | `boundaryLabs[key] ?? null` |
| `currentExecutionLab()` | 5333–5335 | `executionLabs[key] ?? null` |
| `scrollChildOnAxis(container, child, axis)` | 5337–5351 | Smooth centring on one axis |
| `initializePassTable()` | 5353–5367 | One-time `.pass-lab` relocation + table row wiring |
| `treeLineDiff(before, after)` | 5369–5395 | LCS line diff → two unchanged-index Sets |
| `renderPassTree(el, tree, activeToken, unchanged, diffClass)` | 5397–5407 | Pass tree with diff + active-line spans |
| `renderPhysicalState(el, text, unchanged, diffClass)` | 5409–5421 | State pane with `[✓]`/`[ ]`/`→`/`READY`/`RETURN` classes |
| `renderCompilerLab()` | 5423–5519 | Compiler lab full render |
| `selectCompilerAction(index)` | 5521–5526 | Bounds-checked selection |
| `applyCompilerAction()` | 5528–5532 | Strict-next apply |
| `resetCompilerLab()` | 5534–5539 | Reset + render |
| `renderPhysicalLab()` | 5541–5594 | Physical lab full render |
| `selectPhysicalAction(index)` | 5596–5601 | Bounds-checked selection |
| `applyPhysicalAction()` | 5603–5607 | Strict-next apply |
| `resetPhysicalLab()` | 5609–5613 | Reset + render |
| `setBoundarySource(elementId, href, prefix)` | 5615–5619 | Labelled link setter |
| `utf8Bytes(text)` | 5621–5623 | `new TextEncoder().encode` |
| `formatHex(bytes, limit = 192)` | 5625–5636 | 16-byte hexdump with ASCII gutter |
| `renderBoundaryLanes(config)` | 5638–5664 | Three-lane progress strip |
| `renderBoundaryRail(config)` | 5666–5683 | Boundary chip rail |
| `renderBoundaryPlanLab(config)` | 5685–5774 | Body A — node → JSON → bytes explorer |
| `buildBoundaryContext()` | 5776–5785 | Assembles the request-context object |
| `renderBoundaryContextLab()` | 5787–5863 | Body B — context toggles, diff, quiz |
| `renderBoundaryHandoffLab(config)` | 5865–5938 | Body C — interop call + failure injection |
| `renderBoundaryLab()` | 5940–5968 | Boundary chrome + body dispatch |
| `stopBoundaryPlay()` | 5970–5974 | Clears `boundaryTimer` |
| `moveBoundaryAction(delta)` | 5976–5982 | Clamped step with play-stop |
| `toggleBoundaryPlay()` | 5984–6003 | 1100 ms autoplay with rewind |
| `resetBoundaryLab()` | 6005–6014 | Full boundary state reset |
| `executionMemoryAt(config, through)` | 6016–6036 | Folds memory events into four zone Maps |
| `renderExecutionMemory(config, action)` | 6038–6095 | Heap zones + call stack |
| `renderExecutionComponents(action)` | 6097–6111 | 8-component status grid |
| `renderExecutionLab()` | 6113–6197 | Execution lab full render |
| `selectExecutionAction(index)` | 6199–6204 | Bounds-checked selection |
| `applyExecutionAction()` | 6206–6211 | **Ungated** `Math.max` apply |
| `resetExecutionLabState()` | 6213–6217 | State-only reset |
| `resetExecutionLab()` | 6219–6222 | Reset + render |
| `renderPassLab()` | 6224–6317 | Pass lab full render + table write-back |
| `selectPass(index)` | 6319–6325 | Selection; also resets `passNodeIndex` |
| `setPassNode(index)` | 6327–6332 | Clamped walk-token position |
| `applySelectedPass()` | 6334–6338 | Strict-next apply |
| `resetPassLab()` | 6340–6345 | Narrow reset + render |
| `resetPassLabState()` | 6347–6363 | Broad state-only reset across four lab families |
| `toggleArtifactCard()` | 6365–6374 | Collapse toggle + workspace class + ARIA |
| `toggleStageOverview()` | 6376–6385 | Collapse toggle + workspace class + ARIA |
| `renderStages()` | 6387–6399 | Level-1 strip |
| `renderStageOverview()` | 6401–6415 | Stage card fields + nav disabled state |
| `renderSubsteps()` | 6417–6464 | Level-2 rail + slider bounds |
| `renderStep()` | 6466–6511 | Step detail + fan-out to all five labs |
| `renderNetwork()` | 6513–6525 | Beacon state resolution |
| `traversalOccurrence(order, id, until)` | 6527–6531 | Count occurrences up to an index |
| `firstOrderPosition(order, id)` | 6533–6536 | 1-based first occurrence, or `""` |
| `renderTraversalNode(node, definition)` | 6538–6577 | Recursive `<li>` builder |
| `renderTraversal()` | 6579–6612 | Traversal card full render |
| `findTraversalNode(node, id)` | 6614–6621 | Depth-first id lookup |
| `setTraversal(index)` | 6623–6628 | Bounds-checked traversal position |
| `stopTraversal()` | 6630–6634 | Clears timer, restores `▶` |
| `toggleTraversal()` | 6636–6652 | 850 ms autoplay with rewind |
| `render()` | 6654–6659 | Full refresh |
| `selectStage(index)` | 6661–6671 | Stage transition |
| `selectStep(index)` | 6673–6686 | Substep transition with scroll preservation |

---

## 18. Defects, contradictions, and dead code

All items are **normative current behaviour**. Only items marked `CAVEAT` are proposed for change.

### 18.1 Data defects

1. **`stages[].steps[8]` is dead data.** Populated for all 45 substeps with an `L.*` URL; read by no
   renderer. The `L` registry exists almost entirely to feed it.
2. **`methodTargets["PassManager.Execute"]` duplicate key** (L3062 vs L3119). Last-wins resolves to
   `Src/Engine/DataNode/Common/PassManager.cs:58–88`, contradicting the neighbouring
   `preciseLinks[3][3]` which points at `RelationalEngine.cs:130–147`.
3. **`traversalCatalog[1].focuses[4] = 18` is out of range** (`order.length === 18`). Rescued only by
   the clamp at L6582, which lands S2.5 on index 17.

### 18.2 CSS defects

4. **`--text` is used but never declared** — four rules (L859, L896, L955, L1301) silently fall back
   to inherited colour.
5. **`--surface` is declared but never used.**
6. **Dead CSS rules** — no code path ever produces these class combinations:
   `.boundary-action-chip.current`, `.boundary-node-rail`, `.boundary-failure-rail`,
   `.boundary-size`, `.boundary-index`, `.boundary-context-options`, `.boundary-diff-line`,
   `.boundary-breakpoint` (singular), `.boundary-failure-result`, `.boundary-quiz-result`,
   `.boundary-experiment-controls`, `.execution-heap-object.current`,
   `.execution-stack-frame.abi`, `.execution-stack-frame.csharp`.
7. **`.execution-stack-frame.abi` has no rule** although `abi` is a live `frame.kind` value; those
   frames inherit the default blue left border.

### 18.3 JavaScript defects and contradictions

8. **"Apply" does not accumulate anything** (§7.7) — the strongest contradiction between UI copy and
   behaviour.
9. **The execution lab breaks the gating contract shared by the other three** — `Math.max` instead of
   strict-next, and `#execution-apply` is never `disabled`. Its memory panel additionally reflects the
   *previewed* index, not the *executed* one.
10. **Dead JS branch** — `action.lang === "abi"` at L6165 is unreachable; `abi` occurs only as a
    stack-frame kind.
11. **`renderBoundaryContextLab` and `renderBoundaryHandoffLab` branch on `stepIndex`, not on the lab
    key** (L5962–5964). Correct only because `boundaryLabs` is confined to stage 8.
12. **`renderBoundaryPlanLab(config)` accepts `config` and never reads it.**
13. **`8-1`'s five actions drive no body content** — stepping or playing them changes only the lanes,
    the status line, and `#boundary-primary-source`.
14. **`boundaryPlanNodes` skips NodeId 5** — `HashJoin#4` is followed by `RemoteQueryNode#6`. This is
    deliberate (the elided local build subtree) but is nowhere explained in the UI.
15. **`#boundary-play` loses its `▶` glyph** on the first render; `#traversal-play` retains
    glyph-only labels (`▶` / `❚❚`).
16. **Keyboard navigation self-disables** after the first click on any control (§9.2). `CAVEAT`.
17. **`selectStage` does not preserve scroll**, while `selectStep` goes to considerable lengths to do
    so — an asymmetry the user will feel when moving between stages.
18. **`html { scroll-behavior: smooth }` fights the synchronous `window.scrollTo` restore** inside
    `selectStep`; the `requestAnimationFrame` second call is the mitigation.
19. **Stale optimization-table badges** — the 4th-cell `.pass-mark` badges are only rewritten while
    `renderPassLab` has a config, so leaving S5.1 removes `.selected` but leaves the badges. Not
    observable, because the section is hidden in that state.
20. **`visited` is seeded with `new Set([0])`** but `selectStage(0)` is never invoked for the initial
    render, so Stage 1's `✓` depends entirely on the literal seed.
21. **`#step-summary` and `#step-action` render the identical string** (`step[1]`) in two adjacent
    regions of the same card.
22. **The static caveat `<p>` at L2458 is never replaced**, so the `Pass<T>` / `SyntaxPass` /
    `ReportPassResult` disclaimer appears beneath all 15 pass labs regardless of relevance.
23. **`.walk-node` `data-order` shows only the *first* visit position**, and that badge is replaced by
    `✓` once the node is visited — so the ordinal is legible only for not-yet-reached nodes.
24. **15 `innerHTML` assignments.** All interpolate authored constants only, and no user-controlled
    input exists anywhere in the page, so there is no injection vector. `CAVEAT` — the progress and
    status strings (`#compiler-progress`, `#physical-progress`, `#pass-walk-status`,
    `#execution-scenario-output`) would be safer as `textContent` + element construction.
25. **`.pass-lab` lives inside `#optimization-additional-context` in source but outside it at
    runtime.** Any consumer reading the raw HTML without executing `initializePassTable()` will
    mis-model the layout.
26. **`renderStep` invokes all five lab renderers unconditionally**; four of them perform a
    `classList.toggle` and return. Inexpensive, but the contract is "hide all, show one", not
    "show the matching one".
27. **No `<noscript>` fallback.** With JavaScript disabled the page renders an empty stage strip, an
    empty substep strip, empty detail slots, and the two static tables — effectively unusable.
28. **Print output is severely degraded** (§11.2), most notably the total loss of the traversal tree.
    `CAVEAT`.
29. **Seven boundary-lab anchors use `rel="noreferrer"` without `noopener`**, inconsistent with the
    other 14 links (§8.5).

### 18.4 Layout defects

30. **`.center` implicit-column overflow and sticky-artifact occlusion** — fully specified in §15.
    `CAVEAT`.
31. **`#workspace` overflows `.shell`** in the `avail ≈ 1166–1215px` band, where all three `minmax`
    floors bind simultaneously (§15.7).
32. **Below 820px the workspace resolves to a 953.6px single track inside an ~805px shell**,
    producing whole-document horizontal scrolling (§15.7).

---

## 19. Screenshot reconciliation

The canonical screenshot shows a dark navy page, a 10-item stage navigation with Stage 5 selected, a
substep rail, an artifact-transformation panel that appears to float at the right, and a pass pipeline
with before/after trees. Each claim is reconciled against the source below. **Source governs.**

| Screenshot observation | Verdict | Evidence |
|---|---|---|
| Dark navy page | **Confirmed** | `--bg: #07101d` plus two radial gradients, L26–36 |
| 10-stage navigation | **Confirmed** | `grid-template-columns: repeat(10, minmax(125px,1fr))` L187; `stages.length === 10` |
| "Stage 5" selected | **Confirmed** | Display is 1-based; this is `stageIndex === 4`, `short: "Initial optimize"` |
| Substep rail | **Confirmed** | `#substep-strip`; Stage 5 has 5 substeps |
| Artifact panel **floating** | **Qualified** | It is **sticky**, not floating: `position: sticky; top: 12px` (L260–264) as the third workspace grid column at ≥1181px. It *appears* to float during vertical scroll. Below 1180px it becomes `position: static` and spans the full width; below 820px it is an ordinary stacked card. The only genuinely floating element in the document is `#network-beacon` (`position: fixed`, L38) |
| Pass pipeline with before/after trees | **Confirmed** | `passLabs["4-0"]` — 22 passes, `pre#pass-tree-before` / `pre#pass-tree-after`, LCS line diff |
| Centre content appearing behind the artifact panel | **Confirmed and quantified** | §15 — at Stage 5 substep 1 the `.center` implicit column is 953.6px against a 602.92px track, overlapping the artifact card by 338.7px |

---

## 20. Acceptance checklist

A reimplementation is conformant when **every** item below is observably true. Items are grouped by
area and phrased as testable assertions. Items marked **[C]** encode a documented caveat/defect and
must be reproduced exactly unless the caveat is explicitly waived.

### 20.1 File and bootstrap

- [ ] Single self-contained HTML file; no external subresource of any kind is requested on load.
- [ ] `<title>` is `Kusto Query Lifecycle: Two-Level Interactive Walkthrough`; `<html lang="en">`.
- [ ] The script runs under `"use strict"` and requires no `DOMContentLoaded` guard.
- [ ] Bootstrap executes exactly `initializePassTable(); render();`.
- [ ] After bootstrap, `.pass-lab` is a direct child of `.center` positioned immediately before
      `.step-detail`. **[C]** — it is authored inside `#optimization-additional-context`.
- [ ] Each of the 22 optimization table rows has class `pass-row`, `data-pass-index`, a 4th cell, and
      a click handler that ignores clicks landing inside an `<a>`.

### 20.2 Stage level

- [ ] Exactly 10 stage buttons, in the order Syntax, Semantic, Relop, Preparation, Initial optimize,
      Partial queries, Final optimize, Physical plan, Serialize, Execute.
- [ ] `#journey-progress` reads `Stage N of 10`.
- [ ] The selected stage shows amber border and inverted number badge; visited-not-selected stages
      show a green `✓`.
- [ ] Stage 1 shows a `✓` on first load without any interaction. **[C]**
- [ ] `#previous-stage` is disabled at stage 1; `#next-stage` at stage 10.
- [ ] Selecting a stage resets `stepIndex` to 0, resets all lab state, stops both timers, and sets
      `traversalIndex = focuses[0]`.
- [ ] Selecting a stage does **not** preserve scroll position. **[C]**

### 20.3 Substep level

- [ ] Substep counts per stage are exactly 4, 5, 4, 4, 5, 4, 5, 5, 3, 6 (45 total).
- [ ] Each substep chip shows `Substep N`, the title, a cyan walk badge, an amber change badge, and a
      runner badge chosen by the precedence pass → physical → compiler → boundary → execution.
- [ ] The four runner-less substeps (S4.1, S4.4, S6.1, S6.2) show **no** runner badge and render
      **no** lab section and **no** placeholder.
- [ ] Each substep chip carries a source-link anchor labelled `{file}:{line}–{end} ↗`.
- [ ] `#step-slider` `max` equals `steps.length - 1` and tracks `stepIndex` bidirectionally.
- [ ] Selecting a substep preserves scroll position across the layout change (synchronous restore
      plus one `requestAnimationFrame` restore).
- [ ] `#step-summary` and `#step-action` display the identical string. **[C]**

### 20.4 Runner engines

- [ ] At most one lab is visible at any time, at all 45 substeps.
- [ ] Compiler lab is visible at exactly the 13 keys `0-0…0-3`, `1-0…1-4`, `2-0…2-3` and carries the
      correct `kind` class (`syntax` / `semantic` / `relop`) with the matching accent colour.
- [ ] Compiler before/after panel headings vary by `kind` per the table in §6.1.3.
- [ ] The compiler mapping grid renders only at S3.2 and only when the `map` option is selected.
- [ ] Pass lab is visible at exactly the 15 keys listed in §6.2.3, with pass counts
      4, 3, 22, 1, 1, 3, 3, 29, 6, 23, 3, 1, 11, 15, 17.
- [ ] At S5.1 exactly 5 of the 22 passes are marked `CHANGES THIS TREE`.
- [ ] The static second `<p>` of `.pass-lab-head` is never replaced and appears under all 15 pass
      labs. **[C]**
- [ ] `details#physical-plan-deep-dive` is visible at S8.5 and nowhere else.
- [ ] At S5.1, and only there, the 22-row table is two-way bound: clicking a row selects the pass,
      the selected row is tinted, and every row's 4th cell shows a `CHANGES` / `NO CHANGE` badge.
- [ ] Physical lab is visible at exactly `7-0…7-3` with 5, 8, 7, 7 actions and the four mode pills.
- [ ] Physical and boundary lab headings are overwritten with `Run “{substep title}” yourself`.
- [ ] Boundary lab is visible at exactly `8-0`, `8-1`, `8-2` with 6, 5, 7 actions, and its body is
      dispatched by `stepIndex` (0 → plan explorer, 1 → context experiment, 2 → handoff simulator).
      **[C]**
- [ ] The boundary plan explorer offers 6 nodes with NodeIds 0, 1, 2, 3, 4, **6** and three views
      (`C# object`, `JSON`, `UTF-8 bytes`); the hex view wraps at 16 bytes and truncates at 192.
      **[C]** — the NodeId gap is intentional.
- [ ] The boundary quiz accepts `Plan` / `Context` / `Both` and marks only `Context` correct.
- [ ] The boundary context experiment recomputes only the context buffer size; the plan buffer size
      is constant and `PLAN REBUILT?` always reads `No`.
- [ ] Execution lab is visible at exactly `9-0…9-5` with 7, 7, 7, 8, 8, 7 events and 3, 3, 3, 4, 4, 4
      scenarios.
- [ ] Execution heap folds `add` / `update` / `release` events over four zones in the fixed order
      managed, borrowed, cpp, rust, with `live` / `mutated` / `released` styling.
- [ ] The execution heap reflects the **selected** event index, not the executed one. **[C]**

### 20.5 Gating

- [ ] Pass, compiler, and physical Apply buttons are enabled only when the selected index equals
      `applied + 1`; labels cycle `Applied ✓` / `Apply … {n}` / `Apply … {k} first`.
- [ ] The execution Execute button is **never** disabled and applies via `Math.max`. **[C]**
- [ ] Applying never changes any displayed tree, state pane, or heap contents — only chip classes,
      badges, counters, and button labels. **[C]**
- [ ] Every rail's prev/next buttons are disabled at their respective bounds.
- [ ] Every index is clamped into range on render, so no out-of-range state can produce an exception.

### 20.6 Traversal

- [ ] The traversal mode pill, summary, movement, and unwind text come from
      `traversalCatalog[stageIndex]`.
- [ ] Four shared trees are used: `languageTree` (stages 1–3), `relopTree` (4–8), `physicalTree` (9),
      `executionTree` (10).
- [ ] Every id in every `order` exists in its tree, and every tree node appears in its `order`.
- [ ] Node classes resolve as `current` / `returning` / `visited` per the occurrence arithmetic in
      §5.8.
- [ ] `data-order` shows the first occurrence ordinal, replaced by `✓` once visited. **[C]**
- [ ] Clicking a node seeks to the next occurrence at or after the current index, else the first.
- [ ] Play advances at 850 ms, stops at the end, and rewinds to 0 if pressed at the end.
- [ ] Entering S2.5 clamps `traversalIndex` from the out-of-range `focuses[4] = 18` to 17. **[C]**

### 20.7 Network beacon

- [ ] The beacon is `position: fixed` bottom-right with `z-index: 100`.
- [ ] State resolves field-by-field: override `??` stage default.
- [ ] Exactly 8 overrides exist, at `1-0`, `1-2`, `5-2`, `7-3`, `8-2`, `9-3`, `9-4`, `9-5`.
- [ ] The `active` (pulsing red) state occurs at exactly one substep: **S10.5**.
- [ ] The `imminent` (pink) state occurs at exactly one substep: **S10.4**.

### 20.8 Source links

- [ ] All links target `msazure.visualstudio.com/One/_git/Azure-Kusto-Service` pinned to
      `version=GCe6fd1fd059015c2db443ae044b72f3dfba2d3cf3`.
- [ ] Labels render as `{file}:{line}–{end} ↗` with an en dash, collapsing to `{file}:{line} ↗` when
      start equals end.
- [ ] All 45 `preciseLinks` entries are distinct.
- [ ] Every call-path method resolves in `methodTargets`; every traversal node id resolves in
      `treeNodeReferences`.
- [ ] `S4.4`'s `PassManager.Execute` link resolves to `Common/PassManager.cs:58–88`. **[C]**
- [ ] Tree linkification uses a longest-key-first alternation with `(?<![A-Za-z0-9_])` /
      `(?![A-Za-z0-9_])` boundaries.
- [ ] Prose linkification skips text inside `a`, `button`, `code`, `pre`, `script`, `style`, and is
      idempotent across repeated renders.
- [ ] All outbound anchors use `target="_blank"`; 7 boundary-lab anchors use `rel="noreferrer"` while
      the rest use `rel="noopener noreferrer"`. **[C]**

### 20.9 Keyboard and accessibility

- [ ] `ArrowLeft` / `ArrowRight` move substeps; `ArrowUp` / `ArrowDown` move stages with
      `preventDefault`.
- [ ] The handler returns early when `event.target` matches `input, button`, which disables arrow
      navigation once any control holds focus. **[C]**
- [ ] `:focus-visible` renders a 3px amber outline with 2px offset.
- [ ] Both collapse toggles keep `aria-expanded` synchronised and swap `−` / `+` and their `title`.
- [ ] `#network-beacon` is the only `aria-live` region.
- [ ] `#pass-rail` is the only element whose `aria-label` changes at runtime.
- [ ] No `role`, `tabindex`, `aria-selected`, or `aria-current` attributes exist anywhere. **[C]**

### 20.10 Layout, responsive, print

- [ ] `.shell` is `min(1580px, 100% − 26px)`.
- [ ] Workspace tracks follow the formula in §15.2, including the 300px floor clamp.
- [ ] Collapsing the stage overview or the artifact card swaps the corresponding column to `54px` and
      adds `stage-collapsed` / `artifact-collapsed` to `#workspace`.
- [ ] The four breakpoints behave exactly as tabulated in §11.1 (1180, 850, 820, 520).
- [ ] `.center` has no explicit `grid-template-columns`, so its implicit column is min-content sized
      and overflows the track by the per-substep amounts in §15.5. **[C]**
- [ ] `#substep-strip` and `#pass-rail` do not scroll horizontally at ≥1181px; they widen the page
      instead. **[C]**
- [ ] The sticky artifact card overlaps and occludes the intruding centre content, which is not
      hit-testable in the overlap band. **[C]**
- [ ] The overlap persists at 1920px and 3840px for all 31 substeps whose `.center` min-content
      exceeds 772.7px. **[C]**
- [ ] Below 820px the workspace resolves to a 953.6px single track inside an ~805px shell. **[C]**
- [ ] Print hides all `button` and `input` elements, which removes the entire walk tree and every
      rail; dark `pre` backgrounds are not reset. **[C]**

### 20.11 Persistence and safety

- [ ] No `localStorage`, `sessionStorage`, `indexedDB`, cookie, `history`, or hash state is written or
      read.
- [ ] A reload restores every documented initial-state value in §13.
- [ ] The page issues no network request on load or during any interaction.
- [ ] No `try`/`catch`, no input validation, and no error surface exists; all "failure" content is
      static descriptive text.

### 20.12 Data integrity

- [ ] `stages[i].steps.length === preciseLinks[i].length === treeBehaviors[i].length ===
      traversalCatalog[i].focuses.length` for all 10 stages.
- [ ] Every `Step` tuple has arity 9; index `[8]` is present and unread. **[C]**
- [ ] No substep key appears in more than one lab map.
- [ ] `action.lang ∈ {cpp, rust, csharp}`; `frame.kind ∈ {cpp, csharp, rust, abi}`;
      `event.op ∈ {add, update, release}`; `event.zone ∈ {managed, borrowed, cpp, rust}`.
- [ ] Every `action.active` and every entry of `action.live` is a key of `executionComponents`.
- [ ] `boundaryLabs` action lanes are drawn from `{C#, Interop, C++}`.
- [ ] `methodTargets` contains exactly one duplicate key, `PassManager.Execute`. **[C]**
- [ ] `--text` is referenced by four CSS rules and declared by none; `--surface` is declared and
      unused. **[C]**

---

*End of specification.*

