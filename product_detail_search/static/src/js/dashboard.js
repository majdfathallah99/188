/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/* ------- Kiosk behavior knobs ------- */
const KIOSK = {
    autoFocus: true,            // focus input on load/clear
    selectOnFocus: false,       // select input text when focusing (nice on touch screens)
    submitOnEnter: true,        // Enter still works (many scanners send it)
    clearInputOnSuccess: true,  // <-- NEW: empty the input after each successful fetch
    clearAfterMs: 5000,         // clear the result tiles after N ms (0 = keep)
    beepOnSuccess: true,        // short beep after showing a product
};

/* ------- Auto-search knobs ------- */
const AUTO = {
    enabled: true,              // fire search automatically as text streams in
    debounceMs: 180,            // wait this long after last keystroke
    minLength: 3,               // ignore very short strings
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

        this._debTimer = null;
        this._clearTimer = null;
        this._fetching = false;
        this._silenceInput = false; // <-- NEW: prevents our own programmatic clears from re-triggering search

        onMounted(() => {
            const focus = (select = KIOSK.selectOnFocus) => {
                const el = this.el?.querySelector?.(".pds__input");
                if (!el) return;
                el.focus();
                if (select) {
                    // select all without scrolling caret into view
                    try { el.setSelectionRange(0, el.value.length, "forward"); } catch {}
                }
            };
            this._focusInput = focus;
            if (KIOSK.autoFocus) focus();

            // Auto-search wiring
            this._onInput = () => {
                if (this._silenceInput) return; // ignore events caused by our own clears
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

            // Keep Enter support for scanners that append it
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
        if ((this.state.query || "").trim() !== value.trim()) return; // user kept typing
        await this._fetchAndRender(value);
    }

    async onSearch(ev) {
        ev?.preventDefault?.();
        const scan = (this.state.query || "").trim();
        if (!scan) {
            this.notification.add("اكتب أو امسح باركود أولاً", { type: "warning" });
            return;
        }
        await this._fetchAndRender(scan);
    }

    async _fetchAndRender(scan) {
        if (this._fetching) return; // avoid overlapping requests
        this._fetching = true;
        this.state.loading = true;
        clearTimeout(this._clearTimer);

        try {
            // 1) main RPC (unit card + identity)
            let details = await this.orm.call("product.template", "product_detail_search", [scan]);
            if (!details || typeof details !== "object") {
                this.notification.add("لم يتم العثور على المنتج.", { type: "warning" });
                return;
            }

            // 2) enrich تعبئة from UoM Price lines (if missing)
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

            // 4) render
            this.state.details = details;
            if (KIOSK.beepOnSuccess) beep();

            // 5) NEW: clear input immediately for next scan (keep tiles on screen)
            if (KIOSK.clearInputOnSuccess) {
                this._silenceInput = true;
                this.state.query = "";        // wipe the field
                this._focusInput?.();         // keep focus for next scan
                // allow input events again on next tick
                setTimeout(() => { this._silenceInput = false; }, 0);
            }

            // 6) auto-clear tiles after a while (optional)
            if (KIOSK.clearAfterMs) {
                this._clearTimer = setTimeout(() => {
                    this.state.details = null;
                    if (!KIOSK.clearInputOnSuccess) {
                        this._silenceInput = true;
                        this.state.query = "";
                        setTimeout(() => { this._silenceInput = false; }, 0);
                    }
                    if (KIOSK.autoFocus) this._focusInput?.();
                }, KIOSK.clearAfterMs);
            }
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
