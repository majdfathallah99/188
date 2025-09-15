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
        this.state = useState({
            barcode: "",
            details: null, // keep the full dict (includes uom_prices, package_*, etc.)
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
            this.state.details = res && res.length ? res[0] : null;
        } catch (e) {
            console.error("product_detail_search failed", e);
            this.notification.add(_t("Lookup failed"), { type: "danger" });
            this.state.details = null;
        }
    }
}
CustomDashBoardFindProduct.template = "CustomDashBoardFindProduct";

// ---- Legacy fallback so old action runner won't crash ----
function legacyClientAction(env, options) {
    const target = document.createElement("div");
    // Mount the OWL component manually and return a "widget-like" object
    const app = mount(CustomDashBoardFindProduct, { env, target, props: {} });
    return {
        widget: {
            el: target,
            destroy: () => app.unmount(),
        },
    };
}

// Register for BOTH modern and legacy paths
registry.category("actions").add("product_detail_search_barcode_main_menu", {
    component: CustomDashBoardFindProduct,
    clientAction: legacyClientAction,
});
