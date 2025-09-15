/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useBarcodeReader } from "@point_of_sale/app/barcode/barcode_reader_hook";

export class FindProductScreen extends Component {
    static template = "product_detail_search.FindProductScreen";

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");

        // Preserve `this` and handle any barcode event.
        useBarcodeReader({
            product: (code) => this._onScan(code),
            any:     (code) => this._onScan(code),
        });
    }

    async _onScan(code) {
        const barcode = String(code?.base_code || "").trim();
        if (!barcode) return;

        try {
            const recs = await this.orm.searchRead(
                "product.product",
                [["barcode", "=", barcode]],
                ["id", "display_name", "default_code", "list_price", "uom_id"]
            );

            if (!recs || !recs.length) {
                this.pos.showScreen("ProductDetails", { product_details: false });
                return;
            }

            const p = recs[0];
            const details = [{
                id: p.id,
                name: p.display_name,
                default_code: p.default_code || "",
                uom: (p.uom_id && p.uom_id[1]) || "",
                price: p.list_price || 0,
                package_qty: 0,
                package_price: 0,
                symbol: (this.pos.currency && this.pos.currency.symbol) || "$",
                currency_symbol: (this.pos.currency && this.pos.currency.symbol) || "$",
            }];

            this.pos.showScreen("ProductDetails", { product_details: details });
        } catch {
            // Keep POS stable on any error
            this.pos.showScreen("ProductDetails", { product_details: false });
        }
    }

    back() {
        this.pos.showScreen("ProductScreen");
    }
}

// ---- SAFE REGISTRATION (avoids "already exists" crash)
{
    const posScreens = registry.category("pos_screens");
    let exists = false;
    try {
        if (posScreens.get) exists = !!posScreens.get("FindProductScreen");
        else if (posScreens.contains) exists = posScreens.contains("FindProductScreen");
    } catch (_) { /* ignore */ }

    if (!exists) {
        try { posScreens.add("FindProductScreen", FindProductScreen); }
        catch (_) { /* ignore duplicate key thrown by Odoo registry */ }
    }
}
