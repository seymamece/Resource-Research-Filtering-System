# Requirements from the online curriculum project

What the guidance site (the `online-curriculum-` project) needs from this system, and what
in the current resource folders does not match it yet. Written 2026-10-13 for this system to
work from. Where this file and an earlier plan of this system disagree, this file wins for
anything the site will read.

---

## 1. Divide the work: do not rebuild what already exists

The site project already has a working pipeline for **books and documents** (PDF, Word, page
images). This system should not build a second one.

| Already in the site project | Command | Where it keeps its data |
|---|---|---|
| Catalogue of 80 source files, each with a confirmed role and rights | `sources:catalog` | `SOURCES_DIR/_private/source-catalog.json` |
| Text of each source, page by page | `sources:extract` | `SOURCES_DIR/_text/<id>.json` |
| Page search per topic (BM25, English and Turkish) | `draft:context` | `SOURCES_DIR/_private/context/` |
| Quote check: every quote must be on its cited page | `draft:verify` | in the draft |
| Video list from the owner's two spreadsheets | `videos:list` | `SOURCES_DIR/_private/videos.json` |
| Topic coverage report (which topics the books cover weakly) | `topics:coverage` | `curriculum/proposals/coverage.md` |

`SOURCES_DIR` is `G:\My Drive\Sources`. Source ids there are `s-` plus 10 hex characters of
the file's sha256, so they survive renaming and moving files.

**What this system should do (the gaps):**
1. **Web resources.** Websites, articles, online lessons and activities. The site project
   has nothing for these yet.
2. **Videos.** Finding, describing and pre-filtering videos for each topic. This is the
   slowest step in writing a lesson today. The owner's lists are a start, but have no age,
   topic or suitability data.
3. **Topic matching for weak topics.** About a fifth of the 504 topics (mostly modern-life
   topics for ages 15 to 18: university, social media, money) are weakly covered by the
   books. `curriculum/proposals/coverage.md` lists them. Look for web and video material for
   these first.
4. **Per-topic source hints from the owner's spreadsheet.** The topic spreadsheet has a
   "source" column for each topic (for example, age 18 topic 5 points to a chapter on
   reason in *Key Concepts in the Practice of Sufism*). The site project has not imported
   this column yet. Exporting it is valuable.

For a book already in the catalogue, refer to it by its catalogue id. Do not copy it.

---

## 2. Rules that cannot change

These come from the site's PLAN.md, section 0. The site rejects any export that breaks them.

1. **Order of authority.** The Qur'an first, then the Risale-i Nur and Hocaefendi's books,
   with the hadith they cite. Everything else is supporting material. It may give stories,
   examples, activities and methods. It is never the basis for a statement of faith.
2. **No school or institution names in anything the site shows.** Names may stay inside
   this system's own catalogue (a channel or platform is often named after an institution).
   The **export to the site** must contain none in any field the site displays: titles,
   descriptions or notes. Check every exported string against the fingerprints in
   `research/blocked-names.json` (sha256 of lower-cased words; see the site's
   `tools/hash-names.ts`). Put a source's real name only in a private field (section 4).
3. **Only a person marks something verified.** A tool or an AI may set `to_verify` or
   `proposed`. Never `verified`, `approved` or `reviewed`. The same holds for videos: a
   person watches each one before it is approved.
4. **No student data.** No names, classes, attendance or follow-up sheets. A spreadsheet
   "by class" must be checked before it enters this system.
5. **Copyright.** No full texts or book files in git. Store where a passage is and a short
   quote (5 to 40 words). The site writes everything in its own words; quotes stay in the
   evidence and never reach a lesson.
6. **No keys or credentials in git** (`.env` is ignored).
7. **No people or faces in pictures** for the site. Prophets and Companions are never shown.
   Videos are judged case by case; record what is in them (section 4.3).

---

## 3. Shared vocabulary: use the site's ids exactly

