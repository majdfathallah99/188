/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ProductDetailDashboard extends Component {
    static template = "product_detail_search.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ loading: false, details: null, query: "" });
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

    // Fetch normal details, then enrich تعبئة from UoM Price lines (if missing).
    async _fetchAndRender(scan) {
        this.state.loading = true;
        this.state.details = null;

        try {
            let details = await this.orm.call("product.template", "product_detail_search", [scan]);
            if (!details || typeof details !== "object") {
                this.notification.add("لم يتم العثور على المنتج.", { type: "warning" });
                return;
            }

            // Fill تعبئة data from UoM Price helper if server didn't include it
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
                        details.package_qty = payload.package_qty;
                        details.package_price = payload.package_price;
                        details.package_name = payload.package_name;
                    }
                }
            } catch (e) {
                // don't block unit card
                console.warn("[product_detail_search] pack enrich failed:", e);
            }

            // Precompute the small subtitles so the template stays clean
            details._unit_sub = `${details.currency_symbol || ""} – ${details.uom_name || ""}`;
            details._pack_sub = details.package_qty
                ? `${details.uom_name || ""} ${details.package_qty} ×`
                : "";

            this.state.details = details;
        } catch (err) {
            console.error(err);
            this.notification.add("تعذر جلب البيانات. تحقق من الاتصال أو الصلاحيات.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }
}

// Register under the action tag your menu opens
registry.category("actions").add("product_detail_search_barcode_main_menu", ProductDetailDashboard);
// Optional legacy alias
registry.category("actions").add("product_detail_search.dashboard", ProductDetailDashboard);

export default ProductDetailDashboard;
