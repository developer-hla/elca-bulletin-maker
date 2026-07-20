# Rite engine (LWS-0b)

This document describes the rite **schema**, its **storage**, the **text
catalog**, and the **library transcription** of the current ELW Sunday ordo.
It is the reference for the reviewer checking the transcription against the
templates, and for LWS-0c/0d (which will make the renderer iterate rite data
instead of the hardcoded Jinja in `bulletin.html` / `large_print.html`).

**Scope guardrail:** LWS-0b adds *dormant* code and data only. No renderer or
template file changes; generated output is unchanged. The renderer does not yet
read any of this.

## Modules

| Path | Purpose |
|---|---|
| `core/rite.py` | Dataclasses (`Rite`, `RiteModule`, `Block`, `Condition`, `RoleLabels`), strict `to_dict`/`from_dict`, `validate_rite`, `condition_applies`. |
| `core/text_catalog.py` | Stable string keys → the fixed-text constants in `renderer/static_text.py` (imported, never copied). `get_text` fails fast on unknown keys. |
| `core/library/` | Bundled library JSON (`elw_sunday_communion.json`, `elw_holy_baptism.json`) + loader/validator (`__init__.py`). |
| `web/rites.py` | Persistence (`save_rite`/`get_rite`/`list_rites`, module equivalents) over the `rites`/`rite_modules` tables. |
| `web/migrations/008_rites.sql` | `rites` + `rite_modules` tables. |

## Schema overview

A `Rite` is `{ id, church_id (NULL = library), name, tradition, occasion,
base_rite_id, version, meta: {role_labels, notes}, blocks: [Block] }`. A
`RiteModule` is a reusable occasion fragment (e.g. Holy Baptism) referenced by
a `module_ref` block.

Common block fields: `id`, `type`, `title?`, `condition?`, `toggle?`, plus a
`note?` for human annotations (JSON has no comments). Type-specific payload
lives alongside these and is validated per type.

### Block types

Active: `heading{text}`, `rubric{text}`, `dialogue{lines|text_ref}`,
`literal_text{text|text_ref|profile_ref, style?}`, `hymn_slot{slot, render}`,
`reading_slot{slot, render}`, `psalm{source, style}`,
`proper_slot{kind, fallback?}`, `notation{piece, text_fallback?}`,
`music_item{kind}`, `module_ref{module_id}`.

Reserved (defined now, parse fine, but flagged unusable by `validate_rite`
until their UI ships in LWS-7): `prayer_list`, `week_calendar`, `serving_list`,
`staff_directory`, `announcement_text`.

`profile_ref` is a schema extension (allowed values `cover`, `welcome_message`,
`standing_instructions`, `copyright_paragraphs`) for content driven by the
`CongregationProfile` rather than the text catalog — the cover page and the
welcome/standing/copyright chrome. See "What does not fit" below.

### Conditions

`Condition = {seasons?, feasts?, toggles?, invert?}`. An empty (or `None`)
condition always applies; present fields **AND** together; `invert` flips the
final result. `condition_applies(condition, context)` evaluates against a
`context` carrying `season` (str), `feasts` (list), and `toggles` (dict
name→bool). Toggles compare by exact boolean value, so a `{baptism: false}`
condition applies precisely when baptism is off (and when the context omits it,
since absent toggles read as `False`).

### Validation

`from_dict` is **structural** and fail-fast: an unknown block `type`, an
unknown payload field, a missing required field, a bad enum value, a violated
one-of group, or a malformed dialogue line each raises `RiteSchemaError`
naming the offender. `validate_rite` is **referential**: every `text_ref` /
`fallback` / `text_fallback` must resolve in the catalog, every `profile_ref`
must be known, every `module_ref` must resolve, referenced modules' own blocks
are validated too, duplicate block ids are reported, and reserved block types
are flagged. It raises `RiteValidationError` carrying the full error list.

## Toggle → ServiceConfig mapping