### 3.1 Ages
The site has **one track per year of age, 5 to 18**, each with 36 numbered topics
(504 topics). It does not use K-2, 3-5, 5-11, 11-18 or series S1 to S6.

- Store ages as integers: `"ages": { "min": 13, "max": 18 }`.
- Refer to a topic as `{ "age": 18, "topic": 5 }`.
- The topic lists are the site's `curriculum/scope-and-sequence.md` (ages 13 to 18) and
  `curriculum/lists-age-5-12.md` (ages 5 to 12). `tools/topics.ts` reads both.

How the owner's spreadsheet series map to ages:

| Sheet | Labelled | Site age |
|---|---|---|
| S1 | 13–14 | 13 |
| S2 | 14–15 | 14 |
| S3 | 15–16 | 15 |
| S4 | 17–18 | **16** |
| S5 | 17–18 | 17 |
| S6 | 18–19 | 18 |

### 3.2 Strands (what a topic is about)
Use these string ids from the site's `content/strands.json`, not the numbers 1 to 6:

| id | Meaning |
|---|---|
| `akaid` | Belief |
| `quran` | The Qur'an |
| `siyer` | The Prophet's life, with hadith and sunnah |
| `prophets` | The prophets |
| `ilmihal` | Worship and practice |
| `ahlak` | Character and manners |

### 3.3 Lenses (the angle a topic is taught from)
`nature`, `science`, `daily-life`, `technology`, `history`, `companions-scholars`,
`hadith-sunnah`. A resource can have several. "Life and technology" is a **lens** here, not a
strand.

### 3.4 Role (what a resource may be cited for)
This is separate from priority. The current "TIER 1/2/3" is about when to look at something;
keep it, but call it `priority`.

| role | May be cited for |
|---|---|
| `religious` | A statement of faith. Only the Qur'an, the Risale-i Nur and Hocaefendi's books. |
| `religious-supporting` | A story, a Companion's life, a prayer. A faith statement from it must carry the Qur'an or hadith reference it quotes. |
| `method` | Teaching methods, activities, examples, values language. |
| `planning` | Nothing. Background for choosing topics, books and videos. |

Almost every web resource and video will be `method` or `religious-supporting`.

### 3.5 Rights
`pending`, `cleared` or `restricted`. A resource with `restricted` rights is never used.
A copy from an unofficial download site is `restricted`.

### 3.6 Languages
`en`, `tr`, `sw`, `lg`, `ar`. A resource can have several. Record the language of the
resource itself, not the language of its catalogue entry. Several current entries are marked
`tr` but are English sites.

---

## 4. The export the site will read

One file: `exports/online-curriculum/resources.json`. The site project will add an import
command that checks this file against a schema and rejects it whole if any check fails.

It has three levels:

```
resource  →  item  →  passage
(site, channel,   (one article, video,   (one place in the item that
 book)            chapter or lesson)      fits one or more topics)
```

The **passage** level matters most. To write a lesson, the site needs to know *where* to
look and *for which topic*, not only that a website exists.

### 4.1 resource

| Field | Required | Notes |
|---|---|---|
| `id` | yes | Stable, for example `r-` plus a short hash of the URL. A book already in the site's catalogue uses its `s-…` id and sets `catalogueId`. |
| `kind` | yes | `website`, `channel`, `book`, `app`, `course` |
| `title` | yes | A neutral title with no institution name, for example "Children's Qur'an workshop (Turkish)". |
| `privateName` | no | The real name. Kept private; the site never shows it. |
| `url` | yes for web | A working URL. An entry without one stays in this system and is not exported. |
| `languages` | yes | Section 3.6 |
| `ages` | yes | `{ "min", "max" }` |
| `strands`, `lenses` | yes | Sections 3.2 and 3.3 (may be empty lists) |
| `role` | yes | Section 3.4 |
| `rights` | yes | Section 3.5 |
| `priority` | no | `1`, `2` or `3` |
| `status` | yes | `to_verify`, `verified` (person only), `archived` |
| `retrieved` | yes for web | Date last checked, `YYYY-MM-DD` |
| `notes` | no | Our own words; no institution names |

