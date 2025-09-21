/** @odoo-module **/

/**
 * Dashboard (Find Product) – drop-in file
 * - Keeps your original flow to fetch details from product_detail_search
 * - Then always tries to enrich from UoM Price lines via uom_pack_from_lines
 * - Never crashes if enrichment fails
 */

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class ProductDetailDashboard extends Component {
    static template = "product_detail_search.Dashboard"; // keep your original template name
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: false,
            details: null,
            query: "",
        });
    }

    // Called when user types/scans then presses Enter (or you call it from a button)
    async onSearch(ev) {
        ev?.preventDefault?.();
        const scan = (this.state.query || "").trim();
        if (!scan) {
            this.notification.add("اكتب أو امسح باركود أولاً", { type: "warning" });
            return;
        }
        await this._fetchAndRender(scan);
    }

    // --- FULL FETCH WITH ENRICHMENT (paste this whole function) ---
    async _fetchAndRender(scan) {
        this.state.loading = true;
        try {
            // 1) fetch details as your screen already did
            let details = await this.orm.call("product.template", "product_detail_search", [scan]);

            // 2) enrich تعبئة from UoM Price lines if missing/empty
            try {
                const hasPack =
                    details &&
                    typeof details === "object" &&
                    details.package_qty &&
                    details.package_price;

                if (!hasPack) {
                    const pid = details.product_id || null;
                    const ptid = details.product_tmpl_id || null;

                    const payload = await this.orm.call(
                        "product.template",
                        "uom_pack_from_lines",
                        [pid, ptid],
                        {}
                    );

                    if (payload && payload.has_pack) {
                        details.package_qty = payload.package_qty;     // e.g., 12
                        details.package_price = payload.package_price; // e.g., 72.0
                        details.package_name = payload.package_name;   // e.g., "Dozens"
                    }
                }
            } catch (e) {
                // never break the screen
                console.warn("Pack enrich failed:", e);
            }

            // 3) show
            this.state.details = details;
        } catch (err) {
            console.error(err);
            this.notification.add("تعذر جلب البيانات. تحقق من الاتصال أو الصلاحيات.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }
}

// Register the client action (keep your original key if different)
registry.category("actions").add("product_detail_search.dashboard", ProductDetailDashboard);
