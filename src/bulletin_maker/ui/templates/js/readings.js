/* Bulletin Maker — Date & season fetch, readings, defaults */

import {
    $, show, hide, showError, hideError, showWarning, hideWarning,
    showBtnSpinner, hideBtnSpinner, escapeHtml, sanitizeHtml,
} from "./dom.js";
import { state, CANTICLE_LABELS } from "./state.js";
import { api } from "./api.js";
import { applySeasonTheme, formatDate, resetFormUI } from "./wizard.js";
import {
    loadLiturgicalTexts,
    setMemorialAcclamationMode,
    updateMemorialAcclamationModeControls,
    setOffertoryType,
} from "./texts.js";

/** The bundled library rite every service uses until a church picks another. */
export const DEFAULT_RITE_ID = "elw_sunday_communion";

/** Populate the Service Rite dropdown from the API (church + library rites). */
export async function loadRiteOptions() {
    var select = $("#rite-select");
    if (!select) return;
    try {
        var result = await api.get_rites();
        if (!result.success || !result.rites.length) return;
        select.innerHTML = "";
        result.rites.forEach(function(rite) {
            var opt = document.createElement("option");
            opt.value = rite.id;
            opt.textContent = rite.name;
            if (rite.id === DEFAULT_RITE_ID) opt.selected = true;
            select.appendChild(opt);
        });
    } catch (err) {
        // Leave the select empty — collectFormData() then sends no rite_id,
        // and the resolver falls back to the bundled default rite.
    }
}

/** Maps a reading label to an override slot key. */
function readingSlotKey(label) {
    var l = label.toLowerCase();
    if (l.indexOf("first") !== -1) return "first";
    if (l.indexOf("second") !== -1) return "second";
    if (l.indexOf("psalm") !== -1) return "psalm";
    if (l.indexOf("gospel") !== -1) return "gospel";
    return l;
}

// ── Date & Season Fetch ──────────────────────────────────────────────

