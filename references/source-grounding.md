# Source grounding

## Workspace discovery

Locate an authorized local Azure-Kusto-Service checkout at runtime. Do not hardcode a path.
Confirm it is a git worktree and that its remote/repository identity is Azure-Kusto-Service.
Resolve:

```powershell
git -C "<workspace>" rev-parse HEAD
```

The result must be a full 40-character commit. Do not use a branch name, moving tag, short
SHA, cached commit, or commit from a previous run.

## Link shape

Every source link must:

- start with `https://dev.azure.com/msazure/`;
- address an Azure-Kusto-Service repository path;
- include `version=GC<40-char-head>`;
- include numeric `line` and `lineEnd` values;
- identify the same commit in the link object;
- point at the narrowest source range that proves the claim.

Example shape only:

```text
https://dev.azure.com/msazure/<project>/_git/Azure-Kusto-Service
  ?path=/path/to/file
  &version=GC<commit>
  &line=<start>
  &lineEnd=<inclusive-end-plus-one>
  &lineStartColumn=1
  &lineEndColumn=1
```

Azure DevOps treats `lineEnd` as exclusive. The model's `end_line` is inclusive, so encode
`lineEnd=end_line+1` while keeping the displayed model range inclusive.

Use the current workspace path and exact line range. Verify each target after constructing it.
Do not link to search results, directory pages, PR diffs, branch tips, or whole files.

## Claim discipline

A link proves only the adjacent claim. Source that registers or schedules a pass does not
prove that the pass transformed this query. A factory definition does not prove that an
operator is in the supplied plan. A type definition does not prove a concrete allocation or
stack address.

For mixed managed/C++/Rust paths, link each frame or boundary independently. Omit languages
and components not present in the supplied plan/evidence.
