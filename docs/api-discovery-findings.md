# Sundays & Seasons — API Discovery Findings

## Overview

Sundays & Seasons (sundaysandseasons.com) is a **server-rendered ASP.NET MVC app**. There is no REST/JSON API — all content is returned as HTML pages that need to be parsed. Authentication is cookie-based with CSRF tokens.

---

## Authentication

- **Login URL:** `POST https://members.sundaysandseasons.com/Account/Login`
- **Method:** Form POST with:
  - `__RequestVerificationToken` (CSRF token — scraped from the login page)
  - `UserName`
  - `Password`
- **Session:** Cookie-based. After a successful 302 redirect, the session cookie is set and used for all subsequent requests.
- **No Authorization headers** — purely cookie auth.

### Login Flow
1. `GET /Account/Login` → parse the `__RequestVerificationToken` from the HTML form
2. `POST /Account/Login` with token + credentials → 302 redirect on success
3. Session cookies are now set for subsequent requests

---

## Liturgical Content — DayTexts

### Endpoint
```
GET /Home/DayTexts/{date}/{eventDateId}
```

- **Date format:** `YYYY-M-D` (no zero-padding, e.g., `2026-2-22`)
- **eventDateId:** Can be `0` for default day resolution. Special liturgical days have specific IDs (e.g., `2700`, `2712`), but `0` works from the calendar links for most days.

### Response Structure (HTML)
The page content is in `<div id="rightcolumn">` → `<div class="rightpanel">`. Key sections identified by `<h3>` headings:

| Section | Heading |
|---------|---------|
| Day title | `<h2>` e.g., "Sunday, February 22, 2026 — First Sunday in Lent, Year A" |
| Introduction | `<h3>Introduction</h3>` |
| Confession and Forgiveness | `<h3>Confession and Forgiveness</h3>` |
| Prayer of the Day | `<h3>Prayer of the Day</h3>` |
| Gospel Acclamation | `<h3>Gospel Acclamation</h3>` |
| Readings and Psalm | `<h3>Readings and Psalm</h3>` — summary with links |
| First Reading | `<h3>First Reading: {citation}</h3>` — full text |
| Psalm | `<h3>Psalm: {name}</h3>` — full text with refrain markers |
| Second Reading | `<h3>Second Reading: {citation}</h3>` — full text |
| Gospel | `<h3>Gospel: {citation}</h3>` — full text |

### CSS Classes for Formatting
- `.rubric` — leader instructions (typically italic in bulletin)
- `.body` — main content
- `<strong>` — **congregation responses** (bold in bulletin)
- `.redtext` — liturgical symbols (☩)
- `.refrain` — psalm refrain markers
- `.reading_intro` — intro text before each reading (italic)
- `sup.point` — psalm pointing marks

### Download
There's also a direct download link: `GET /Home/Download?view=DayTexts`

---

## Day ID Resolution

The `/Home/DayTexts/{date}/{eventDateId}` endpoint needs an eventDateId, but **`0` works for most dates** — the server resolves it to the correct liturgical day. From the Planner/Month page, only Sundays and special feast days have non-zero IDs:

Example from March 2026:
- `/Home/DayTexts/2026-3-1/2701` (Sunday)
- `/Home/DayTexts/2026-3-8/2702` (Sunday)
- `/Home/DayTexts/2026-3-19/2762` (St. Joseph)
- `/Home/DayTexts/2026-3-25/2763` (Annunciation)

**Strategy:** Use `0` as the eventDateId. If needed, scrape the Planner/Month page to get exact IDs.

---

## Music / Hymn Lookup

### Search
```
GET /Music/Search?collection=ELW&Search.HymnSongNumber={number}
```

Key search form fields:
- `collection` — hymnal (e.g., `ELW`)
- `Search.HymnSongNumber` — hymn number (e.g., `504`)
- `Search.Title` — title search
- `Search.AuthorComposer` — author/composer
- `page`, `sortColumn`, `sortDirection` — pagination/sorting

Results contain elements with `data-atom-id` and `data-title` attributes.

### Hymn Details
```
POST /Music/_Details
Body: atomId={id}
```

Returns HTML fragment with:
- **Harmony image:** `<img src="/File/GetImage?atomCode=STANZA_{code}_h&width=700&height=700"/>`
- **Melody image:** `<img src="/File/GetImage?atomCode=STANZA_{code}_m&width=700&height=700"/>`
- Copyright information
- Text/tune details

### Media Preview (Audio)
```
POST /Music/MediaPreview
Body: atomId={id}
```
Returns **base64-encoded MP3 audio** data.

### Hymn Number → atomId Mapping
ELW hymn numbers are NOT used directly. The flow is:
1. Search by number: `GET /Music/Search?collection=ELW&Search.HymnSongNumber=504`
2. Parse `data-atom-id` from results
3. Fetch details: `POST /Music/_Details` with `atomId`

---

## File/Image Endpoints

### Score Notation Images
```
GET /File/GetImage?atomCode={code}&width={w}&height={h}
```
- Returns JPEG images
- Codes follow pattern: `STANZA_{number}_h` (harmony) or `STANZA_{number}_m` (melody)

### Thumbnails
```
GET /File/GetThumbnail?atomCode={code}
```
- Returns JPEG thumbnails (used for liturgical art/icons)

### File Download (ZIP)
```
POST /File/Download
Body: atomId={id}&useType=Worship&useDate={date}&numCopies={count}
```
- Returns `application/octet-stream` (ZIP file)
- Example: `"Kyrie (Schubert).zip"`
- Date format in POST: `M/DD/YYYY` (URL-encoded)

### Visual Art Download
```
GET /File/Download?atomCode={code}
```
- Returns TIFF images for visual art/clip art

---

## Summary of What We Need to Build

1. **Login session manager** — GET login page, parse CSRF token, POST credentials, maintain cookies
2. **DayTexts scraper** — fetch and parse HTML for liturgical content by date
3. **Music search** — look up ELW number → atomId
4. **Image downloader** — fetch notation images via `/File/GetImage`
5. **HTML-to-DOCX formatter** — convert the parsed content (with rubric/bold/italic classes) to Word styles