export async function handleDateFetchResult(result) {
    state.season = result.season;
    state.defaults = result.defaults;
    state.unsavedWork = true;

    // Surface S&S content sanity-check warnings (empty sections)
    var contentWarning = $("#content-warning");
    if (contentWarning) {
        if (result.warnings && result.warnings.length) {
            showWarning(contentWarning,
                "Content check: " + result.warnings.join(" "));
        } else {
            hideWarning(contentWarning);
        }
    }

    // Reset hymns and service details for the new date
    state.hymns = { gathering: null, sermon: null, communion: null, sending: null };
    state.coverImage = "";
    resetFormUI();

    // Display day info + apply season theme
    $("#day-name").textContent = result.day_name;
    applySeasonTheme(result.season);
    var seasonBar = $("#season-bar");
    if (seasonBar) $("#season-bar-day").textContent = "— " + result.day_name;

    const readingsEl = $("#readings-list");
    readingsEl.innerHTML = "";
    state.readingOverrides = {};
    (result.readings || []).forEach(function(r) {
        var slot = readingSlotKey(r.label);
        var div = document.createElement("div");
        div.className = "reading-item";
        div.dataset.slot = slot;

        // Header row: label + citation + action links
        var header = document.createElement("div");
        header.className = "reading-header";

        var labelSpan = document.createElement("span");
        labelSpan.className = "reading-label";
        labelSpan.textContent = r.label + ":";
        header.appendChild(labelSpan);

        var citationSpan = document.createElement("span");
        citationSpan.className = "reading-citation-text";
        citationSpan.textContent = " " + r.citation;
        header.appendChild(citationSpan);

        var editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "btn-link reading-edit-btn";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", function() {
            var editArea = div.querySelector(".reading-edit-area");
            if (editArea) {
                editArea.hidden = !editArea.hidden;
                editBtn.textContent = editArea.hidden ? "Edit" : "Cancel";
                return;
            }
            editBtn.textContent = "Cancel";
            var area = document.createElement("div");
            area.className = "reading-edit-area";
            var input = document.createElement("input");
            input.type = "text";
            input.className = "reading-citation-input";
            input.value = r.citation;
            input.placeholder = "Enter citation (e.g. Genesis 2:15-25)";
            area.appendChild(input);

            var fetchBtn = document.createElement("button");
            fetchBtn.type = "button";
            fetchBtn.className = "btn secondary reading-fetch-btn";
            fetchBtn.textContent = "Fetch";
            fetchBtn.addEventListener("click", async function() {
                var citation = input.value.trim();
                if (!citation) return;
                showBtnSpinner(fetchBtn);
                var result = await api.fetch_custom_reading(citation);
                hideBtnSpinner(fetchBtn, "Fetch");
                var msg = area.querySelector(".reading-edit-msg");
                if (!msg) {
                    msg = document.createElement("div");
                    msg.className = "reading-edit-msg";
                    area.appendChild(msg);
                }
                if (result.success) {
                    msg.innerHTML = '<span class="reading-edit-ok">Fetched. Will use custom citation.</span>';
                    state.readingOverrides[slot] = {
                        label: r.label,
                        citation: citation,
                        intro: "",
                        text_html: result.text_html,
                    };
                    citationSpan.textContent = " " + citation + " (custom)";
                    // Invalidate any cached preview
                    var oldPreview = div.querySelector(".reading-content-preview");
                    if (oldPreview) oldPreview.remove();
                    previewBtn.textContent = "Preview";
                } else {
                    msg.innerHTML = '<span class="error-msg">' + escapeHtml(result.error || "Failed to fetch") + '</span>';
                }
            });
            area.appendChild(fetchBtn);

            var resetBtn = document.createElement("button");
            resetBtn.type = "button";
            resetBtn.className = "btn-link reading-reset-btn";
            resetBtn.textContent = "Reset";
            resetBtn.addEventListener("click", function() {
                delete state.readingOverrides[slot];
                input.value = r.citation;
                citationSpan.textContent = " " + r.citation;
                var msg = area.querySelector(".reading-edit-msg");
                if (msg) msg.innerHTML = "";
                // Invalidate any cached preview
                var oldPreview = div.querySelector(".reading-content-preview");
                if (oldPreview) oldPreview.remove();
                previewBtn.textContent = "Preview";
            });
            area.appendChild(resetBtn);

            div.appendChild(area);
        });
        header.appendChild(editBtn);

        // Preview button
        var previewBtn = document.createElement("button");
        previewBtn.type = "button";
        previewBtn.className = "btn-link reading-preview-btn";
        previewBtn.textContent = "Preview";
        previewBtn.addEventListener("click", async function() {
            var existing = div.querySelector(".reading-content-preview");
            if (existing) {
                existing.hidden = !existing.hidden;
                previewBtn.textContent = existing.hidden ? "Preview" : "Hide";
                return;
            }
            showBtnSpinner(previewBtn);
            var res = await api.get_reading_preview(slot);
            hideBtnSpinner(previewBtn, "Preview");
            if (!res.success) {
                showError($("#date-error"),
                    "Could not load the preview: " + (res.error || "unknown error"));
                return;
            }
            hideError($("#date-error"));
            var preview = document.createElement("div");
            preview.className = "reading-content-preview";
            if (res.intro) {
                var intro = document.createElement("p");
                intro.className = "reading-intro";
                intro.textContent = res.intro;
                preview.appendChild(intro);
            }
            var content = document.createElement("div");
            content.className = "reading-content";
            content.innerHTML = sanitizeHtml(res.preview_html);
            preview.appendChild(content);
            div.appendChild(preview);
            previewBtn.textContent = "Hide";
        });
        header.appendChild(previewBtn);

        div.appendChild(header);

        readingsEl.appendChild(div);
    });

    show($("#day-info"));

    // Show filename preview
    try {
        var prefixResult = await api.get_file_prefix();
        if (prefixResult.success) {
            $("#filename-prefix").textContent = "[Document] - " + prefixResult.prefix + ".pdf";
            show($("#filename-preview"));
        } else {
            hide($("#filename-preview"));
        }
    } catch (_) {
        hide($("#filename-preview"));
    }

    // Fetch liturgical texts for the review step
    await loadLiturgicalTexts();

    // Pre-fill liturgical settings
    applyDefaults(result.defaults);

    // Reset generate area
    hide($("#progress-area"));
    hide($("#results-area"));
    hideError($("#generate-error"));
}

