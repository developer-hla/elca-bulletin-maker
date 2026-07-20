# Sundays & Seasons content cache

Liturgical content for a given date is identical for every church, and the
Sundays & Seasons (S&S) site is slow and rate-sensitive. To avoid re-fetching
the same day content, day texts, and hymn lyrics over and over, reads go
through a caching service layer backed by the `sns_cache` table.

## Architecture

- `sns/content_service.py` — `ContentService`, the single interface the web
  layer calls for day content, Bible passages, and hymn lyrics. On every read
  it checks `sns_cache` first and only falls through to a live S&S fetch (via
  the church's `SundaysClient`) on a miss or when `force_refresh` is set. It
  stores the JSON payload with `fetched_at = now()`.
- `sns/prefetch.py` — the Thursday warm-up job (see below).
- The web layer (`web/server.py`) never calls the S&S client for content
  directly anymore; it builds a `ContentService` per request and calls that.
  If a real S&S API ever replaces the scraping client, only the `sns/` modules
  change — the web layer is insulated.

## Cache keys and payloads

| Content       | Key                          | Payload                          |
|---------------|------------------------------|----------------------------------|
| Day content   | `day:{YYYY-M-D}`             | `DayContent.to_dict()`           |
| Bible passage | `passage:{citation}`         | `{"html": "..."}`                |
| Hymn lyrics   | `hymn:{collection}:{number}` | `HymnLyrics.to_dict()`           |

`DayContent`, `Reading`, and `HymnLyrics` are dataclasses with
`to_dict()`/`from_dict()` so `payload_jsonb` round-trips losslessly.

## TTL / freshness

`sns_cache.ttl_seconds` defaults to 604800 (7 days). A cached entry older than
its TTL is treated as a miss. Because liturgical content for a date does not
change, 7 days is comfortable. Every endpoint that reads content accepts a
`refresh=true` query parameter, which threads through as `force_refresh` and
bypasses the cached copy for that one call (the fresh result is then stored).

## Entitlement rule

Cached content is served **only** to churches that have a validated S&S link of
their own (`churches.sns_username` non-empty). The cache is keyed by
date/citation/hymn and is therefore **shared across churches**, so this rule is
what keeps the cache from becoming a way to read S&S content without a
subscription:

- The web layer refuses the request with the same "no account linked" error
  (HTTP 409, `sns_unlinked`) it returned before the cache existed, *before* any
  cache read happens.
- `ContentService` independently enforces entitlement (`entitled=False` raises
  `SubscriptionRequiredError` and touches neither the cache nor the client), so
  no caller can bypass the rule by accident.

## Thursday prefetch

`python -m bulletin_maker.sns.prefetch` warms the cache for the **coming
Sunday** for every church with a linked, validated S&S credential. It fetches
day content (which carries all the day texts) with `force_refresh=True`.

Hymn lyrics are **not** prefetched: hymns are chosen by the user, so none can be
determined ahead of time without input. Day content alone is the warm target.

Per-church failures are logged and never abort the run.

Cron (Thursday 06:00 local):

```cron
0 6 * * 4 cd /path/to/elca-bulletin-maker && DATABASE_URL=postgresql://localhost/bulletin_maker venv/bin/python -m bulletin_maker.sns.prefetch >> /var/log/bulletin-prefetch.log 2>&1
```

## Out of scope: binary assets

Hymn notation images are still fetched live during generation and are **not**
cached here. The `sns_cache.object_key` column is the future hook: a binary
asset would be written to object storage and its key recorded there instead of
inlining bytes into `payload_jsonb`.
