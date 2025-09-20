/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { useService } from "@web/core/utils/hooks";
import { Component } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { SelectionPopup } from "@point_of_sale/app/utils/input_popups/selection_popup";
import { ControlButtons } from "@point_of_sale/app/screens/product_screen/control_buttons/control_buttons";
import { patch } from "@web/core/utils/patch";

patch(ProductScreen.prototype, {
    async _getProductByBarcode(code) {
        let product = this.pos.models["product.product"].getBy("barcode", code.base_code);

        if (!product) {
            const productPackaging = this.pos.models["product.packaging"].getBy(
                "barcode",
                code.base_code
            );
            product = productPackaging && productPackaging.product_id;
        }
        if (!product) {
            const allProducts = this.pos.models["product.product"].getAll();
            product = allProducts.find((p) => {
                if (p.multi_uom_price_id) {
                    const matchedUom = p.multi_uom_price_id.find((uom) => uom.barcode === code.base_code);
                    if (matchedUom) {
                        return true;
                    }
                }
                return false;
            });
        }

        if (!product) {
            const records = await this.pos.data.callRelated(
                "pos.session",
                "find_product_by_barcode",
                [odoo.pos_session_id, code.base_code, this.pos.config.id]
            );
            await this.pos.processProductAttributes();

            if (records && records["product.product"].length > 0) {
                product = records["product.product"][0];
                await this.pos._loadMissingPricelistItems([product]);
            }
        }

        return product;
    },

    async _barcodeProductAction(code) {
        const product = await this._getProductByBarcode(code);

        if (!product) {
            this.barcodeReader.showNotFoundNotification(code);
            return;
        }

        let matchedUom = null;
        if (product.multi_uom_price_id) {
            matchedUom = product.multi_uom_price_id.find((uom) => uom.barcode === code.base_code);
        }

        const options = {
            product_id: product,
            product_uom_id: matchedUom ? matchedUom.uom_id : product.uom_id,
            price_unit: matchedUom ? matchedUom.price : product.list_price,
            note: '',
        };
        if (matchedUom) {
            options.price_type = "automatic";
        }

        await this.pos.addLineToCurrentOrder(
            options,
            { code },
            product.needToConfigure()
        );

        this.numberBuffer.reset();
    }
});
patch(ControlButtons.prototype, {
    async onClick() {

        const selectedOrderline = this.pos.get_order().get_selected_orderline();
        if (!selectedOrderline) {
            return;
        }
        if (selectedOrderline.product_id.multi_uom_price_id) {

            let uomPricesObj = selectedOrderline.product_id.multi_uom_price_id;
            let filteredUomPrices = Object.values(uomPricesObj);
            const uomList = filteredUomPrices.map(uomPrice => ({
                id: uomPrice.id,
                label: `${uomPrice.uom_id.name} - Price: ${uomPrice.price}`,
                isSelected: false,
                item: uomPrice,
            }));

            this.dialog.add(SelectionPopup, {
                title: _t("Select UOM"),
                list: uomList,
                getPayload: (selectedUOM) => {
                    if (selectedUOM) {
                        console.log(selectedUOM)
                        selectedOrderline.set_uom({0: selectedUOM.id, 1: selectedUOM.name,2:selectedUOM.uom_id});
                        selectedOrderline.price_type = "automatic";
                        selectedOrderline.set_unit_price(selectedUOM.price);
                        selectedOrderline.setNote('');
                    }
                },
            });
        }
    }
});