export function setupDateFetch() {
    $("#fetch-btn").addEventListener("click", async function() {
        const dateInput = $("#date-input");
        const dateStr = dateInput.value;
        if (!dateStr) {
            showError($("#date-error"), "Please select a date.");
            return;
        }

        // Validate date is parseable
        const dateVal = new Date(dateStr + "T12:00:00");
        if (isNaN(dateVal.getTime())) {
            showError($("#date-error"), "Invalid date format.");
            return;
        }

        // Warn if changing date will lose existing work
        var hasWork = Object.values(state.hymns).some(function(h) { return h; }) ||
            Object.keys(state.textChoices).some(function(k) { return state.textChoices[k] && state.textChoices[k].isCustom; });
        if (hasWork && !confirm("Changing the date will clear all hymns and text edits. Continue?")) {
            return;
        }

        hideError($("#date-error"));
        hideWarning($("#date-warning"));
        hideWarning($("#content-warning"));
        hide($("#day-info"));

        // Warn if date is not a Sunday (non-blocking)
        if (dateVal.getDay() !== 0) {
            showWarning($("#date-warning"), "Note: this date is not a Sunday.");
        }

        const spinner = $("#date-spinner");
        show(spinner);
        this.disabled = true;

        const dateDisplay = formatDate(dateStr);

        const result = await api.fetch_day_content(dateStr, dateDisplay);

        hide(spinner);
        this.disabled = false;

        if (!result.success) {
            if (result.auth_error) return;
            showError($("#date-error"), result.error || "Failed to fetch content.");
            return;
        }

        state.dateStr = dateStr;
        state.dateDisplay = dateDisplay;
        await handleDateFetchResult(result);
    });
}

/** Pre-fills liturgical setting controls from seasonal defaults. */
function applyDefaults(defaults) {
    if (!defaults) return;

    // Creed
    const creedRadio = document.querySelector('input[name="creed_type"][value="' + defaults.creed_type + '"]');
    if (creedRadio) creedRadio.checked = true;
    $("#hint-creed").textContent = "Default: " + (defaults.creed_type === "nicene" ? "Nicene" : "Apostles'");

    // Kyrie
    $("#include-kyrie").checked = defaults.include_kyrie;
    $("#hint-kyrie").textContent = "Default: " + (defaults.include_kyrie ? "Yes" : "No");

    // Canticle
    const canticleRadio = document.querySelector('input[name="canticle"][value="' + defaults.canticle + '"]');
    if (canticleRadio) canticleRadio.checked = true;
    $("#hint-canticle").textContent = "Default: " + (CANTICLE_LABELS[defaults.canticle] || defaults.canticle);

    // Eucharistic form
    const epRadio = document.querySelector('input[name="eucharistic_form"][value="' + defaults.eucharistic_form + '"]');
    if (epRadio) epRadio.checked = true;
    $("#hint-eucharistic").textContent = "Default: " + defaults.eucharistic_form.charAt(0).toUpperCase() + defaults.eucharistic_form.slice(1);

    // Memorial acclamation
    $("#include-memorial").checked = defaults.include_memorial_acclamation;
    setMemorialAcclamationMode(defaults.memorial_acclamation_mode || null);
    updateMemorialAcclamationModeControls();
    $("#hint-memorial").textContent = defaults.include_memorial_acclamation
        ? "Default: Yes; choose sung or spoken"
        : "Default: No";
    var settingsError = $("#settings-error");
    if (settingsError) hideError(settingsError);

    // Preface
    if (defaults.preface) {
        populatePrefaceDropdown(defaults.preface);
    }

    // Confession
    var showConf = defaults.show_confession !== undefined ? defaults.show_confession : true;
    $("#show-confession").checked = showConf;
    $("#hint-confession").textContent = "Default: " + (showConf ? "Yes" : "No");

    // Nunc Dimittis
    var showNunc = defaults.show_nunc_dimittis !== undefined ? defaults.show_nunc_dimittis : true;
    $("#show-nunc-dimittis").checked = showNunc;
    $("#hint-nunc-dimittis").textContent = "Default: Yes";

    // Baptism (always unchecked by default)
    $("#include-baptism").checked = false;
    hide($("#baptism-details"));
    $("#baptism-names").value = "";
}