### 4.2 item

| Field | Required | Notes |
|---|---|---|
| `id`, `resourceId` | yes | |
| `kind` | yes | `article`, `video`, `chapter`, `lesson-plan`, `activity`, `worksheet` |
| `title` | yes | Neutral, as in 4.1 |
| `url` | yes for web | |
| `languages`, `ages`, `strands`, `lenses` | yes | May narrow the resource's values |
| `retrieved` | yes | |

### 4.3 Extra fields for a video item

| Field | Notes |
|---|---|
| `youtubeId` | The 11-character id, if it is on YouTube |
| `minutes` | Length. The site prefers 5 to 20 minutes. |
| `channelPrivate` | The channel name, private |
| `subtitles` | Languages with subtitles, for example `["en", "tr"]` |
| `content` | What is in it: `faces`, `music`, `animation`, `talk`, `nasheed`, `drawn-prophet` (never usable) |
| `watchedBy` | Set only by a person, with a date, after watching it all |

### 4.4 passage

| Field | Required | Notes |
|---|---|---|
| `id`, `itemId` | yes | |
| `where` | yes | Page number, section heading, or `mm:ss` for a video |
| `quote` | yes for text | 5 to 40 words, **exactly** as in the source, so the site's quote check can find it |
| `qref` | no | A Qur'an reference it quotes, for example `"2:286"` |
| `href` | no | A hadith reference it quotes, for example `"Bukhari 6094"` |
| `topics` | yes | `[{ "age": 18, "topic": 5, "use": "story" }]` |
| `use` | yes | `faith`, `story`, `example`, `activity`, `science`, `definition` |
| `status` | yes | `proposed` until a person accepts it |

### 4.5 Example: age 18, topic 5, "The Heart and Mind Connection"

```json
{
  "version": 1,
  "exported": "2026-10-13",
  "resources": [
    {
      "id": "r-3f9a2c",
      "kind": "website",
      "title": "Teen mental health articles (English)",
      "privateName": "(kept here, not shown)",
      "url": "https://example.org/teens",
      "languages": ["en"],
      "ages": { "min": 15, "max": 18 },
      "strands": ["ahlak"],
      "lenses": ["science", "daily-life"],
      "role": "method",
      "rights": "cleared",
      "priority": 1,
      "status": "to_verify",
      "retrieved": "2026-10-13"
    }
  ],
  "items": [
    {
      "id": "i-7b21",
      "resourceId": "r-3f9a2c",
      "kind": "article",
      "title": "How emotions and thinking work together",
      "url": "https://example.org/teens/emotions-and-thinking",
      "languages": ["en"],
      "ages": { "min": 15, "max": 18 },
      "strands": ["ahlak"],
      "lenses": ["science"],
      "retrieved": "2026-10-13"
    }
  ],
  "passages": [
    {
      "id": "p-0042",
      "itemId": "i-7b21",
      "where": "section 'Two systems'",
      "quote": "(5 to 40 words copied exactly from the article)",
      "topics": [{ "age": 18, "topic": 5 }],
      "use": "science",
      "status": "proposed"
    }
  ],
  "topicHints": [
    {
      "age": 18,
      "topic": 5,
      "fromSheet": "S6 week 5",
      "hint": "Key Concepts in the Practice of Sufism, the chapter on reason ('aql)",
      "catalogueId": null
    }
  ]
}
```

`topicHints` carries the "source" column of the owner's topic spreadsheet (section 1, item 4).
Remove institution and website names from `hint`. Fill `catalogueId` when the book is in the
site's catalogue.

---

## 5. What does not match yet in the current folders

Found in `online-curriculum-/research/` on 2026-10-13.

### 5.1 Data
1. **Strands are numbered 1 to 6, with different meanings.** For example, "Life &
   Technology" is a strand there but a lens on the site. Use section 3.2 and 3.3.
