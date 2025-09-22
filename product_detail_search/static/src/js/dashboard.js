/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/* -------- Scanner behavior -------- */
const SCAN_DEBOUNCE_MS = 220;  // quiet time after last char before firing
const SCAN_MIN_LEN     = 2;    // ignore short noise

export class ProductDetailDashboard extends Component {
    static template = "product_detail_search.Dashboard";

    // timers / flags
    _timer = null;
    _fetching = false;
    _mounted = false;
    _onGlobalKeydown = null;
    _silenceInput = false; // don't retrigger search when we clear the field programmatically

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ loading: false, barcode: "", details: null });

        // Bind hooks once
        onMounted(() => this._onMountedCb());
        onWillUnmount(() => this._onWillUnmountCb());
    }

    /* ---------- lifecycle: autofocus + global keyboard capture ---------- */
    _onMountedCb() {
        this._mounted = true;

        // Aggressive autofocus so scanning works immediately
        this._focus();
        setTimeout(() => this._focus(), 0);
        setTimeout(() => this._focus(), 120);
        requestAnimationFrame(() => this._focus());

        // Capture barcode stream even if input loses focus
        this._onGlobalKeydown = (ev) => this._handleGlobalKeydown(ev);
        document.addEventListener("keydown", this._onGlobalKeydown, { capture: true });
    }
    _onWillUnmountCb() {
        this._mounted = false;
        document.removeEventListener("keydown", this._onGlobalKeydown, { capture: true });
        clearTimeout(this._timer);
    }

    /* ---------------- DOM helpers & input handlers ---------------- */
    _focus() {
        const el = this.refs?.scanInput
            || this.el?.querySelector?.(".pds__input, .scan-input, input[type='text']");
        if (!el) return;
        try { el.focus({ preventScroll: true }); } catch {}
    }

    // Fired when the scan input itself changes (typing or scanner in-field)
    onInput(ev) {
        if (this._silenceInput) return;
        this.state.barcode = (ev.target.value || "").trim();
        this._scheduleLookup();
    }
    // Optional: keep manual Enter working
    onKeyDown(ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            this._fireLookup();
        }
    }

    /* ---------------- Global scanner buffer ---------------- */
    _handleGlobalKeydown(ev) {
        if (!this._mounted) return;

        // Ignore real typing fields and modified keys
        const t = ev.target;
        const typing =
            (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) || t?.isContentEditable;
        if (typing || ev.ctrlKey || ev.altKey || ev.metaKey) return;

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

        // Clear ONLY the input so the next scan is clean; keep tiles visible
        this._silenceInput = true;
        this.state.barcode = "";
        setTimeout(() => { this._silenceInput = false; }, 0);

        await this._fetchAndRender(term);
        this._focus(); // hands-free for the next scan
    }

    /* ---------------- Fetch + enrich ---------------- */
    async _fetchAndRender(scan) {
        if (this._fetching) return;
        this._fetching = true;
        this.state.loading = true;
        try {
            // 1) main details
            let details = await this.orm.call("product.template", "product_detail_search", [scan]);
            if (!details || typeof details !== "object") {
                this.notification.add("لم يتم العثور على المنتج.", { type: "warning" });
                return;
            }

            // 2) تعبئة from UoM Price lines, if missing
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

            // 3) pretty subtitles + robust name for header
            details._unit_sub = `${details.currency_symbol || ""} – ${details.uom_name || ""}`;
            details._pack_sub = details.package_qty ? `${details.uom_name || ""} ${details.package_qty} ×` : "";
            details._name =
                details.product_display_name ||
                details.display_name ||
                details.name ||
                "";

            this.state.details = details; // render two cards + header
        } catch (err) {
            console.error(err);
            this.notification.add("تعذر جلب البيانات. تحقق من الاتصال أو الصلاحيات.", { type: "danger" });
        } finally {
            this.state.loading = false;
            this._fetching = false;
        }
    }
}

// Register under your action tag(s)
registry.category("actions").add("product_detail_search_barcode_main_menu", ProductDetailDashboard);
registry.category("actions").add("product_detail_search.dashboard", ProductDetailDashboard);

export default ProductDetailDashboard;
