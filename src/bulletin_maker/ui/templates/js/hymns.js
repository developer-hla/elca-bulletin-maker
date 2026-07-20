/* Bulletin Maker — Hymn fetching */

import { $, $$, show, hide, showError, hideError, showBtnSpinner, hideBtnSpinner } from "./dom.js";
import { state } from "./state.js";
import { api } from "./api.js";

// ── Hymn Fetching ────────────────────────────────────────────────────

/** Build verse checkbox HTML for a hymn with the given verse count. */
function buildVerseCheckboxes(slotName, verseCount) {
    var html = '<span class="verse-label">Verses:</span>';
    for (var i = 1; i <= verseCount; i++) {
        var id = "verse-" + slotName + "-" + i;
        html += '<label class="verse-cb-label" for="' + id + '">' +
            '<input type="checkbox" id="' + id + '" value="' + i + '" checked> ' + i +
            '</label>';
    }
    return html;
}

/** Read which verse checkboxes are checked in a slot's .verse-select container. */
function getSelectedVerses(slot) {
    var checks = slot.querySelectorAll(".verse-select input[type=checkbox]:checked");
    var selected = [];
    checks.forEach(function(cb) { selected.push(parseInt(cb.value, 10)); });
    return selected;
}

/** Show verse checkboxes for a hymn slot after successful lyrics fetch. */
function showVerseSelect(slot, slotName, verseCount) {
    var container = slot.querySelector(".verse-select");
    container.innerHTML = buildVerseCheckboxes(slotName, verseCount);
    show(container);
    // Wire checkbox changes to update state
    container.querySelectorAll("input[type=checkbox]").forEach(function(cb) {
        cb.addEventListener("change", function() {
            var hymn = state.hymns[slotName];
            if (hymn) {
                hymn.selectedVerses = getSelectedVerses(slot);
            }
        });
    });
}

function clearHymnSlot(slot) {
    var slotName = slot.dataset.slot;
    state.hymns[slotName] = null;
    slot.querySelector(".hymn-number").value = "";
    var infoEl = slot.querySelector(".hymn-info");
    infoEl.textContent = "";
    hide(infoEl);
    hideError(slot.querySelector(".hymn-error"));
    var verseEl = slot.querySelector(".verse-select");
    verseEl.innerHTML = "";
    hide(verseEl);
    var clearBtn = slot.querySelector(".hymn-clear-btn");
    if (clearBtn) hide(clearBtn);
}

export function setupFetchAllHymns() {
    $("#fetch-all-hymns-btn").addEventListener("click", async function() {
        var slots = $$(".hymn-slot");
        var toFetch = [];
        slots.forEach(function(slot) {
            var number = slot.querySelector(".hymn-number").value.trim();
            if (number) toFetch.push(slot);
        });
        if (toFetch.length === 0) return;

        showBtnSpinner(this);
        for (var i = 0; i < toFetch.length; i++) {
            await fetchHymnSlot(toFetch[i]);
        }
        hideBtnSpinner(this, "Fetch All Hymns");
    });
}

/** Fetch one hymn slot's title + lyrics. Callable directly (Fetch All,
    past-run restore) or from the per-slot button — no click simulation. */
async function fetchHymnSlot(slot) {
    const slotName = slot.dataset.slot;
    const numberInput = slot.querySelector(".hymn-number");
    const collection = slot.querySelector(".hymn-collection").value;
    const errorEl = slot.querySelector(".hymn-error");
    const infoEl = slot.querySelector(".hymn-info");
    const fetchBtn = slot.querySelector(".hymn-fetch-btn");
    const clearBtn = slot.querySelector(".hymn-clear-btn");
    const number = numberInput.value.trim();

    if (!number) {
        showError(errorEl, "Enter a hymn number from the hymnal's index.");
        hide(infoEl);
        return;
    }

    hideError(errorEl);
    infoEl.textContent = "";
    hide(infoEl);
    if (clearBtn) hide(clearBtn);
    state.hymns[slotName] = null;
    showBtnSpinner(fetchBtn);

    try {
        // One call: the server merges search + lyrics fetch
        const result = await api.search_hymn(number, collection);
        hideBtnSpinner(fetchBtn, "Fetch");

        if (!result.success) {
            showError(errorEl, result.error ||
                "Hymn not found. Check the number and make sure the right hymnal is selected.");
            return;
        }

        if (result.lyrics_unavailable) {
            infoEl.textContent = result.title + " (title only — no lyrics available)";
            show(infoEl);
            if (clearBtn) show(clearBtn);
            state.hymns[slotName] = {
                number: number,
                collection: collection,
                title: result.title,
                hasLyrics: false,
            };
            return;
        }

        infoEl.textContent = result.title +
            " — " + result.verse_count + " verse(s)" +
            (result.has_refrain ? " + refrain" : "");
        show(infoEl);
        if (clearBtn) show(clearBtn);
        var allVerses = [];
        for (var vi = 1; vi <= result.verse_count; vi++) allVerses.push(vi);
        state.hymns[slotName] = {
            number: number,
            collection: collection,
            title: result.title,
            hasLyrics: result.verse_count > 0,
            verseCount: result.verse_count,
            selectedVerses: allVerses,
        };
        if (result.verse_count > 1) {
            showVerseSelect(slot, slotName, result.verse_count);
        }
    } catch (err) {
        hideBtnSpinner(fetchBtn, "Fetch");
        showError(errorEl, "Failed to fetch hymn: " + (err.message || "unknown error"));
    }
}

export function setupHymnFetch() {
    // Clear buttons
    $$(".hymn-clear-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            clearHymnSlot(this.closest(".hymn-slot"));
        });
    });

    $$(".hymn-fetch-btn").forEach(function(btn) {
        btn.addEventListener("click", function() {
            fetchHymnSlot(this.closest(".hymn-slot"));
        });
    });
}

export async function restoreHymns(fd) {
    var slots = ["gathering", "sermon", "communion", "sending"];
    for (var i = 0; i < slots.length; i++) {
        var slot = slots[i];
        var hymnData = fd[slot + "_hymn"];
        if (!hymnData || !hymnData.number) continue;

        var slotEl = document.querySelector('.hymn-slot[data-slot="' + slot + '"]');
        if (!slotEl) continue;

        slotEl.querySelector(".hymn-number").value = hymnData.number;
        var collectionSelect = slotEl.querySelector(".hymn-collection");
        if (collectionSelect && hymnData.collection) {
            collectionSelect.value = hymnData.collection;
        }

        await fetchHymnSlot(slotEl);

        // Restore verse selection if applicable
        if (hymnData.selected_verses && state.hymns[slot] && state.hymns[slot].verseCount) {
            var verseChecks = slotEl.querySelectorAll(".verse-select input[type=checkbox]");
            verseChecks.forEach(function(cb) {
                var v = parseInt(cb.value, 10);
                cb.checked = hymnData.selected_verses.indexOf(v) !== -1;
            });
            state.hymns[slot].selectedVerses = hymnData.selected_verses.slice();
        }
    }
}
