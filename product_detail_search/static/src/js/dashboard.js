/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

function humanizeError(err) {
    try {
        // Odoo RPC error formats vary; extract something readable
        const data = err?.message || err?.toString?.();
        const msg = err?.data?.message || err?.message || data || "خطأ غير معروف";
        return msg.replace(/(<([^>]+)>)/gi, ""); // strip HTML if present
    } catch {
        return "خطأ غير معروف";
    }
}

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

    async _fetchAndRender(scan) {
        this.state.loading = true;
        this.state.details = null;

        try {
            // 1) Primary RPC (server method on product.template)
            let details;
            try {
                details = await this.orm.call("product.template", "product_detail_search", [scan]);
                if (!details || typeof details !== "object") {
                    throw new Error("لم يتم العثور على المنتج أو استجابة غير متوقعة.");
                }
            } catch (err) {
                console.error("[product_detail_search] product_detail_search failed:", err);
                this.notification.add("فشل استدعاء المنتج. " + humanizeError(err), { type: "danger" });
                return; // stop here; nothing to render
            }

            // 2) Enrich التعبئة from UoM Price lines (safe: ignore errors)
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
            } catch (err) {
                console.warn("[product_detail_search] uom_pack_from_lines failed:", err);
                // Don't notify the user; unit card can still render
            }

            // 3) Render
            this.state.details = details;
        } finally {
            this.state.loading = false;
        }
    }
}

// Register under the exact tag your menu opens
registry.category("actions").add("product_detail_search_barcode_main_menu", ProductDetailDashboard);
// Optional legacy alias if your menu/action used another tag earlier
registry.category("actions").add("product_detail_search.dashboard", ProductDetailDashboard);

export default ProductDetailDashboard;
