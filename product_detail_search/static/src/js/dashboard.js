/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

class CustomDashBoardFindProduct extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            barcode: "",
            details: null,   // will hold the FULL dict from product_detail_search (including uom_prices)
        });
    }

    async onInput(ev) {
        this.state.barcode = ev.target.value || "";
    }

    async onKeyDown(ev) {
        if (ev.key === "Enter") {
            await this._fetchDetails();
        }
    }

    async _fetchDetails() {
        const code = (this.state.barcode || "").trim();
        if (!code) {
            this.state.details = null;
            return;
        }
        try {
            const res = await this.orm.call("product.template", "product_detail_search", [code]);
            // IMPORTANT: keep the whole row so uom_prices, package_* etc. survive
            this.state.details = res && res.length ? res[0] : null;
        } catch (e) {
            console.error("product_detail_search failed", e);
            this.notification.add(_t("Lookup failed"), { type: "danger" });
            this.state.details = null;
        }
    }
}
CustomDashBoardFindProduct.template = "CustomDashBoardFindProduct";

registry.category("actions").add("product_detail_search_barcode_main_menu", {
    component: CustomDashBoardFindProduct,
});
