/** @odoo-module */

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";

patch(TicketScreen.prototype, {
    getToRefundDetail(orderline) {
        const toRefundDetail = super.getToRefundDetail(orderline);
        toRefundDetail.product_uom_id = orderline.product_uom_id;
        return toRefundDetail;
    },
    async onDoRefund() {
        const order = this.getSelectedOrder();

        if (order && this._doesOrderHaveSoleItem(order)) {
            if (!this._prepareAutoRefundOnOrder(order)) {
                // Don't proceed on refund if preparation returned false.
                return;
            }
        }

        if (!order || !this.getHasItemsToRefund()) {
            return;
        }

        const partner = order.get_partner();
        // The order that will contain the refund orderlines.
        // Use the destinationOrder from props if the order to refund has the same
        // partner as the destinationOrder.
        const destinationOrder =
            this.props.destinationOrder &&
            this.props.destinationOrder.lines.every(
                (l) =>
                    l.quantity >= 0 || order.lines.some((ol) => ol.id === l.refunded_orderline_id)
            ) &&
            partner === this.props.destinationOrder.get_partner() &&
            !this.pos.doNotAllowRefundAndSales()
                ? this.props.destinationOrder
                : this._getEmptyOrder(partner);

        destinationOrder.takeaway = order.takeaway;
        // Add orderline for each toRefundDetail to the destinationOrder.
        const lines = [];
        for (const refundDetail of this._getRefundableDetails(partner, order)) {
            console.log('refundDetail', refundDetail)
            const refundLine = refundDetail.line;
            const line = this.pos.models["pos.order.line"].create({
                qty: -refundDetail.qty,
                price_unit: refundLine.price_unit,
                product_id: refundLine.product_id,
                order_id: destinationOrder,
                discount: refundLine.discount,
                product_uom_id: refundLine.product_uom_id,
                tax_ids: refundLine.tax_ids.map((tax) => ["link", tax]),
                refunded_orderline_id: refundLine,
                pack_lot_ids: refundLine.pack_lot_ids.map((packLot) => [
                    "create",
                    { lot_name: packLot.lot_name },
                ]),
                price_type: "automatic",
            });
            lines.push(line);
            refundDetail.destination_order_uuid = destinationOrder.uuid;
        }
        // link the refund combo lines
        const refundComboParentLines = lines.filter(
            (l) => l.refunded_orderline_id.combo_line_ids.length > 0
        );
        for (const refundComboParent of refundComboParentLines) {
            const children = refundComboParent.refunded_orderline_id.combo_line_ids
                .map((l) => l.refund_orderline_ids)
                .flat();
            refundComboParent.update({
                combo_line_ids: [["link", ...children]],
            });
        }

        //Add a check too see if the fiscal position exist in the pos
        if (order.fiscal_position_not_found) {
            this.dialog.add(AlertDialog, {
                title: _t("Fiscal Position not found"),
                body: _t(
                    "The fiscal position used in the original order is not loaded. Make sure it is loaded by adding it in the pos configuration."
                ),
            });
            return;
        }

        if (order.fiscal_position_id) {
            destinationOrder.update({ fiscal_position_id: order.fiscal_position_id });
        }
        // Set the partner to the destinationOrder.
        this.setPartnerToRefundOrder(partner, destinationOrder);

        if (this.pos.get_order().uuid !== destinationOrder.uuid) {
            this.pos.set_order(destinationOrder);
        }
        await this.addAdditionalRefundInfo(order, destinationOrder);

        this.postRefund(destinationOrder);

        this.closeTicketScreen();
    }
});


