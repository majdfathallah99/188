/** @odoo-module */

import { PosStore } from "@point_of_sale/app/store/pos_store";
import { PosOrderline } from "@point_of_sale/app/models/pos_order_line";
//import { Order } from "@pos_preparation_display/app/components/order/order";
import { Orderline } from "@point_of_sale/app/generic_components/orderline/orderline";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";
import {
    roundDecimals,
} from "@web/core/utils/numbers";

patch(PosOrderline.prototype, {
    setup(_defaultObj, options) {
        super.setup(...arguments);
        this.product_uom_id = this.product_uom_id || this.product_id?.uom_id;
    },
    set_uom(uom_id) {
        this.product_uom_id = uom_id[2];
    },
    getDisplayData() {
        const displayData = super.getDisplayData();
        if (this.product_uom_id){
            displayData.unit = this.product_uom_id ? this.product_uom_id.name : "";

        }else{
            displayData.unit = this.product_id.uom_id ? this.product_id.uom_id.name : "";

        }
        return displayData;
    },
    get_unit() {
        if (this.product_uom_id){
            return this.product_uom_id;
        } else{
          return this.product?.get_unit();

        }
    },
    can_be_merged_with(orderline) {
        const productPriceUnit = this.models["decimal.precision"].find(
            (dp) => dp.name === "Product Price"
        ).digits;
        const price = window.parseFloat(
            roundDecimals(this.price_unit || 0, productPriceUnit).toFixed(productPriceUnit)
        );
        let order_line_price = orderline
            .get_product()
            .get_price(orderline.order_id.pricelist_id, this.get_quantity());
        order_line_price = roundDecimals(order_line_price, this.currency.decimal_places);

        const isSameCustomerNote =
            (Boolean(orderline.get_customer_note()) === false &&
                Boolean(this.get_customer_note()) === false) ||
            orderline.get_customer_note() === this.get_customer_note();

        const hasSameUom = this.get_unit()?.id === orderline.get_unit()?.id;
        return (
            !this.skip_change &&
            orderline.getNote() === this.getNote() &&
            this.get_product().id === orderline.get_product().id &&
            this.is_pos_groupable() &&
            // don't merge discounted orderlines
            this.get_discount() === 0 &&
            !(
                this.product_id.tracking === "lot" &&
                (this.pickingType.use_create_lots || this.pickingType.use_existing_lots)
            ) &&
            this.full_product_name === orderline.full_product_name &&
            isSameCustomerNote &&
            !this.refunded_orderline_id &&
            !orderline.isPartOfCombo() &&
            orderline.price_unit === this.price_unit &&
            hasSameUom
        );
    }
});

