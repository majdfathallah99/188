/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/* ------- Kiosk behavior knobs ------- */
const KIOSK = {
    autoFocus: true,          // focus input on load and after clear
    submitOnEnter: true,      // keep Enter support (most scanners send it)
    clearAfterMs: 5000,       // clear result + input after N ms (0 = disabled)
    beepOnSuccess: true,      // short beep when a product is displayed
};

/* ------- Auto-search knobs ------- */
const AUTO = {
    enabled: true,            // fire search automatically from input changes
    debounceMs: 180,          // wait this long after last keystroke
    minLength: 3,             // don’t search for very short strings
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

        onMounted(() => {
            const focusInput = () => this.el?.querySelector?.(".pds__input")?.focus();
            if (KIOSK.autoFocus) focusInput();

            // Auto-search wiring on the input element
            this._onInput = () => {
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

            // Optional: Enter key for scanners that send it
            this._keydown = (ev) => {
                if (KIOSK.submitOnEnter && ev.key === "Enter") {
                    ev.preventDefault();
                    this.onSearch(ev);
                }
            };
            window.addEventListener("keydown", this._keydown);

            // keep a handy method for later
            this._focusInput = focusInput;
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
        // If the user changed the field since the debounce started, don’t fire the old query
        if ((this.state.query || "").trim() !== value.trim()) return;
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
        if (this._fetching) return; // avoid overlapping requests on fast scans
        this._fetching = true;
        this.state.loading = true;
        this.state.details = null;
        clearTimeout(this._clearTimer);

        try {
            // 1) main RPC
            let details = await this.orm.call("product.template", "product_detail_search", [scan]);
            if (!details || typeof details !== "object") {
                this.notification.add("لم يتم العثور على المنتج.", { type: "warning" });
                return;
            }

            // 2) enrich تعبئة from UoM Price lines (if the server didn’t include them)
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

            // 4) render + beep
            this.state.details = details;
            if (KIOSK.beepOnSuccess) beep();

            // 5) auto-clear after a bit
            if (KIOSK.clearAfterMs) {
                this._clearTimer = setTimeout(() => {
                    this.state.details = null;
                    this.state.query = "";
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

// Register under your action tag(s)
registry.category("actions").add("product_detail_search_barcode_main_menu", ProductDetailDashboard);
registry.category("actions").add("product_detail_search.dashboard", ProductDetailDashboard);

export default ProductDetailDashboard;
