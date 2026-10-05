# Third-party code and assets

AIHOT, fixed upstream commit `035f7b7f6e26cf203562ddd6065ff7adc1bb0c07`.
Source: https://github.com/KKKKhazix/AIHOT/tree/035f7b7f6e26cf203562ddd6065ff7adc1bb0c07

Included editorial prompt templates are copied from `industry/prompts/` to
`backend/app/analysis/prompt_templates/`. The rendering/include/hash logic in
`backend/app/analysis/prompts.py` is adapted from
`packages/backend/src/editorial/prompts.ts` to Python; HotKey's brand is provided
at render time. The existing topic-analysis prompt remains a separate purpose
under the same analysis domain and call/version ledger.

Leaderboard calculation code is adapted from `packages/backend/src/leaderboard/method/`;
its local module records the exact algorithms and changes. No AIHOT name/logo or
third-party fonts/marks are copied by these code imports. New copied assets must
retain their respective original terms.

The source registry, configuration selection, identities, refresh and source parsing
under `backend/app/leaderboard/` are also adapted from the upstream leaderboard domain.
The prefilter, independent scoring, structure, writing and identity rules under
`backend/app/analysis/editorial_*` are adapted from upstream `editorial/analyze.ts`,
`editorial/input.ts`, `editorial/writing.ts`, `industry/selection.ts` and
`industry/taxonomy.ts`; HotKey retains its own persistence, topic relevance and jobs.
WP-008-002 updates the structure template, category guides and original-quote validation from AIHOT commit `9acad0c3d7687d9210c2b7774f83799dfd36734b`, preserving HotKey JSONB persistence and adding field-level discard diagnostics.
WP-008-003 adapts group-definitions/group-method/group-pair, composite mention guards and relation comparison tests from the same `9acad0c` snapshot; unused group-batch/group-signal templates are removed because HotKey uses its existing fact-partition and pair-output contracts.

Codex announcement logic under `backend/app/monitors/codex_*` is adapted from
upstream `monitor/{time,recognize,assemble,scan,read}.ts` and the monitor administration
semantics. HotKey uses its existing model ledger and source authorization; it does not
adopt the upstream SocialData provider. Times are interpreted by program rules and
predictions remain distinct from confirmations. Event fact and correction semantics
under `backend/app/events/` are adapted from upstream events/stories/facts modules,
while preserving HotKey's frozen content versions and independent topic partitions.

The six source adapters and editorial intake under `backend/app/sources/editorial_*`,
`sources/adapters/editorial_*`, `connections/editorial_*` and `content/editorial_*`
are adapted from upstream source/ingest/provider behavior. Publication, exports,
selected synchronization, media presentation and mirrors under `backend/app/publication/`
are adapted from upstream publication/read/feed/MCP/share/media behavior. Calendar
editions under `backend/app/reports/edition_*`, translation under
`backend/app/analysis/translation_*`, SelectBench under `analysis/evaluation_*`,
and operational feedback/maintenance under `backend/app/operations/` are adapted
from the corresponding upstream modules. They use HotKey's original content,
Evidence, model usage, Job/Outbox, Kafka and notification ownership. Business UI
under the corresponding `frontend/src/app/` routes implements these contracts;
no upstream brand assets or private source material are included.

Initial-import archive admission, undated derived-publication gates and robust source
date/Atom text parsing are adapted from AIHOT commits `50b562b`, `309e32e` and
`6560d7f` (reference snapshot `9acad0c`), including their source/publication date tests;
HotKey retains undated raw reading and personal reports under its own contracts.

Public outlet consistency, category filtering and bounded image rendition reuse are adapted from AIHOT commits `ec42ff7`, `1d48ec1`, `50b562b` and `36604b9` (reference snapshot `9acad0c`); HotKey retains ALL live permission checks and its restricted SVG codec, while MCP subscription capacity/retirement (`dd12db1`, `36604b9`) and oversized SVG conversion (`9acad0c`) are not ported.

Edition selection/memory and daily-to-period compilation are adapted from AIHOT
`9acad0c` (`reports/edition.ts`, `reports/compose.ts`, `docs/selection.md` step 7);
the three `report-period*.md` templates use that version, while the unused
`report-daily-lead.md` template is removed. HotKey retains Beijing calendar
windows, ALL permission checks and the existing immutable version/call ledger.

Source avatar selection/cache and native/embedding event rematching are adapted
from upstream `sources/icons.ts`, `providers/embeddings.ts` and `events/group.ts`.
Industry topic definitions and canonical share layouts/QR behavior are adapted
from the upstream taxonomy and publication modules. The local PNG renderer uses
the upstream Noto Sans SC subsets under `backend/app/publication/assets/og-fonts/`;
the original copyright notice and complete SIL Open Font License 1.1 accompany
those files. No upstream trademark/logo assets are used.

## AIHOT MIT license

MIT License

Copyright (c) 2026 数字生命卡兹克

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Upstream notice

AIHOT
Copyright (c) 2026 数字生命卡兹克. The code is licensed under the MIT License (LICENSE).

The name "AIHOT" and the AIHOT logo are not licensed under the MIT License. Please use your own name
and logo for your site.

This repository also contains third-party material under its own terms:

- assets/og-fonts/: Noto Sans SC, SIL Open Font License 1.1 (assets/og-fonts/LICENSE).
- assets/model-providers/: model and provider marks, mostly from Lobe Icons (MIT). The marks remain
  trademarks of their respective owners and are used only to identify them (assets/model-providers/NOTICE.md).
- assets/leaderboard-sources/: the published marks of each evaluation operator, used only to identify
  them (assets/leaderboard-sources/NOTICE.md).

The demo sources in industry/sources.json are public feeds of their publishers. Their content belongs
to them; by default the site shows only a summary and a link to the original.

## Editor.js and content rendering

The Web content viewer uses [Editor.js](https://github.com/codex-team/editor.js)
2.31.7 (Apache-2.0) OutputData types as a development dependency; it does not
bundle the editor runtime or block/inline tool packages. Markdown parsing uses
[marked](https://github.com/markedjs/marked) 18.0.14 (MIT); HTML cleaning uses
[sanitize-html](https://github.com/apostrophecms/sanitize-html) 2.18.0 (MIT).
Package licenses remain in the dependency distributions; resolved versions are
recorded in frontend/pnpm-lock.yaml.