Every condition toggle used by the library rite maps to a real
`ServiceConfig` field (`core/models.py`; the wizard's `core/service_form.py`
populates it). Three enum fields are exposed to the boolean condition system as
**derived toggles** (see "Canticle & creed modeling" for why).

| Toggle (in rite) | ServiceConfig field | Template gate | Notes |
|---|---|---|---|
| `show_confession` | `show_confession: Optional[bool]` | `{% if show_confession %}` | Off e.g. Christmas Eve. |
| `greeting` | `show_greeting: Optional[bool]` | `{% if greeting_entries %}` | Renderer builds `greeting_entries` from `show_greeting`. |
| `kyrie` | `include_kyrie: Optional[bool]` | `{% if kyrie_image_uri %}` (bulletin) / `kyrie_entries` (LP) | |
| `canticle_glory_to_god` | `canticle == "glory_to_god"` | `{% if canticle_image_uri %}` + renderer image/text choice | Derived from the `canticle` enum. |
| `canticle_this_is_the_feast` | `canticle == "this_is_the_feast"` | same | Derived; `canticle == "none"` → neither true, no canticle block. |
| `baptism` | `include_baptism: bool` | `{% if include_baptism %}` | When true, baptism module **replaces** the creed. |
| `creed_nicene` | `creed_type == "nicene"` | `{% else %}` creed branch, `creed_name`/`creed_stanzas` | Derived; gated additionally on `baptism == false`. |
| `creed_apostles` | `creed_type == "apostles"` | same | Derived; gated on `baptism == false`. |
| `eucharistic_extended` | `eucharistic_form == "extended"` | `{% if eucharistic_form == "extended" %}` | Derived; short form omits the extended-only blocks. |
| `memorial_acclamation` | `include_memorial_acclamation: Optional[bool]` | `{% if has_memorial_acclamation %}` | Extended form only. |
| `nunc_dimittis` | `show_nunc_dimittis: Optional[bool]` | `{% if show_nunc_dimittis ... %}` | |

Season condition (not a toggle):

| Condition | Template gate | Notes |
|---|---|---|
| `seasons: ["lent"]` (Invitation to Lent) | `{% if is_lent %}` | Renderer resolves `is_lent` from the liturgical day. |

Deliberately **unconditioned** blocks that a naive reading of the brief might
expect a toggle on:

- **Gospel acclamation** — no `ServiceConfig` field backs a "ga" toggle. In
  `large_print.html` the heading is *always* present (falling back to the S&S
  acclamation text); in `bulletin.html` it is hidden only when the notation
  image asset is unavailable (`{% if ga_image_uri %}`). That is a renderer-side
  asset fallback, not a liturgical choice, so the block carries no condition.
  Inventing a toggle with no config field would violate the brief's rule that
  every toggle map to a real field.

### Canticle & creed modeling (choice + justification)

The `canticle`, `creed_type`, and `eucharistic_form` fields are single enums in
`ServiceConfig`, but conditions in this schema are boolean. Two options were on
the table (per §2.1 / the brief): one block with a `variant` field, or two
blocks each gated on a toggle.

**Chosen: two blocks, each gated on a derived boolean toggle.** For the
canticle: `canticle_glory_to_god` and `canticle_this_is_the_feast`, exactly one
of which is true (or neither, when `canticle == "none"`). Likewise
`creed_nicene`/`creed_apostles` and the extended-EP blocks on
`eucharistic_extended`.

Justification:

1. **No new schema surface.** A `variant` field would be a fourth
   variant-selection mechanism (alongside `condition`, `toggle`, and the
   render-mode fields). The condition system already expresses "show this block
   when X", and mapping an enum to N derived booleans reuses it exactly.
2. **The blocks genuinely differ.** Glory to God and This Is the Feast have
   different text (`GLORY_TO_GOD_TEXT` vs `THIS_IS_THE_FEAST_TEXT`), different
   notation images, and This Is the Feast has a distinct `final_refrain`. Nicene
   and Apostles' are different creeds. These are two blocks, not one block with
   a toggled field.
