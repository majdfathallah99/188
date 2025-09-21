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

    // Fetch as usual, then enrich تعبئة from UoM Price lines
    async _fetchAndRender(scan) {
        this.state.loading = true;
        try {
            let details = await this.orm.call("product.template", "product_detail_search", [scan]);

            try {
                const hasPack = details?.package_qty && details?.package_price;
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
                        details.package_qty = payload.package_qty;
                        details.package_price = payload.package_price;
                        details.package_name = payload.package_name;
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

// IMPORTANT: register with the exact key your menu/action expects:
registry.category("actions").add("product_detail_search_barcode_main_menu", ProductDetailDashboard);

// (Optional) keep an alias you may have used earlier:
registry.category("actions").add("product_detail_search.dashboard", ProductDetailDashboard);

export default ProductDetailDashboard;
