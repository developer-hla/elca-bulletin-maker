/* Bulletin Maker — Constants & shared state */

// ── Constants ────────────────────────────────────────────────────────

/** Season key to display label. */
export const SEASON_LABELS = {
    advent: "Advent",
    christmas: "Christmas",
    epiphany: "Epiphany",
    lent: "Lent",
    easter: "Easter",
    pentecost: "Ordinary Time",
    christmas_eve: "Christmas Eve",
};

/** Liturgical season colors for the season bar. */
export const SEASON_COLORS = {
    advent:       "#2B5EA0",
    christmas:    "#8A6414",
    epiphany:     "#2E7D32",
    lent:         "#5B2882",
    easter:       "#8A6414",
    pentecost:    "#2E7D32",
    christmas_eve:"#8A6414",
};

/** Canticle key to display label. */
export const CANTICLE_LABELS = {
    glory_to_god: "Glory to God",
    this_is_the_feast: "This Is the Feast",
    none: "None",
};

/** Document key to display label. */
export const DOC_LABELS = {
    bulletin: "Bulletin for Congregation",
    prayers: "Pulpit Prayers",
    scripture: "Pulpit Scripture",
    large_print: "Full with Hymns LARGE PRINT",
    leader_guide: "Leader Guide",
};

/** Wizard panel IDs in step order. */
export const STEP_IDS = ["step-date-music", "step-liturgy-texts", "step-review-generate"];

// ── State ────────────────────────────────────────────────────────────

/** Returns a fresh initial state object. */
export function initialState() {
    return {
        currentStep: 1,
        dateStr: "",          // "2026-02-22" (HTML input value)
        dateDisplay: "",      // "February 22, 2026"
        season: "",
        defaults: null,       // seasonal liturgical defaults
        hymns: {              // {slot: {number, collection, title}}
            gathering: null,
            sermon: null,
            communion: null,
            sending: null,
        },
        readingOverrides: {},  // {slot: {label, citation, intro, text_html}}
        coverImage: "",
        liturgicalTexts: null,  // raw texts from API
        textChoices: {},        // {key: {source, isCustom, value}}
    };
}

export const state = initialState();
