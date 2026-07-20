/* Bulletin Maker — Wizard UI entry point */

import { $ } from "./dom.js";
import { state } from "./state.js";
import { getNextSunday, setupNewBulletin, setupHelp, setupWizardNav, setupWizardStepKeys } from "./wizard.js";
import { setupA11y } from "./a11y.js";
import { setupAuth, setupLogout, initAuth } from "./auth.js";
import { setupSettings } from "./settings.js";
import { setupRiteEditor } from "./rite-editor.js";
import { setupOperator } from "./operator.js";
import { setupDateFetch, setupResetDefaults } from "./readings.js";
import { setupHymnFetch, setupFetchAllHymns } from "./hymns.js";
import { setupFilePickers, setupGenerate } from "./generate.js";
import { setupBaptismToggle, setupMemorialAcclamationModeToggle } from "./texts.js";
import { setupPastRuns } from "./past-runs.js";

// Back/refresh/close protection: a fetched-but-not-generated bulletin
// represents real volunteer effort — make the browser ask first.
window.addEventListener("beforeunload", function(e) {
    if (state.unsavedWork) {
        e.preventDefault();
        e.returnValue = "";
    }
});

document.addEventListener("DOMContentLoaded", function() {
    // Pre-fill date with next Sunday
    $("#date-input").value = getNextSunday();
    setupA11y();

    setupAuth();
    setupSettings();
    setupRiteEditor();
    setupOperator();
    setupLogout();
    setupNewBulletin();
    setupHelp();
    setupDateFetch();
    setupResetDefaults();
    setupHymnFetch();
    setupFetchAllHymns();
    setupFilePickers();
    setupGenerate();
    setupBaptismToggle();
    setupMemorialAcclamationModeToggle();
    setupPastRuns();
    setupWizardNav();
    setupWizardStepKeys();
    initAuth();
});
