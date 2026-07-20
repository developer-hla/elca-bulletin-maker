/* Bulletin Maker — Server API adapter */

import { state } from "./state.js";
import { handleAuthError } from "./auth.js";

// ── Server API adapter ───────────────────────────────────────────────
// Talks to the FastAPI backend. Method names mirror the old pywebview
// bridge so call sites read the same; failures resolve to
// {success:false, error, error_type, auth_error?} rather than throwing.
export var api = (function() {
    var lastDayResponse = null;
    var hymnCache = {};       // "COLL_NUM" -> merged hymn response
    var lastJobId = null;

    async function req(method, url, body) {
        var opts = { method: method, headers: {} };
        if (body !== undefined) {
            opts.headers["Content-Type"] = "application/json";
            opts.body = JSON.stringify(body);
        }
        var resp;
        try {
            resp = await fetch(url, opts);
        } catch (e) {
            if (method !== "GET") {
                return { success: false, error_type: "network",
                         error: "Cannot reach the Bulletin Maker server. Is it still running?" };
            }
            // Reads are safe to retry once — absorbs transient hiccups
            await new Promise(function(r) { setTimeout(r, 400); });
            try {
                resp = await fetch(url, opts);
            } catch (e2) {
                return { success: false, error_type: "network",
                         error: "Cannot reach the Bulletin Maker server. Is it still running?" };
            }
        }
        var data = null;
        try { data = await resp.json(); } catch (e) {}
        if (!resp.ok) {
            var detail = (data && data.detail) || {};
            var failure = {
                success: false,
                error: detail.error || ("Server error (HTTP " + resp.status + ")"),
                error_type: detail.error_type || "internal",
                auth_error: !!detail.auth_error,
            };
            // Expired sessions re-open the sign-in overlay from ANY call
            if (failure.auth_error) handleAuthError(failure);
            return failure;
        }
        if (data === null) {
            return { success: false, error_type: "internal",
                     error: "The server sent an unexpected response — please try again." };
        }
        return data;
    }

    var methods = {
        login: function(email, password) {
            return req("POST", "/api/session", { email: email, password: password });
        },
        register: function(payload) { return req("POST", "/api/register", payload); },
        join: function(payload) { return req("POST", "/api/join", payload); },
        whoami: function() { return req("GET", "/api/session"); },
        instance_info: function() { return req("GET", "/api/instance"); },
        logout: function() { return req("DELETE", "/api/session"); },
        forgot_password: function(email) {
            return req("POST", "/api/auth/forgot", { email: email });
        },
        reset_password: function(token, newPassword) {
            return req("POST", "/api/auth/reset",
                       { token: token, new_password: newPassword });
        },
        request_magic_link: function(email) {
            return req("POST", "/api/auth/magic", { email: email });
        },
        consume_magic_link: function(token) {
            return req("POST", "/api/auth/magic/consume", { token: token });
        },
        verify_email: function(token) {
            return req("POST", "/api/auth/verify", { token: token });
        },
        get_church: function() { return req("GET", "/api/church"); },
        update_church_profile: function(payload) {
            return req("PUT", "/api/church/profile", payload);
        },
        link_sns: function(username, password) {
            return req("PUT", "/api/church/sns-link",
                       { username: username, password: password });
        },
        get_preface_options: function() { return req("GET", "/api/prefaces"); },

        fetch_day_content: async function(dateStr, dateDisplay) {
            var result = await req("GET", "/api/day?date=" + encodeURIComponent(dateStr) +
                                   "&display=" + encodeURIComponent(dateDisplay));
            if (result.success) lastDayResponse = result;
            return result;
        },
        get_file_prefix: function() {
            if (lastDayResponse && lastDayResponse.prefix) {
                return Promise.resolve({ success: true, prefix: lastDayResponse.prefix });
            }
            return Promise.resolve({ success: false, error: "No content fetched yet.",
                                     error_type: "validation" });
        },
        get_liturgical_texts: function() { return req("GET", "/api/day/texts"); },
        get_reading_preview: function(slot) {
            return req("GET", "/api/day/readings/" + encodeURIComponent(slot) + "/preview");
        },
        fetch_custom_reading: function(citation) {
            return req("POST", "/api/passage", { citation: citation });
        },

        // The server merges search + lyrics into one endpoint; both old
        // bridge methods resolve from it (cached per hymn).
        search_hymn: async function(number, collection) {
            var result = await req("GET", "/api/hymns/" + encodeURIComponent(collection) +
                                   "/" + encodeURIComponent(number) +
                                   "?date=" + encodeURIComponent(state.dateStr || ""));
            if (result.success) {
                hymnCache[collection + "_" + number] = result;
            }
            return result;
        },

        save_past_run: function(formData, metadata) {
            return req("POST", "/api/runs", { form_data: formData, metadata: metadata });
        },
        get_past_runs: function() { return req("GET", "/api/runs"); },
        get_past_run: function(runId) { return req("GET", "/api/runs/" + encodeURIComponent(runId)); },
        delete_past_run: function(runId) { return req("DELETE", "/api/runs/" + encodeURIComponent(runId)); },

        upload_cover: async function(file) {
            var fd = new FormData();
            fd.append("file", file, file.name);
            var resp;
            try {
                resp = await fetch("/api/cover", { method: "POST", body: fd });
            } catch (e) {
                return { success: false, error: "Upload failed.", error_type: "network" };
            }
            var data = null;
            try { data = await resp.json(); } catch (e) {}
            if (!resp.ok) {
                var detail = (data && data.detail) || {};
                return { success: false, error: detail.error || "Upload failed.",
                         error_type: detail.error_type || "internal" };
            }
            return data;
        },

        generate_all: async function(formData, onProgress) {
            var start = await req("POST", "/api/generate", formData);
            if (!start.success) return start;
            lastJobId = start.job_id;
            var seen = 0;
            for (;;) {
                // Poll every 700ms; when a backgrounded tab returns to
                // focus, check immediately instead of waiting out the
                // browser's throttled timer.
                await new Promise(function(r) {
                    var timer = setTimeout(done, 700);
                    function done() {
                        clearTimeout(timer);
                        document.removeEventListener("visibilitychange", onVisible);
                        r();
                    }
                    function onVisible() {
                        if (!document.hidden) done();
                    }
                    document.addEventListener("visibilitychange", onVisible);
                });
                var status = await req("GET", "/api/jobs/" + lastJobId);
                if (!status.success) return status;
                (status.progress || []).slice(seen).forEach(function(entry) {
                    onProgress(entry);
                });
                seen = (status.progress || []).length;
                if (status.status !== "running") {
                    return { success: status.status === "done",
                             results: status.results, errors: status.errors };
                }
            }
        },
        file_url: function(docKey) {
            return "/api/jobs/" + lastJobId + "/files/" + encodeURIComponent(docKey);
        },
        zip_url: function() { return "/api/jobs/" + lastJobId + "/zip"; },
    };
    return methods;
})();