/** Populate preface dropdown from API, pre-selecting the seasonal default. */
async function populatePrefaceDropdown(defaultKey) {
    var select = $("#preface-select");
    select.innerHTML = "";

    try {
        var result = await api.get_preface_options();
        if (!result.success) return;

        var prefaces = result.prefaces;

        // Seasonal group
        var seasonalGroup = document.createElement("optgroup");
        seasonalGroup.label = "Seasonal";
        (prefaces.seasonal || []).forEach(function(p) {
            var opt = document.createElement("option");
            opt.value = p.key;
            opt.textContent = p.label;
            if (p.key === defaultKey) opt.selected = true;
            seasonalGroup.appendChild(opt);
        });
        select.appendChild(seasonalGroup);

        // Occasional group
        var occasionalGroup = document.createElement("optgroup");
        occasionalGroup.label = "Occasional";
        (prefaces.occasional || []).forEach(function(p) {
            var opt = document.createElement("option");
            opt.value = p.key;
            opt.textContent = p.label;
            if (p.key === defaultKey) opt.selected = true;
            occasionalGroup.appendChild(opt);
        });
        select.appendChild(occasionalGroup);

        $("#hint-preface").textContent = "Default: " + (select.options[select.selectedIndex] ? select.options[select.selectedIndex].textContent : defaultKey);
    } catch (err) {
        // Fallback: just set the key directly
        var opt = document.createElement("option");
        opt.value = defaultKey;
        opt.textContent = defaultKey;
        opt.selected = true;
        select.appendChild(opt);
    }
}

export function setupResetDefaults() {
    $("#reset-defaults-btn").addEventListener("click", function() {
        if (state.defaults) {
            applyDefaults(state.defaults);
        }
    });
}

export function applyRestoredSettings(fd) {
    // Service rite
    var riteSelect = $("#rite-select");
    if (riteSelect && fd.rite_id) riteSelect.value = fd.rite_id;

    // Liturgical settings
    var creedRadio = document.querySelector('input[name="creed_type"][value="' + fd.creed_type + '"]');
    if (creedRadio) creedRadio.checked = true;

    $("#include-kyrie").checked = !!fd.include_kyrie;

    var canticleRadio = document.querySelector('input[name="canticle"][value="' + fd.canticle + '"]');
    if (canticleRadio) canticleRadio.checked = true;

    var epRadio = document.querySelector('input[name="eucharistic_form"][value="' + fd.eucharistic_form + '"]');
    if (epRadio) epRadio.checked = true;

    $("#include-memorial").checked = !!fd.include_memorial_acclamation;
    setMemorialAcclamationMode(fd.memorial_acclamation_mode || null);
    updateMemorialAcclamationModeControls();

    if (fd.preface) {
        var prefSelect = $("#preface-select");
        if (prefSelect) prefSelect.value = fd.preface;
    }

    if (fd.show_confession !== undefined) $("#show-confession").checked = fd.show_confession;
    if (fd.show_nunc_dimittis !== undefined) $("#show-nunc-dimittis").checked = fd.show_nunc_dimittis;

    // Baptism
    $("#include-baptism").checked = !!fd.include_baptism;
    var baptismDetails = $("#baptism-details");
    if (fd.include_baptism) {
        show(baptismDetails);
        $("#baptism-names").value = fd.baptism_candidate_names || "";
    } else {
        hide(baptismDetails);
    }

    // Service music
    $("#prelude-title").value = fd.prelude_title || "";
    $("#prelude-composer").value = fd.prelude_composer || "";
    setOffertoryType(fd.offertory_type || "offertory");
    $("#offertory-title").value = fd.offertory_title || "";
    $("#offertory-composer").value = fd.offertory_composer || "";
    $("#offertory-performer").value = fd.offertory_performer || "";
    $("#postlude-title").value = fd.postlude_title || "";
    $("#postlude-composer").value = fd.postlude_composer || "";
    $("#choral-title").value = fd.choral_title || "";
    $("#choral-composer").value = fd.choral_composer || "";
}