3. **LWS-0c stays a pure filter.** The renderer becomes "keep blocks whose
   condition applies", with the enum→derived-boolean expansion living in one
   small context-builder step. No block-type-specific variant resolution in the
   dispatch loop.

The renderer (LWS-0c) will expand each enum into its derived booleans when it
builds the condition `context` — e.g. `canticle="glory_to_god"` →
`{canticle_glory_to_god: True, canticle_this_is_the_feast: False}`.

## Text catalog keys

`text_ref` / `fallback` / `text_fallback` resolve here. Keys are namespaced:
`elw.*` = ELW ordo / Setting Two text; `house.*` = an Ascension house text that
overrides the S&S/ELW default. Every value is imported from
`renderer/static_text.py` (single source of truth).

| Key | Constant |
|---|---|
| `elw.confession_form_a` | `CONFESSION_AND_FORGIVENESS` |
| `elw.greeting` | `GREETING` |
| `elw.kyrie_dialog` | `KYRIE_DIALOG` |
| `elw.glory_to_god` | `GLORY_TO_GOD_TEXT` |
| `elw.this_is_the_feast` | `THIS_IS_THE_FEAST_TEXT` |
| `elw.invitation_to_lent` | `INVITATION_TO_LENT` |
| `elw.nicene_creed` | `NICENE_CREED` |
| `elw.apostles_creed` | `APOSTLES_CREED` |
| `elw.default_prayers_call` | `DEFAULT_PRAYERS_CALL` |
| `elw.default_prayers_response` | `DEFAULT_PRAYERS_RESPONSE` |
| `elw.offertory_hymn_verses` | `OFFERTORY_HYMN_VERSES` |
| `elw.great_thanksgiving_dialog` | `GREAT_THANKSGIVING_DIALOG` |
| `elw.great_thanksgiving_preface` | `GREAT_THANKSGIVING_PREFACE` |
| `elw.great_thanksgiving_preface_short` | `GREAT_THANKSGIVING_PREFACE_SHORT` |
| `elw.sanctus` | `SANCTUS` |
| `elw.eucharistic_prayer_extended` | `EUCHARISTIC_PRAYER_EXTENDED` |
| `elw.words_of_institution` | `WORDS_OF_INSTITUTION` |
| `elw.memorial_acclamation` | `MEMORIAL_ACCLAMATION` |
| `elw.eucharistic_prayer_closing` | `EUCHARISTIC_PRAYER_CLOSING` |
| `elw.come_holy_spirit` | `COME_HOLY_SPIRIT` |
| `elw.lords_prayer` | `LORDS_PRAYER` |
| `house.invitation_to_communion` | `INVITATION_TO_COMMUNION` |
| `elw.agnus_dei` | `AGNUS_DEI` |
| `elw.nunc_dimittis` | `NUNC_DIMITTIS` |
| `elw.aaronic_blessing` | `AARONIC_BLESSING` |
| `elw.dismissal` | `DISMISSAL_ENTRIES` |
| `elw.dismissal_text` | `DISMISSAL` |
| `elw.baptism_presentation` | `BAPTISM_PRESENTATION` |
| `elw.baptism_renunciation` | `BAPTISM_RENUNCIATION` |
| `elw.baptism_profession` | `BAPTISM_PROFESSION` |
| `elw.baptism_flood_prayer` | `BAPTISM_FLOOD_PRAYER` |
| `elw.baptism_formula` | `BAPTISM_FORMULA` |
| `elw.baptism_welcome` | `BAPTISM_WELCOME` |
| `elw.baptism_welcome_response` | `BAPTISM_WELCOME_RESPONSE` |

Five keys are present but not directly referenced by a current block, because
the corresponding text is resolved renderer-side today, not through a block
`text_ref`: `elw.come_holy_spirit` (interleaved between EP closing stanzas),
`elw.default_prayers_call` / `elw.default_prayers_response` (S&S-supplied
call/response with these as defaults), `elw.dismissal_text` (the plain-string
dismissal; the block uses the `(role, text)` `elw.dismissal`), and
`elw.great_thanksgiving_preface_short` (the abbreviated preface variant). They
are catalogued so LWS-0c/0d can wire them without touching this module.

