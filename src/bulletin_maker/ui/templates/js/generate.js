/* Bulletin Maker — Generation, progress, cover upload */

import { $, $$, show, hide, showError, hideError } from "./dom.js";
import { state, DOC_LABELS } from "./state.js";
import { api } from "./api.js";
import { handleAuthError } from "./auth.js";
import {
    getMemorialAcclamationMode,
    getOffertoryType,
    collectStructuredEntries,
    validateMemorialAcclamationMode,
} from "./texts.js";
import { savePastRun } from "./past-runs.js";
import { collectRiteVariables } from "./readings.js";

// ── Progress callback (called from Python via evaluate_js) ──────────

function updateProgress(data) {
    // Route update-step progress to the banner progress bar
    const fill = document.getElementById("progress-fill");
    const status = document.getElementById("progress-status");
    const bar = document.querySelector(".progress-bar");
    if (fill) fill.style.width = data.pct + "%";
    if (status) status.textContent = data.detail;
    if (bar) bar.setAttribute("aria-valuenow", data.pct);
}

window.updateProgress = updateProgress;

// ── File Pickers ─────────────────────────────────────────────────────

export function setupFilePickers() {
    var fileInput = $("#cover-file-input");

    $("#cover-image-btn").addEventListener("click", function() {
        fileInput.click();
    });

    fileInput.addEventListener("change", async function() {
        var file = this.files && this.files[0];
        this.value = "";
        if (!file) return;
        var btn = $("#cover-image-btn");
        btn.disabled = true;
        try {
            var result = await api.upload_cover(file);
            if (!result.success) {
                showError($("#cover-error"),
                    result.error || "Could not upload the cover image.");
                return;
            }
            hideError($("#cover-error"));
            state.coverImage = result.cover_token;
            $("#cover-image-path").textContent = file.name;
            show($("#cover-image-clear"));
            var img = $("#cover-image-preview");
            img.src = URL.createObjectURL(file);
            show(img);
        } finally {
            btn.disabled = false;
        }
    });

    $("#cover-image-clear").addEventListener("click", function() {
        state.coverImage = "";
        $("#cover-image-path").textContent = "None selected";
        hide(this);
        var img = $("#cover-image-preview");
        hide(img);
        img.removeAttribute("src");
    });
}

// ── Generation ───────────────────────────────────────────────────────

/** Collects all form data into a dict for the Python API. */
function collectFormData() {
    // Liturgical settings
    const creedEl = document.querySelector('input[name="creed_type"]:checked');
    const canticleEl = document.querySelector('input[name="canticle"]:checked');
    const epEl = document.querySelector('input[name="eucharistic_form"]:checked');
    const includeMemorial = $("#include-memorial").checked;

    const formData = {
        date: state.dateStr,
        date_display: state.dateDisplay,
        rite_id: $("#rite-select").value || null,
        creed_type: creedEl ? creedEl.value : null,
        include_kyrie: $("#include-kyrie").checked,
        canticle: canticleEl ? canticleEl.value : null,
        eucharistic_form: epEl ? epEl.value : null,
        include_memorial_acclamation: includeMemorial,
        memorial_acclamation_mode: includeMemorial ? getMemorialAcclamationMode() : null,
        preface: $("#preface-select").value || null,
        show_confession: $("#show-confession").checked,
        show_nunc_dimittis: $("#show-nunc-dimittis").checked,
        include_baptism: $("#include-baptism").checked,
        baptism_candidate_names: $("#baptism-names").value.trim(),
        variables: collectRiteVariables(),
        prelude_title: $("#prelude-title").value.trim(),
        prelude_composer: $("#prelude-composer").value.trim(),
        offertory_type: getOffertoryType(),
        offertory_title: $("#offertory-title").value.trim(),
        offertory_composer: $("#offertory-composer").value.trim(),
        offertory_performer: $("#offertory-performer").value.trim(),
        postlude_title: $("#postlude-title").value.trim(),
        postlude_composer: $("#postlude-composer").value.trim(),
        choral_title: $("#choral-title").value.trim(),
        choral_composer: $("#choral-composer").value.trim(),
        cover_image: state.coverImage,
        selected_docs: Array.from($$('input[name="doc_select"]:checked')).map(function(el) { return el.value; }),
    };

    // Reading overrides
    if (state.readingOverrides && Object.keys(state.readingOverrides).length > 0) {
        formData.reading_overrides = state.readingOverrides;
    }

    // Hymns
    ["gathering", "sermon", "communion", "sending"].forEach(function(slot) {
        const data = state.hymns[slot];
        if (data && data.number) {
            var hymnEntry = {
                number: data.number,
                collection: data.collection,
                title: data.title,
            };
            // Include selected_verses only when a subset is chosen
            if (data.selectedVerses && data.verseCount &&
                data.selectedVerses.length < data.verseCount) {
                hymnEntry.selected_verses = data.selectedVerses;
            }
            formData[slot + "_hymn"] = hymnEntry;
        } else {
            formData[slot + "_hymn"] = null;
        }
    });

    // Liturgical texts
    var tc = state.textChoices;

    // Structured texts: collect entries from the editor rows
    ["confession", "dismissal"].forEach(function(key) {
        if (!tc[key]) return;
        var editorEl = document.querySelector('.structured-editor[data-key="' + key + '"]');
        if (editorEl) {
            formData[key + "_entries"] = collectStructuredEntries(editorEl);
        }
    });

    // Plain texts: collect from textarea value
    ["offering_prayer", "prayer_after_communion", "blessing"].forEach(function(key) {
        if (tc[key]) {
            formData[key + "_text"] = tc[key].value || "";
        }
    });

    return formData;
}

