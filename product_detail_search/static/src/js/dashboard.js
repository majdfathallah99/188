/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

// --- Kiosk options ---
const KIOSK = {
    autoFocus: true,          // focus the input when the screen loads
    submitOnEnter: true,      // most scanners send Enter
    clearAfterMs: 5000,       // auto-clear result after 5s (set 0/false to disable)
    beepOnSuccess: true,      // play a short beep when a product is shown
};

// tiny WebAudio beep (does nothing if AudioContext blocked)
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

        // lifecycle: focus, global Enter, cleanup
        onMounted(() => {
            if (KIOSK.autoFocus) {
                this.el?.querySelector?.(".pds__input")?.focus();
            }
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
            clearTimeout(this._clearT);
        });
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
        this.state.loading = true;
        this.state.details = null;
        clearTimeout(this._clearT);

        try {
            // 1) main RPC
            let details = await this.orm.call("product.template", "product_detail_search", [scan]);
            if (!details || typeof details !== "object") {
                this.notification.add("لم يتم العثور على المنتج.", { type: "warning" });
                return;
            }

            // 2) enrich تعبئة from UoM Price lines (if server didn’t provide them)
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

            // 3) subtitles for pretty UI
            details._unit_sub = `${details.currency_symbol || ""} – ${details.uom_name || ""}`;
            details._pack_sub = details.package_qty ? `${details.uom_name || ""} ${details.package_qty} ×` : "";

            // 4) render and beep
            this.state.details = details;
            if (KIOSK.beepOnSuccess) beep();

            // 5) auto-clear
            if (KIOSK.clearAfterMs) {
                this._clearT = setTimeout(() => {
                    this.state.details = null;
                    this.state.query = "";
                    if (KIOSK.autoFocus) this.el?.querySelector?.(".pds__input")?.focus();
                }, KIOSK.clearAfterMs);
            }
        } catch (err) {
            console.error(err);
            this.notification.add("تعذر جلب البيانات. تحقق من الاتصال أو الصلاحيات.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }
}

registry.category("actions").add("product_detail_search_barcode_main_menu", ProductDetailDashboard);
registry.category("actions").add("product_detail_search.dashboard", ProductDetailDashboard);
export default ProductDetailDashboard;
