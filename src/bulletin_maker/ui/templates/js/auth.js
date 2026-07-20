/* Bulletin Maker — Authentication */

import { $, $$, show, hide, showError, hideError, showWarning } from "./dom.js";
import { state } from "./state.js";
import { api } from "./api.js";
import { showSettingsPanel } from "./settings.js";
import { resetAll } from "./wizard.js";
import { loadPastRuns } from "./past-runs.js";
import { loadRiteOptions } from "./readings.js";

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
    return [$("#login-form"), $("#register-form"), $("#join-form"),
            $("#recover-form"), $("#reset-form")];
}

function showAuthForm(id) {
    _authForms().forEach(function(f) { hide(f); });
    ["#login-error", "#register-error", "#join-error",
     "#recover-error", "#reset-error"].forEach(function(sel) {
        hideError($(sel));
    });
    hide($("#login-info"));
    hide($("#login-spinner"));
    show($(id));
}

function showLoginWith(message, isError) {
    showAuthForm("#login-form");
    if (!message) return;
    if (isError) {
        showError($("#login-error"), message);
    } else {
        $("#login-info").textContent = message;
        show($("#login-info"));
    }
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
    $("#operator-link").hidden = !auth.operator;
    loadChurchLabels();
    loadRiteOptions();
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

// ── Emailed link tokens (#reset= / #magic= / #verify=) ──────────────

var resetToken = null;

function _takeHashToken() {
    var match = /^#(reset|magic|verify)=([A-Za-z0-9_-]+)$/.exec(
        window.location.hash);
    if (!match) return null;
    // Drop the token from the URL so it doesn't linger in history
    history.replaceState(null, "", window.location.pathname);
    return { kind: match[1], token: match[2] };
}

function _overlayVisible() {
    return !$("#login-overlay").hidden;
}

/** Returns true when the token flow already decided what to show. */
async function _handleHashToken() {
    var found = _takeHashToken();
    if (!found) return false;
    if (found.kind === "magic") {
        var result = await api.consume_magic_link(found.token);
        if (result.success) {
            enterApp(result);
        } else if (_overlayVisible()) {
            // Signed-in users can ignore a stale sign-in link
            showLoginWith(result.error ||
                "This sign-in link is invalid or has expired.", true);
        }
        return true;
    }
    if (found.kind === "reset") {
        // Resetting invalidates every session, so force the auth card
        resetToken = found.token;
        hide($("#app"));
        show($("#login-overlay"));
        showAuthForm("#reset-form");
        return true;
    }
    var verified = await api.verify_email(found.token);
    if (_overlayVisible()) {
        showLoginWith(verified.success
            ? "Email verified — you can sign in."
            : (verified.error || "This verification link is invalid or has expired."),
            !verified.success);
    }
    return false;   // verification still falls through to a whoami check
}

export async function initAuth() {
    if (await _handleHashToken()) return;
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

var recoverMode = "reset";

function _openRecoverForm(mode) {
    recoverMode = mode;
    showAuthForm("#recover-form");
    hide($("#recover-sent"));
    $("#recover-btn").disabled = false;
    $("#recover-hint").textContent = mode === "reset"
        ? "Enter your email and we'll send you a password-reset link."
        : "Enter your email and we'll send you a one-time sign-in link — no password needed.";
    $("#recover-btn").textContent = mode === "reset"
        ? "Send Reset Link" : "Send Sign-In Link";
    $("#recover-email").value = $("#login-email").value.trim();
}

export function setupAuth() {
    // Emailed links opened in an already-loaded tab only change the hash
    window.addEventListener("hashchange", function() { _handleHashToken(); });

    $("#show-recover-link").addEventListener("click", function(e) {
        e.preventDefault();
        _openRecoverForm("reset");
    });
    $("#show-magic-link").addEventListener("click", function(e) {
        e.preventDefault();
        _openRecoverForm("magic");
    });
    $("#recover-form").addEventListener("submit", async function(e) {
        e.preventDefault();
        var email = $("#recover-email").value.trim();
        if (!email) return;
        hideError($("#recover-error"));
        $("#recover-btn").disabled = true;
        var send = recoverMode === "reset"
            ? api.forgot_password : api.request_magic_link;
        var result = await send(email);
        if (result.success) {
            show($("#recover-sent"));
        } else {
            $("#recover-btn").disabled = false;
            showError($("#recover-error"),
                      result.error || "Something went wrong — try again.");
        }
    });
    $("#reset-form").addEventListener("submit", async function(e) {
        e.preventDefault();
        var password = $("#reset-password").value;
        if (password.length < 8) return;
        hideError($("#reset-error"));
        $("#reset-btn").disabled = true;
        var result = await api.reset_password(resetToken, password);
        $("#reset-btn").disabled = false;
        if (result.success) {
            resetToken = null;
            $("#reset-password").value = "";
            showLoginWith("Password updated — sign in with your new password.");
        } else {
            showError($("#reset-error"),
                      result.error || "This reset link is invalid or has expired.");
        }
    });

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
