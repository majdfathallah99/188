/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/* ---------- Scanner behavior (lifted from the working module) ---------- */
const SCAN_DEBOUNCE_MS = 220;  // wait this long after the last keystroke
const SCAN_MIN_LEN     = 2;    // ignore too-short noise

export class ProductDetailDashboard extends Component {
    static template = "product_detail_search.Dashboard";

    // scanner state / timers
    _timer = null;
    _mounted = false;
    _onGlobalKeydown = null;
    _silenceInput = false; // prevents our own clears from re-triggering search

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        // barcode: the live buffer; details: current product payload
        this.state = useState({ loading: false, barcode: "", details: null });
    }

    /* ---------------- lifecycle: autofocus + global scanner capture ---------------- */
    onMountedCallback() {
        this._mounted = true;

        // Aggressive autofocus so you can scan immediately after opening the action
        this._focus();
        setTimeout(() => this._focus(), 0);
        setTimeout(() => this._focus(), 120);
        requestAnimationFrame(() => this._focus());

        // Capture barcode streams even if the input isn’t focused
        this._onGlobalKeydown = (ev) => this._handleGlobalKeydown(ev);
        document.addEventListener("keydown", this._onGlobalKeydown, { capture: true });
    }

    onWillUnmountCallback() {
        this._mounted = false;
        document.removeEventListener("keydown", this._onGlobalKeydown, { capture: true });
        clearTimeout(this._timer);
    }

    // Owl hooks
    setupLifecycleOnce = (() => {
        onMounted(() => this.onMountedCallback());
        onWillUnmount(() => this.onWillUnmountCallback());
        return true;
    })();

    /* ---------------- DOM helpers & input handlers ---------------- */
    _focus() {
        // Prefer a ref set in XML; fallback to common selectors
        const el = this.refs?.scanInput
            || this.el?.querySelector?.(".pds__input, .scan-input, input[type='text']");
        if (!el) return;
        try { el.focus({ preventScroll: true }); } catch { /* ignore */ }
    }

    // If your input is focused and user types/pastes there
    onInput(ev) {
        if (this._silenceInput) return;
        this.state.barcode = (ev.target.value || "").trim();
        this._scheduleLookup();
    }

    onKeyDown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this._fireLookup();
        }
    }

    /* ---------------- Global scanner buffer (works without focusing the field) ---------------- */
    _handleGlobalKeydown(ev) {
        if (!this._mounted) return;

        // Ignore when user is typing in another real input/textarea/contentEditable
        const t = ev.target;
        const inTypingField =
            (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) || t?.isContentEditable;
        if (inTypingField || ev.ctrlKey || ev.altKey || ev.metaKey) return;

        if (ev.key === "Enter") {
            ev.preventDefault();
            this._fireLookup();
            return;
        }
        if (ev.key === "Backspace") {
            this.state.barcode = (this.state.barcode || "").slice(0, -1);
            return;
        }
        if (ev.key && ev.key.length === 1) {
            this.state.barcode = (this.state.barcode || "") + ev.key;
            this._scheduleLookup();
        }
    }

    _scheduleLookup() {
        clearTimeout(this._timer);
        const term = (this.state.barcode || "").trim();
        if (term.length < SCAN_MIN_LEN) return;
        this._timer = setTimeout(() => this._fireLookup(), SCAN_DEBOUNCE_MS);
    }

    async _fireLookup() {
        clearTimeout(this._timer);
        const term = (this.state.barcode || "").trim();
        if (!term || term.length < SCAN_MIN_LEN) return;

        // Clear ONLY the input for the next scan; keep the tiles visible
        this._silenceInput = true;
        this.state.barcode = "";
        setTimeout(() => { this._silenceInput = false; }, 0);

        await this._fetchAndRender(term);
        this._focus(); // stay hands-free for the next scan
    }

    /* ---------------- Your existing fetch flow (kept intact) ---------------- */
    async _fetchAndRender(scan) {
        this.state.loading = true;
        try {
            // 1) Fetch main details
            let details = await this.orm.call("product.template", "product_detail_search", [scan]);
            if (!details || typeof details !== "object") {
                this.notification.add("لم يتم العثور على المنتج.", { type: "warning" });
                return;
            }

            // 2) Enrich تعبئة from UoM Price lines if missing
            try {
                if (!(details.package_qty && details.package_price)) {
                    const pid = details.product_id || null;
                    const ptid = details.product_tmpl_id || null;
                    const payload = await this.orm.call(
                        "product.template",
                        "uom_pack_from_lines",
                        [pid, ptid],
                        {}
                    );
                    if (payload?.has_pack) {
                        details.package_qty  = payload.package_qty;
                        details.package_price = payload.package_price;
                        details.package_name  = payload.package_name;
                    }
                }
            } catch (e) {
                console.warn("[product_detail_search] pack enrich failed:", e);
            }

            // 3) Prettify subtitles (same as before)
            details._unit_sub = `${details.currency_symbol || ""} – ${details.uom_name || ""}`;
            details._pack_sub = details.package_qty ? `${details.uom_name || ""} ${details.package_qty} ×` : "";

            this.state.details = details; // render two cards
        } catch (err) {
            console.error(err);
            this.notification.add("تعذر جلب البيانات. تحقق من الاتصال أو الصلاحيات.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }
}

// Register under your action tag(s)
registry.category("actions").add("product_detail_search_barcode_main_menu", ProductDetailDashboard);
registry.category("actions").add("product_detail_search.dashboard", ProductDetailDashboard);

export default ProductDetailDashboard;
