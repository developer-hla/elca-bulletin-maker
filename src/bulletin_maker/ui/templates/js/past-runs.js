/* Bulletin Maker — Past Runs */

import { $, show, hide, showError, hideError, showWarning, hideWarning } from "./dom.js";
import { state } from "./state.js";
import { api } from "./api.js";
import { formatDate, showStep } from "./wizard.js";
import { handleDateFetchResult, applyRestoredSettings } from "./readings.js";
import { restoreHymns } from "./hymns.js";
import { restoreLiturgicalTextChoices } from "./texts.js";

// ── Past Runs ────────────────────────────────────────────────────────

export async function loadPastRuns() {
    var container = $("#past-runs-list");
    if (!container) return;
    container.innerHTML = "";

    try {
        var result = await api.get_past_runs();
        if (!result.success || !result.runs.length) {
            hide($("#past-runs-section"));
            return;
        }

        show($("#past-runs-section"));

        result.runs.forEach(function(run) {
            var item = document.createElement("div");
            item.className = "past-run-item";

            var info = document.createElement("button");
            info.type = "button";
            info.className = "past-run-load-btn";
            var meta = run.metadata || {};
            var label = meta.date_display || run.date || "Unknown";
            if (meta.day_name) label += " — " + meta.day_name;
            info.textContent = label;
            info.addEventListener("click", function() {
                restorePastRun(run.id);
            });
            item.appendChild(info);

            if (meta.hymn_summary) {
                var hymns = document.createElement("span");
                hymns.className = "past-run-hymns";
                hymns.textContent = meta.hymn_summary;
                item.appendChild(hymns);
            }

            var deleteBtn = document.createElement("button");
            deleteBtn.type = "button";
            deleteBtn.className = "btn-link past-run-delete";
            deleteBtn.textContent = "Delete";
            deleteBtn.addEventListener("click", function(e) {
                e.stopPropagation();
                deletePastRun(run.id, label);
            });
            item.appendChild(deleteBtn);

            container.appendChild(item);
        });
    } catch (_) {
        hide($("#past-runs-section"));
    }
}

async function deletePastRun(runId, label) {
    if (!confirm('Delete the saved run "' + (label || runId) + '"? This cannot be undone.')) {
        return;
    }
    var result = await api.delete_past_run(runId);
    if (!result.success) {
        showError($("#date-error"),
            "Could not delete that run: " + (result.error || "unknown error"));
        return;
    }
    loadPastRuns();
}

export async function savePastRun(formData) {
    var saveData = Object.assign({}, formData);
    delete saveData.selected_docs;
    delete saveData.cover_image;

    var hymnSummary = ["gathering", "sermon", "communion", "sending"]
        .map(function(slot) {
            var h = state.hymns[slot];
            return h && h.number ? h.collection + " " + h.number : "";
        })
        .filter(Boolean)
        .join(", ");

    var metadata = {
        date_display: state.dateDisplay,
        season: state.season,
        day_name: $("#day-name") ? $("#day-name").textContent : "",
        hymn_summary: hymnSummary,
    };

    var result = await api.save_past_run(saveData, metadata);
    if (!result.success) {
        showWarning($("#date-warning"),
            "The documents generated, but this run could not be saved to Past Runs.");
        return;
    }
    loadPastRuns();
}

async function restorePastRun(runId) {
    var result = await api.get_past_run(runId);
    if (!result.success) {
        showError($("#date-error"),
            "Could not load that past run: " + (result.error || "unknown error"));
        return;
    }

    var fd = result.form_data;

    // Set the date and trigger content fetch
    $("#date-input").value = fd.date;

    hideError($("#date-error"));
    hideWarning($("#date-warning"));
    hideWarning($("#content-warning"));
    hide($("#day-info"));
    var spinner = $("#date-spinner");
    show(spinner);
    $("#fetch-btn").disabled = true;

    var fetchResult = await api.fetch_day_content(fd.date, state.dateDisplay);

    hide(spinner);
    $("#fetch-btn").disabled = false;

    if (!fetchResult.success) {
        showError($("#date-error"), fetchResult.error || "Failed to fetch content for this date.");
        return;
    }

    state.dateStr = fd.date;
    state.dateDisplay = formatDate(fd.date);
    await handleDateFetchResult(fetchResult);

    // Overlay saved settings
    applyRestoredSettings(fd);

    // Restore hymns
    await restoreHymns(fd);

    // Restore liturgical text choices after texts have loaded
    restoreLiturgicalTextChoices(fd);

    showStep(1);
}

export function setupPastRuns() {
    var toggle = $("#past-runs-toggle");
    if (!toggle) return;
    toggle.addEventListener("click", function() {
        var list = $("#past-runs-list");
        var isOpen = !list.hidden;
        if (isOpen) {
            hide(list);
            toggle.innerHTML = "Past Runs &#9654;";
        } else {
            show(list);
            toggle.innerHTML = "Past Runs &#9660;";
        }
    });
}
