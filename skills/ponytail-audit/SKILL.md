---
name: ponytail-audit
description: >-
  整个仓库的过度设计审计。和 ponytail-review 同类，区别是扫全库而不是只看 diff：
  产出一份排好序的清单，讲清哪些该删、哪些该简化、哪些该换成标准库或平台原生实现。
  用户说 "audit this codebase"、"audit for over-engineering"、"what can I delete from this repo"、
  "find bloat"、"ponytail-audit" 或 "/ponytail-audit" 时使用。只出报告，不动手改。
disable-model-invocation: true

---

ponytail-review, repo-wide. Scan the whole tree instead of a diff. Rank
findings biggest cut first.

## Tags

Same as ponytail-review:

- `delete:` dead code, unused flexibility, speculative feature. Replacement: nothing.
- `stdlib:` hand-rolled thing the standard library ships. Name the function.
- `native:` dependency or code doing what the platform already does. Name the feature.
- `yagni:` abstraction with one implementation, config nobody sets, layer with one caller.
- `shrink:` same logic, fewer lines. Show the shorter form.

## Hunt

Deps the stdlib or platform already ships, single-implementation interfaces,
factories with one product, wrappers that only delegate, files exporting one
thing, dead flags and config, hand-rolled stdlib.

## Output

One line per finding, ranked: `<tag> <what to cut>. <replacement>. [path]`.
End with `net: -<N> lines, -<M> deps possible.` Nothing to cut: `Lean already. Ship.`

## Boundaries

Scope: over-engineering and complexity only. Correctness bugs, security holes,
and performance are explicitly out of scope. Route them to a normal review
pass. Lists findings, applies nothing. One-shot.
"stop ponytail-audit" or "normal mode" to revert.