/** Runs the document generation flow. Extracted for reuse by single-doc regen. */
var generationInProgress = false;

async function runGeneration(docOverride) {
    const generateBtn = $("#generate-btn");
    const errorEl = $("#generate-error");
    if (generationInProgress) return;
    hideError(errorEl);
    hide($("#results-area"));

    // Validate required state
    if (!state.dateStr || !state.dateDisplay) {
        showError(errorEl, "Please fetch content for a date first.");
        return;
    }

    // The date box must match what was actually fetched
    var dateInput = $("#date-input");
    if (dateInput && dateInput.value && dateInput.value !== state.dateStr) {
        showError(errorEl,
            "The date box shows " + dateInput.value + " but the fetched content is for " +
            state.dateStr + ". Click Fetch Content on Step 1 before generating.");
        return;
    }

    var selectedDocs = docOverride ||
        Array.from($$('input[name="doc_select"]:checked')).map(function(el) { return el.value; });
    if (selectedDocs.length === 0) {
        showError(errorEl, "Select at least one document to generate.");
        return;
    }
    if (!validateMemorialAcclamationMode(errorEl)) {
        return;
    }

    const formData = collectFormData();
    formData.selected_docs = selectedDocs;

    // Warn if any hymns lack lyrics (Large Print will show title only)
    var missingLyrics = [];
    ["gathering", "sermon", "communion", "sending"].forEach(function(slot) {
        var hymn = state.hymns[slot];
        if (!hymn || !hymn.number) return;
        // The hymn was fetched but lyrics may not have loaded
        if (hymn.title && !hymn.hasLyrics) {
            var label = slot.charAt(0).toUpperCase() + slot.slice(1);
            missingLyrics.push(label + " (" + hymn.collection + " " + hymn.number + ")");
        }
    });
    if (missingLyrics.length > 0) {
        var proceed = confirm(
            "The following hymns have no lyrics text — Large Print will show title only:\n\n" +
            missingLyrics.join("\n") +
            "\n\nContinue anyway?"
        );
        if (!proceed) return;
    }

    generationInProgress = true;
    generateBtn.disabled = true;
    $$(".regen-single-btn").forEach(function(el) { el.disabled = true; });
    show($("#progress-area"));
    $("#progress-fill").style.width = "0%";
    $("#progress-status").textContent = "Starting generation...";
    const bar = document.querySelector(".progress-bar");
    if (bar) bar.setAttribute("aria-valuenow", 0);

    const result = await api.generate_all(formData, updateProgress);

    generationInProgress = false;
    generateBtn.disabled = false;

    if (result.error && !result.results) {
        hide($("#progress-area"));
        if (handleAuthError(result)) return;
        showError(errorEl, result.error);
        return;
    }

    // Show results
    const resultsList = $("#results-list");
    resultsList.innerHTML = "";

    if (result.results) {
        Object.keys(result.results).forEach(function(key) {
            const li = document.createElement("li");
            const name = result.results[key];

            var link = document.createElement("a");
            link.href = api.file_url(key);
            link.textContent = (DOC_LABELS[key] || key) + " — " + name;
            link.setAttribute("download", name);
            li.appendChild(link);

            // Single-doc regenerate link
            var regenLink = document.createElement("button");
            regenLink.type = "button";
            regenLink.className = "btn-link regen-single-btn";
            regenLink.textContent = "Regenerate";
            regenLink.addEventListener("click", function() {
                regenerateSingleDoc(key);
            });
            li.appendChild(regenLink);

            resultsList.appendChild(li);
        });
    }

    // Show errors if any
    const errorsArea = $("#results-errors");
    const errorsList = $("#errors-list");
    errorsList.innerHTML = "";

    if (result.errors && Object.keys(result.errors).length > 0) {
        Object.keys(result.errors).forEach(function(key) {
            const li = document.createElement("li");
            li.textContent = (DOC_LABELS[key] || key) + ": " + result.errors[key];
            errorsList.appendChild(li);
        });
        show(errorsArea);
    } else {
        hide(errorsArea);
    }

    hide($("#progress-area"));

    // Show/hide success banner
    var banner = $("#success-banner");
    if (Object.keys(result.errors || {}).length === 0 && Object.keys(result.results || {}).length > 0) {
        show(banner);
    } else {
        hide(banner);
    }



    state.unsavedWork = false;
    show($("#results-area"));
    $("#results-area").scrollIntoView({ behavior: "smooth", block: "start" });

    // Save this run for Past Runs recall
    if (Object.keys(result.results || {}).length > 0) {
        savePastRun(formData);
    }
}

/** Regenerate a single document by key, then restore all checkboxes. */
async function regenerateSingleDoc(docKey) {
    await runGeneration([docKey]);
}

export function setupGenerate() {
    $("#generate-btn").addEventListener("click", function() {
        runGeneration();
    });

    // Generate Again button
    $("#generate-again-btn").addEventListener("click", function() {
        hide($("#results-area"));
        hide($("#success-banner"));
        $$('input[name="doc_select"]').forEach(function(el) { el.checked = true; });
    });

    // Download-all button
    $("#download-zip-btn").addEventListener("click", function() {
        window.location.href = api.zip_url();
    });
}
