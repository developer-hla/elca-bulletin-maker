/* Bulletin Maker — Authentication */

import { $, $$, show, hide, showError, hideError, showWarning } from "./dom.js";
import { state } from "./state.js";
import { api } from "./api.js";
import { showSettingsPanel } from "./settings.js";
import { resetAll } from "./wizard.js";
import { loadPastRuns } from "./past-runs.js";

/** Shows login overlay when session expires. Returns true if auth error was handled. */
export function handleAuthError(result) {
    if (!result || !result.auth_error) return false;
    show($("#login-overlay"));
    showAuthForm("#login-form");
    showError($("#login-error"), "Session expired. Please sign in again.");
    $("#login-btn").disabled = false;
    return true;
}

// ── Login ────────────────────────────────────────────────────────────

function _authForms() {
    return [$("#login-form"), $("#register-form"), $("#join-form")];
}

function showAuthForm(id) {
    _authForms().forEach(function(f) { hide(f); });
    ["#login-error", "#register-error", "#join-error"].forEach(function(sel) {
        hideError($(sel));
    });
    hide($("#login-spinner"));
    show($(id));
}

/** Post-auth entry: reveal the app and personalize the header. */
function enterApp(auth) {
    hide($("#login-overlay"));
    show($("#app"));
    var user = auth.user || {};
    $("#user-display").textContent = user.display_name || user.email || "";
    $("#church-display").textContent = (auth.church && auth.church.name) || "";
    document.title = "Bulletin Maker — " + ((auth.church && auth.church.name) || "");
    state.isAdmin = user.role === "admin";
    state.snsLinked = !!auth.sns_linked;
    loadChurchLabels();
    if (!state.snsLinked) {
        showWarning($("#date-warning"),
            state.isAdmin
                ? "No Sundays & Seasons account is linked yet — open Settings to link one before fetching content."
                : "No Sundays & Seasons account is linked yet — ask your church admin to link one under Settings.");
    }
    loadPastRuns();
}

/** Cache the church's setting/paper labels for the review outline. */
export async function loadChurchLabels() {
    var result = await api.get_church();
    if (!result.success) return;
    var profile = result.profile || {};
    function labelFor(options, key) {
        var found = (options || []).filter(function(o) { return o.key === key; })[0];
        return found ? found.label : key;
    }
    state.settingLabel = labelFor(result.options.liturgical_setting,
                                  profile.liturgical_setting);
    state.paperLabel = labelFor(result.options.paper_size, profile.paper_size);
}

export async function initAuth() {
    var who = await api.whoami();
    if (who.success && who.authenticated) {
        enterApp(who);
        return;
    }
    // Show the registration-code field only when this server requires it
    var info = await api.instance_info();
    if (info.success && info.has_churches) {
        show($("#register-code-field"));
    }
}

async function _submitAuth(action, errorEl, form) {
    hideError(errorEl);
    hide(form);
    show($("#login-spinner"));
    var result = await action();
    hide($("#login-spinner"));
    if (result && result.success) {
        enterApp(result);
    } else {
        show(form);
        showError(errorEl, (result && result.error) || "Something went wrong.");
    }
}

export function setupAuth() {
    $("#show-register-link").addEventListener("click", function(e) {
        e.preventDefault();
        showAuthForm("#register-form");
    });
    $("#show-join-link").addEventListener("click", function(e) {
        e.preventDefault();
        showAuthForm("#join-form");
    });
    $$(".show-login-link").forEach(function(link) {
        link.addEventListener("click", function(e) {
            e.preventDefault();
            showAuthForm("#login-form");
        });
    });

    $("#login-form").addEventListener("submit", function(e) {
        e.preventDefault();
        var email = $("#login-email").value.trim();
        var password = $("#login-password").value;
        if (!email || !password) return;
        _submitAuth(function() { return api.login(email, password); },
                    $("#login-error"), $("#login-form"));
    });

    $("#register-form").addEventListener("submit", function(e) {
        e.preventDefault();
        _submitAuth(function() {
            return api.register({
                church_name: $("#register-church").value.trim(),
                display_name: $("#register-name").value.trim(),
                email: $("#register-email").value.trim(),
                password: $("#register-password").value,
                registration_code: $("#register-code").value.trim(),
            });
        }, $("#register-error"), $("#register-form"));
    });

    $("#join-form").addEventListener("submit", function(e) {
        e.preventDefault();
        _submitAuth(function() {
            return api.join({
                invite_code: $("#join-code").value.trim(),
                display_name: $("#join-name").value.trim(),
                email: $("#join-email").value.trim(),
                password: $("#join-password").value,
            });
        }, $("#join-error"), $("#join-form"));
    });
}

export function setupLogout() {
    $("#logout-link").addEventListener("click", async function(e) {
        e.preventDefault();
        if (!confirm("Log out? Any unsaved work will be lost.")) return;
        await api.logout();
        // Show the auth overlay again
        show($("#login-overlay"));
        hide($("#app"));
        showSettingsPanel(false);
        showAuthForm("#login-form");
        $("#login-email").value = "";
        $("#login-password").value = "";
        $("#login-btn").disabled = false;

        // Reset state
        resetAll();
    });
}
