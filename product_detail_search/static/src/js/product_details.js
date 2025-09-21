/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { useBarcodeReader } from "@point_of_sale/app/barcode/barcode_reader_hook";
import { useService } from "@web/core/utils/hooks";

export class ProductDetails extends Component {
    static template = "product_detail_search.ProductDetails";

    setup() {
        this.pos = usePos();
        this.orm = useService("orm");

        // Allow re-scanning while on the details screen
        useBarcodeReader({
            product: (code) => this._onScanAgain(code),
            any:     (code) => this._onScanAgain(code),
        });
    }

    async _onScanAgain(code) {
        const barcode = String(code?.base_code || "").trim();
        if (!barcode) return;

        try {
            const recs = await this.orm.searchRead(
                "product.product",
                [["barcode", "=", barcode]],
                ["id, display_name, default_code, list_price, uom_id".split(", ").join(", ")].split(", ") // safeguard
            );
        } catch {
            // fallback if above line confuses minifier; use explicit fields:
        }

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
            this.pos.showScreen("ProductDetails", { product_details: false });
        }
    }

    back() {
        this.pos.showScreen("FindProductScreen");
    }
}

// ---- SAFE REGISTRATION (avoids "already exists" crash)
{
    const posScreens = registry.category("pos_screens");
    let exists = false;
    try {
        if (posScreens.get) exists = !!posScreens.get("ProductDetails");
        else if (posScreens.contains) exists = posScreens.contains("ProductDetails");
    } catch (_) { /* ignore */ }

    if (!exists) {
        try { posScreens.add("ProductDetails", ProductDetails); }
        catch (_) { /* ignore duplicate key */ }
    }
}