## Storage

`rites` and `rite_modules` (migration 008): `church_id` NULL = library row;
`blocks`/`meta` are `jsonb`; `version` bumps on every re-save; `updated_at`
tracks it. Uniqueness is enforced by
`UNIQUE (COALESCE(church_id, 0), occasion, name)` for rites (and
`COALESCE(church_id, 0), name` for modules) so library rows share one
namespace — a plain `UNIQUE` would treat every NULL `church_id` as distinct.
`save_rite` UPSERTs by id and bumps `version` on conflict; `list_rites(church_id)`
returns that church's rites plus all library rites (library first).

## What does not fit "one rite, two styles"

The vision is: one rite, rendered by two (five) document styles that differ by
typography, not content. Most of the ordo fits cleanly. The following were
captured as `note` fields rather than forced into the schema, and are the
renderer's job (LWS-0c/0d), not the rite's:

1. **Notation vs text is renderer-style.** `kyrie`, `canticle`, `great_thanksgiving`,
   `sanctus`, `agnus_dei`, `nunc_dimittis`, `memorial_acclamation`, `preface`,
   the offertory hymn, and the sung Amen are single `notation` blocks with a
   `text_fallback`. The bulletin renders the notation image; large print renders
   the fallback text; the leader guide overlays notation. One block, per-document
   rendering.
2. **Per-document hymn render mode.** A `hymn_slot` carries one `render` value,
   but the same hymn is a title (bulletin), lyrics (large print), or notation
   (leader guide) depending on document. The stored value is the bulletin's; the
   real choice is per-document and stays renderer-side.
3. **Memorial-acclamation sung/spoken.** `ServiceConfig.memorial_acclamation_mode`
   picks image (sung) vs bold text (spoken) *within the bulletin*. That is a
   render variant of the same notation block, not a structural fork, so it is one
   block noted rather than two.
4. **Preface resolution.** Which preface text/notation is used is per-season /
   per-occasion (`ServiceConfig.preface`). Kept renderer-side for now; the block
   anchors the full-text fallback only.
5. **Profile-driven chrome.** The cover page and the welcome / standing-instruction
   / copyright blocks come from the `CongregationProfile`, not the text catalog.
   Modeled as `literal_text` with a `profile_ref`; they do not fit the pure
   `literal_text{text}` model and are identity/chrome rather than liturgy.
6. **Inline template literals.** Several short leader/response lines have no
   `static_text` constant and live inline in the templates today (peace,
   offering invitation, post-communion blessing, gospel/reading responses, the
   Lord's-Prayer bidding, prayers-of-intercession framing). They were transcribed
   as `dialogue`/`literal_text` blocks with the text inline (from `bulletin.html`,
   the primary source) so no renderer file was edited to add a constant.

### Genuine bulletin/large-print wording differences (not typography)

Transcribed from `bulletin.html` (primary). The two templates differ in more
than typography at these points; LWS-0d must reconcile them (likely by moving
the longer/alternate wording into the rite or a per-document override):

- **Sharing of the Peace instruction** — bulletin: "We greet one another with a
  sign of Christ's peace."; large print appends: "…saying "Peace be with you,"
  as we shake hands or share a hug."
- **Post-communion blessing** — bulletin: "our Lord Jesus **Christ**"; large
  print: "our Lord Jesus".
- **Heading wording** — bulletin "*PRAYER OF THE DAY" vs LP "Prayer of the Day";
  bulletin "*GOSPEL ACCLAMATION" vs LP "*GOSPEL ACCLAMATION (SUNG)"; bulletin
  "AGNUS DEI" vs LP "AGNUS DEI (SUNG)". These are title/case differences; the
  rite stores the bulletin title.
