# Learn

The **Learn** screen is a small library about artificial intelligence (AI), meant to take a
person from "what is this?" to professional level at their own pace — or to let them stay at
the level they are comfortable with.

## What is in it

| Part | What | Where |
|---|---|---|
| **Lessons** | 14 short texts written for Datas, in English and Spanish, 2–4 minutes each. Readable offline. | `datas/learn/lessons.en.md`, `lessons.es.md` |
| **Glossary** | 42 words the app and the field use, one sentence each. | `datas/learn/catalog.json` → `glossary` |
| **Outside material** | 55 courses, videos, articles, books, reports, research papers and official texts. | `catalog.json` → `items` |
| **Paths** | 18 ordered routes through all of the above. | `catalog.json` → `paths` |

Paths: Start here · Use it well · Daily life · AI on your own device · How it works · Build
with it · Go deep · Where it came from · Where it stands today · Where it may go · Who is who
· Rules and public policy · Ethics, safety and rights · At work and in business · Teaching
and learning · Social projects and nonprofits · Government and public services · In Spanish.

Every item has a **level** from 1 to 5: new to AI, everyday use, confident, building with AI,
expert. The screen filters by level and searches titles, authors and descriptions.

"Ask the guide about this" on a lesson opens a chat with the lesson attached, so the AI
running on the device can explain it another way.

## Rules for the list of outside material

1. **Every address is checked by a person** against a search result or the publisher's own
   page on the date in `checked`. No address is written from memory or built by pattern.
2. **Primary sources first**: the law itself, the report itself, the author's own page.
3. **Say whose voice it is.** An investor's yearly report, a company chief's essay and an
   intergovernmental review are all listed — each described as what it is.
4. **Debates get more than one side.** "Where it may go" pairs an optimistic essay, a sceptical
   one, a fast-risk scenario and the international scientific review, on purpose.
5. **Neutral.** Datas does not rank opinions. It says what a text is and who wrote it.
6. **Spanish matters.** Items available in Spanish are marked, and "En español" collects them.
7. **Nothing is sent.** Links open in the user's own browser (`POST /api/open-url`, web
   addresses only). Datas does not contact those sites.

Known and useful, but **not linked** because their address was not verified when the list was
made: the Spanish-language channel *Dot CSV* (search for it by name), a Spanish edition of the
Prompt Engineering Guide, ISO/IEC 42001, the Dartmouth 1955 proposal, MIT 6.S191.

## Adding or changing an item

Edit `datas/learn/catalog.json`:

```json
{
  "id": "short-name", "title": "Exact title", "by": "Author or organisation", "year": 2026,
  "url": "https://…", "kind": "course|video|article|book|report|paper|law|guide|site",
  "level": 1, "lang": ["en", "es"], "cost": "free",
  "why": {"en": "One sentence: what it is and who it is for.", "es": "Lo mismo en español."}
}
```

Add its `id` to at least one path, update `checked`, and run `pytest tests/test_learn.py`: the
test refuses items that are on no path, paths that point to nothing, missing translations and
addresses that are not `https`.

Lessons are Markdown. A lesson starts with `=== id | level | minutes`, then `# Title`. Keep
them short, concrete and free of claims that go stale; the same lesson must exist in both
language files.

## Progress

"Mark as done" is stored in `<data folder>/learn.json` in Remember mode. In Forget mode
nothing is written.
