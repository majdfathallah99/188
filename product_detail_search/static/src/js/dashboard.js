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
            details: null, // keep FULL dict (includes uom_prices, package_*, etc.)
        });
    }

    onInput(ev) {
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
            // IMPORTANT: assign the whole row so uom_prices reaches the template
            this.state.details = res && res.length ? res[0] : null;
        } catch (e) {
            console.error("product_detail_search failed", e);
            this.notification.add(_t("Lookup failed"), { type: "danger" });
            this.state.details = null;
        }
    }
}
CustomDashBoardFindProduct.template = "CustomDashBoardFindProduct";

/** Legacy-compatible client action runner (used by some paths) */
function clientAction(env /*, options */) {
    const target = document.createElement("div");
    const app = mount(CustomDashBoardFindProduct, { env, target, props: {} });
    return {
        widget: {
            el: target,
            destroy: () => app.unmount(),
        },
    };
}

/** Register BOTH ways so any runner path works */
registry.category("actions").add("product_detail_search_barcode_main_menu", {
    component: CustomDashBoardFindProduct, // modern path
    clientAction,                         // legacy path
});
