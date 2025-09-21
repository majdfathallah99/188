/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

/**
 * Backend "Find Product" dashboard.
 * - Fetches product details (unit card).
 * - Enriches تعبئة card from UoM Price lines via uom_pack_from_lines.
 * - Registers under the exact client-action tag your menu uses:
 *   "product_detail_search_barcode_main_menu".
 */
export class ProductDetailDashboard extends Component {
    static template = "product_detail_search.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: false,
            details: null,
            query: "",
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
        try {
            // 1) Fetch as your module already does
            let details = await this.orm.call("product.template", "product_detail_search", [scan]);

            // 2) Always try to fill تعبئة from UoM Price lines if missing
            try {
                const hasPack = details && details.package_qty && details.package_price;
                if (!hasPack) {
                    const pid = details.product_id || null;
                    const ptid = details.product_tmpl_id || null;
                    const payload = await this.orm.call(
                        "product.template",
                        "uom_pack_from_lines",
                        [pid, ptid],
                        {}
                    );
                    if (payload?.has_pack) {
                        details.package_qty = payload.package_qty;     // e.g., 12
                        details.package_price = payload.package_price; // e.g., 72.0
                        details.package_name = payload.package_name;   // e.g., "Dozens"
                    }
                }
            } catch (e) {
                console.warn("Pack enrich failed:", e);
            }

            this.state.details = details;
        } catch (err) {
            console.error(err);
            this.notification.add("تعذر جلب البيانات. تحقق من الاتصال أو الصلاحيات.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }
}

// IMPORTANT: register under the SAME tag your menu/client action uses
registry.category("actions").add("product_detail_search_barcode_main_menu", ProductDetailDashboard);

// (Optional) keep a legacy alias if you used a different key before
registry.category("actions").add("product_detail_search.dashboard", ProductDetailDashboard);

export default ProductDetailDashboard;