2. **Ages are in series.** `sources-metadata.json` has two series labelled "17–18" (S4 and
   S5) and one labelled "18–19". Map them with the table in section 3.1.
3. **216 topics are listed, but the site has 504.** The spreadsheet covers ages 13 to 18
   only. Ages 5 to 12 have their own lists on the site.
4. **Half the topics (106 of 216) are filed under Character.** That is a keyword guess. The
   site sets each topic's strand itself when the lesson is written, from its six strands and
   seven lenses. Treat the strand on a topic hint as a suggestion; the site's choice wins.
5. **`link-resources.json`: every `url` is empty.** Every entry is also `language: "tr"`,
   even English sites, and `status: "new"`. Fill the URLs, correct the languages, use the
   status values in section 4.1, and give neutral titles. The current titles are platform
   names.
6. **No role or rights field** on any resource (section 3.4 and 3.5).

### 5.2 Files
7. **Duplicate copies.** The same books are in `01_PRIMARY-SOURCES/`, `primary/Books/` and
   `05_ARCHIVE/`. The site's catalogue already treats identical files as one entry; keep one
   copy.
8. **macOS leftover files.** `._…` files in `05_ARCHIVE/BOOKS/Booklets in english/` are not
   books. Delete them.
9. **Folder names suggest roles that differ from the confirmed ones.** `supporting-books/`
   holds *The Staff of Moses* (Risale-i Nur, role `religious`) next to *Time Management*
   (`restricted`). `01_PRIMARY-SOURCES/` holds children's books and du'a booklets
   (`religious-supporting`). The confirmed roles in the site's catalogue stand; folder names
   do not change them.
10. **Files left out of lesson material by the owner on 2026-10-11** are back in the folders:
    the supervisor seminar file, the publisher catalogue, the dream account and the
    organisational-history talk. Keep them out of anything exported.
11. **`TOPICS 1-6 role model follow up - by class.xlsx`.** Check it for children's names
    before this system reads it (rule 4). If it has any, keep it out.
12. **1.1 GB of books inside the site's repository folder.** They are not committed, but one
    `git add .` would push them. The originals belong in `SOURCES_DIR`. The site project
    will add `research/` subfolders to `.gitignore` (see section 6).

### 5.3 This system's own plan
13. **Location.** The setup summary says `/home/claude/...`. That is a temporary claude.ai
    sandbox. Keep the system in `Desktop\Resource Research & Filtering System` and in its own
    git repository.
14. **Integration is by file, not by import.** The site is TypeScript. `from resource_system
    import ResourceManager` will not run there. The site reads `exports/online-curriculum/resources.json`
    and nothing else.
15. **Not needed yet:** a web dashboard, a database, an API, usage tracking. First build
    `add`, `validate` (sections 2 to 4), `filter`, and `export --project online-curriculum`.

---

## 6. What the site project will do on its side

- Add `research/01_PRIMARY-SOURCES/`, `02_SUPPORTING-MATERIALS/`, `04_DATA-FILES/`,
  `05_ARCHIVE/` and `primary/` to `.gitignore`.
- Add `npm run resources:import`. It checks the export against sections 3 and 4, refuses
  blocked names and refuses `verified` set without a person. It then writes the accepted
  passages into the context that `draft:context` gives the lesson writer for each topic.
- Show passages and videos for a topic in the draft's review page, marked "proposed".

---

## 7. Order of work

1. Fix the data in section 5.1 for the existing 16 platforms (URLs, languages, roles,
   neutral titles).
2. Build `add` and `validate` against sections 3 and 4.
3. Export `topicHints` from the topic spreadsheet. This is quick, and useful right away.
4. Collect videos and passages for the weak topics in `coverage.md`, starting with age 18,
   because that is the age the site is writing now (topics 5 to 36).
5. `export --project online-curriculum`. Hand the file to the site project.
