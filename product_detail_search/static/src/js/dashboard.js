/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/* ---- Kiosk behavior ---- */
const KIOSK = {
    autoFocus: true,            // keep caret in the field
    selectOnFocus: false,
    submitOnEnter: false,       // Enter not required anymore
    clearInputOnSuccess: true,  // <-- clear ONLY the barcode field after a hit
    clearAfterMs: 0,            // <-- NEVER clear the result tiles automatically
    beepOnSuccess: true,
};

/* ---- Auto-search (fires as you scan/type) ---- */
const AUTO = {
    enabled: true,
    debounceMs: 60,             // tiny wait to group bursty barcode keystrokes
    minLength: 1,               // start searching as soon as there’s any input
};

function beep(ms = 120, freq = 880) {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = "sine";
        osc.frequency.value = freq;
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start();
        setTimeout(() => { osc.stop(); ctx.close(); }, ms);
    } catch { /* ignore */ }
}

export class ProductDetailDashboard extends Component {
    static template = "product_detail_search.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ loading: false, details: null, query: "" });

        this._debTimer   = null;
        this._fetching   = false;
        this._clearTimer = null;
        this._silenceInput = false; // don’t re-trigger search when we clear programmatically

        onMounted(() => {
            const focus = (select = KIOSK.selectOnFocus) => {
                const el = this.el?.querySelector?.(".pds__input");
                if (!el) return;
                el.focus();
                if (select) {
                    try { el.setSelectionRange(0, el.value.length, "forward"); } catch {}
                }
            };
            this._focusInput = focus;
            if (KIOSK.autoFocus) focus();

            // Auto-search
            this._onInput = () => {
                if (this._silenceInput) return;
                const v = (this.state.query || "").trim();
                clearTimeout(this._debTimer);
                if (AUTO.enabled && v.length >= AUTO.minLength) {
                    this._debTimer = setTimeout(() => this._autoSearch(v), AUTO.debounceMs);
                }
            };
            this._onPaste = () => this._onInput();

            this._inputEl = this.el?.querySelector?.(".pds__input");
            this._inputEl?.addEventListener?.("input", this._onInput);
            this._inputEl?.addEventListener?.("paste", this._onPaste);

            // Optional: keep Enter support (not required)
            this._keydown = (ev) => {
                if (KIOSK.submitOnEnter && ev.key === "Enter") {
                    ev.preventDefault();
                    this.onSearch(ev);
                }
            };
            window.addEventListener("keydown", this._keydown);
        });

        onWillUnmount(() => {
            window.removeEventListener("keydown", this._keydown || (()=>{}));
            this._inputEl?.removeEventListener?.("input", this._onInput || (()=>{}));
            this._inputEl?.removeEventListener?.("paste", this._onPaste || (()=>{}));
            clearTimeout(this._debTimer);
            clearTimeout(this._clearTimer);
        });
    }

    async _autoSearch(value) {
        // ignore if the user kept typing since the debounce started
        if ((this.state.query || "").trim() !== value.trim()) return;
        await this._fetchAndRender(value);
    }

    async onSearch(ev) {
        ev?.preventDefault?.();
        const scan = (this.state.query || "").trim();
        if (!scan) return;
        await this._fetchAndRender(scan);
    }

    async _fetchAndRender(scan) {
        if (this._fetching) return; // prevent overlapping calls on fast scans
        this._fetching = true;
        this.state.loading = true;

        try {
            // 1) main RPC
            let details = await this.orm.call("product.template", "product_detail_search", [scan]);
            if (!details || typeof details !== "object") {
                this.notification.add("لم يتم العثور على المنتج.", { type: "warning" });
                return;
            }

            // 2) enrich تعبئة if server didn’t provide it
            try {
                if (!(details.package_qty && details.package_price)) {
                    const pid = details.product_id || null;
                    const ptid = details.product_tmpl_id || null;
                    const payload = await this.orm.call("product.template", "uom_pack_from_lines", [pid, ptid], {});
                    if (payload?.has_pack) {
                        details.package_qty  = payload.package_qty;
                        details.package_price = payload.package_price;
                        details.package_name  = payload.package_name;
                    }
                }
            } catch (e) {
                console.warn("[price-checker] pack enrich failed:", e);
            }

            // 3) subtitles for UI
            details._unit_sub = `${details.currency_symbol || ""} – ${details.uom_name || ""}`;
            details._pack_sub = details.package_qty ? `${details.uom_name || ""} ${details.package_qty} ×` : "";

            // 4) render the tiles (and keep them on screen)
            this.state.details = details;
            if (KIOSK.beepOnSuccess) beep();

            // 5) clear ONLY the input so next scan is immediate
            if (KIOSK.clearInputOnSuccess) {
                this._silenceInput = true;
                this.state.query = "";
                // allow the input event loop to settle, then accept events again
                setTimeout(() => { this._silenceInput = false; }, 0);
            }
            if (KIOSK.autoFocus) this._focusInput?.();
        } catch (err) {
            console.error(err);
            this.notification.add("تعذر جلب البيانات. تحقق من الاتصال أو الصلاحيات.", { type: "danger" });
        } finally {
            this.state.loading = false;
            this._fetching = false;
        }
    }
}

registry.category("actions").add("product_detail_search_barcode_main_menu", ProductDetailDashboard);
registry.category("actions").add("product_detail_search.dashboard", ProductDetailDashboard);
export default ProductDetailDashboard;