patch(PosStore.prototype, {
    async addLineToOrder(vals, order, opts = {}, configure = true) {
        let merge = true;
        order.assert_editable();

        const options = {
            ...opts,
        };

//        if ("price_unit" in vals) {
//            merge = false;
//        }

        if (typeof vals.product_id == "number") {
            vals.product_id = this.data.models["product.product"].get(vals.product_id);
        }
        const product = vals.product_id;

        const values = {
            price_type: "price_unit" in vals ? "manual" : "original",
            price_extra: 0,
            price_unit: 0,
            order_id: this.get_order(),
            qty: 1,
            tax_ids: product.taxes_id.map((tax) => ["link", tax]),
            ...vals,
        };

        // Handle refund constraints
        if (
            order.doNotAllowRefundAndSales() &&
            order._isRefundOrder() &&
            (!values.qty || values.qty > 0)
        ) {
            this.dialog.add(AlertDialog, {
                title: _t("Refund and Sales not allowed"),
                body: _t("It is not allowed to mix refunds and sales"),
            });
            return;
        }

        // In case of configurable product a popup will be shown to the user
        // We assign the payload to the current values object.
        // ---
        // This actions cannot be handled inside pos_order.js or pos_order_line.js
        if (values.product_id.isConfigurable() && configure) {
            const payload = await this.openConfigurator(values.product_id);

            if (payload) {
                const productFound = this.models["product.product"]
                    .filter((p) => p.raw?.product_template_variant_value_ids?.length > 0)
                    .find((p) =>
                        p.raw.product_template_variant_value_ids.every((v) =>
                            payload.attribute_value_ids.includes(v)
                        )
                    );

                Object.assign(values, {
                    attribute_value_ids: payload.attribute_value_ids
                        .filter((a) => {
                            if (productFound) {
                                const attr =
                                    this.data.models["product.template.attribute.value"].get(a);
                                return (
                                    attr.is_custom || attr.attribute_id.create_variant !== "always"
                                );
                            }
                            return true;
                        })
                        .map((id) => [
                            "link",
                            this.data.models["product.template.attribute.value"].get(id),
                        ]),
                    custom_attribute_value_ids: Object.entries(payload.attribute_custom_values).map(
                        ([id, cus]) => [
                            "create",
                            {
                                custom_product_template_attribute_value_id:
                                    this.data.models["product.template.attribute.value"].get(id),
                                custom_value: cus,
                            },
                        ]
                    ),
                    price_extra: values.price_extra + payload.price_extra,
                    qty: payload.qty || values.qty,
                    product_id: productFound || values.product_id,
                });
            } else {
                return;
            }
        } else if (values.product_id.product_template_variant_value_ids.length > 0) {
            // Verify price extra of variant products
            const priceExtra = values.product_id.product_template_variant_value_ids
                .filter((attr) => attr.attribute_id.create_variant !== "always")
                .reduce((acc, attr) => acc + attr.price_extra, 0);
            values.price_extra += priceExtra;
        }

        // In case of clicking a combo product a popup will be shown to the user
        // It will return the combo prices and the selected products
        // ---
        // This actions cannot be handled inside pos_order.js or pos_order_line.js
        if (values.product_id.isCombo() && configure) {
            const payload = await makeAwaitable(this.dialog, ComboConfiguratorPopup, {
                product: values.product_id,
            });

            if (!payload) {
                return;
            }

            const comboPrices = computeComboItems(
                values.product_id,
                payload,
                order.pricelist_id,
                this.data.models["decimal.precision"].getAll(),
                this.data.models["product.template.attribute.value"].getAllBy("id")
            );

            values.combo_line_ids = comboPrices.map((comboItem) => [
                "create",
                {
                    product_id: comboItem.combo_item_id.product_id,
                    tax_ids: comboItem.combo_item_id.product_id.taxes_id.map((tax) => [
                        "link",
                        tax,
                    ]),
                    combo_item_id: comboItem.combo_item_id,
                    price_unit: comboItem.price_unit,
                    order_id: order,
                    qty: 1,
                    attribute_value_ids: comboItem.attribute_value_ids?.map((attr) => [
                        "link",
                        attr,
                    ]),
                    custom_attribute_value_ids: Object.entries(
                        comboItem.attribute_custom_values
                    ).map(([id, cus]) => [
                        "create",
                        {
                            custom_product_template_attribute_value_id:
                                this.data.models["product.template.attribute.value"].get(id),
                            custom_value: cus,
                        },
                    ]),
                },
            ]);
        }

        // In the case of a product with tracking enabled, we need to ask the user for the lot/serial number.
        // It will return an instance of pos.pack.operation.lot
        // ---
        // This actions cannot be handled inside pos_order.js or pos_order_line.js
        const code = opts.code;
        if (values.product_id.isTracked() && (configure || code)) {
            let pack_lot_ids = {};
            const packLotLinesToEdit =
                (!values.product_id.isAllowOnlyOneLot() &&
                    this.get_order()
                        .get_orderlines()
                        .filter((line) => !line.get_discount())
                        .find((line) => line.product_id.id === values.product_id.id)
                        ?.getPackLotLinesToEdit()) ||
                [];

            // if the lot information exists in the barcode, we don't need to ask it from the user.
            if (code && code.type === "lot") {
                // consider the old and new packlot lines
                const modifiedPackLotLines = Object.fromEntries(
                    packLotLinesToEdit.filter((item) => item.id).map((item) => [item.id, item.text])
                );
                const newPackLotLines = [{ lot_name: code.code }];
                pack_lot_ids = { modifiedPackLotLines, newPackLotLines };
            } else {
                pack_lot_ids = await this.editLots(values.product_id, packLotLinesToEdit);
            }

            if (!pack_lot_ids) {
                return;
            } else {
                const packLotLine = pack_lot_ids.newPackLotLines;
                values.pack_lot_ids = packLotLine.map((lot) => ["create", lot]);
            }
        }

        // In case of clicking a product with tracking weight enabled a popup will be shown to the user
        // It will return the weight of the product as quantity
        // ---
        // This actions cannot be handled inside pos_order.js or pos_order_line.js
        if (values.product_id.to_weight && this.config.iface_electronic_scale && configure) {
            if (values.product_id.isScaleAvailable) {
                this.isScaleScreenVisible = true;
                this.scaleData = {
                    productName: values.product_id?.display_name,
                    uomName: values.product_id.uom_id?.name,
                    uomRounding: values.product_id.uom_id?.rounding,
                    productPrice: this.getProductPrice(values.product_id),
                };
                const weight = await makeAwaitable(
                    this.env.services.dialog,
                    ScaleScreen,
                    this.scaleData
                );
                if (weight) {
                    values.qty = weight;
                }
                this.isScaleScreenVisible = false;
                this.scaleWeight = 0;
                this.scaleTare = 0;
                this.totalPriceOnScale = 0;
            } else {
                await values.product_id._onScaleNotAvailable();
            }
        }

        // Handle price unit
        if (!values.product_id.isCombo() && vals.price_unit === undefined) {
            values.price_unit = values.product_id.get_price(order.pricelist_id, values.qty);
        }
        const isScannedProduct = opts.code && opts.code.type === "product";
        if (values.price_extra && !isScannedProduct) {
            const price = values.product_id.get_price(
                order.pricelist_id,
                values.qty,
                values.price_extra
            );

            values.price_unit = price;
        }

        const line = this.data.models["pos.order.line"].create({ ...values, order_id: order });
        line.setOptions(options);
        this.selectOrderLine(order, line);
        if (configure) {
            this.numberBuffer.reset();
        }
        const selectedOrderline = order.get_selected_orderline();
        if (options.draftPackLotLines && configure) {
            selectedOrderline.setPackLotLines({
                ...options.draftPackLotLines,
                setQuantity: options.quantity === undefined,
            });
        }

        let to_merge_orderline;
        for (const curLine of order.lines) {
            if (curLine.id !== line.id) {
                if (curLine.can_be_merged_with(line) && merge !== false) {
                    to_merge_orderline = curLine;
                }
            }
        }

        if (to_merge_orderline) {
            to_merge_orderline.merge(line);
            line.delete();
            this.selectOrderLine(order, to_merge_orderline);
        } else if (!selectedOrderline) {
            this.selectOrderLine(order, order.get_last_orderline());
        }

        if (configure) {
            this.numberBuffer.reset();
        }

        order.recomputeOrderData();

        if (configure) {
            this.numberBuffer.reset();
        }

        this.hasJustAddedProduct = true;
        clearTimeout(this.productReminderTimeout);
        this.productReminderTimeout = setTimeout(() => {
            this.hasJustAddedProduct = false;
        }, 3000);

        return line;
    }
});

//patch(Order.prototype, {
//    set_orderline_options(orderline, options) {
//        super.set_orderline_options(...arguments);
//
//       if (options.product_uom_id) {
//            orderline.product_uom_id = options.product_uom_id;
//        }
//
//    },
//});

//patch(Orderline, {
//    props: {
//        ...Orderline.props,
//        line: {
//            ...Orderline.props.line,
//            shape: {
//                ...Orderline.props.line.shape,
//                arabicName: { type: String, optional: true },
//            },
//        },
//    },
//});