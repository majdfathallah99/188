/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { mount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

class CustomDashBoardFindProduct extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({ barcode: "", details: null });
    }
    onInput(ev) { this.state.barcode = ev.target.value || ""; }
    async onKeyDown(ev) { if (ev.key === "Enter") await this._fetchDetails(); }
    async _fetchDetails() {
        const code = (this.state.barcode || "").trim();
        this.state.details = null;
        if (!code) return;
        try {
            const res = await this.orm.call("product.template", "product_detail_search", [code]);
            this.state.details = res && res.length ? res[0] : null; // keep FULL dict (uom_prices, package_*, etc.)
        } catch (e) {
            console.error("product_detail_search failed", e);
            this.notification.add(_t("Lookup failed"), { type: "danger" });
        }
    }
}
CustomDashBoardFindProduct.template = "CustomDashBoardFindProduct";

/* Legacy client action function. ActionManager expects a FUNCTION for this tag. */
registry.category("actions").add("product_detail_search_barcode_main_menu", function (env) {
    const target = document.createElement("div");
    const app = mount(CustomDashBoardFindProduct, { env, target, props: {} });
    return { widget: { el: target, destroy: () => app.unmount() } };
});
