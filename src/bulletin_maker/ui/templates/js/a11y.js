/* Bulletin Maker — Accessibility wiring */

import { $, $$ } from "./dom.js";

export function setupA11y() {
    // Announce errors, warnings, and status changes to assistive tech
    $$(".error-msg").forEach(function(el) { el.setAttribute("role", "alert"); });
    $$(".warning-msg").forEach(function(el) { el.setAttribute("role", "status"); });
    $$(".spinner").forEach(function(el) { el.setAttribute("role", "status"); });
    var progressStatus = $("#progress-status");
    if (progressStatus) progressStatus.setAttribute("role", "status");

    // Associate the per-slot hymn labels with their inputs
    $$(".hymn-slot").forEach(function(slot) {
        var slotName = slot.dataset.slot;
        var numberInput = slot.querySelector(".hymn-number");
        var collectionSelect = slot.querySelector(".hymn-collection");
        numberInput.id = "hymn-number-" + slotName;
        collectionSelect.id = "hymn-collection-" + slotName;
        var labels = slot.querySelectorAll(".field label");
        if (labels[0]) labels[0].setAttribute("for", numberInput.id);
        if (labels[1]) labels[1].setAttribute("for", collectionSelect.id);
    });
}
