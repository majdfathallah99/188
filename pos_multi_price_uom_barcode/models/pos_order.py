# -*- coding: utf-8 -*-

import logging

from odoo import models, fields, api, _
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)
    
class PosOrderLine(models.Model):
    _inherit = 'pos.order.line'

    product_uom_id = fields.Many2one('uom.uom', string='Product UoM', related='')

    @api.depends('price_subtotal', 'total_cost')
    def _compute_margin(self):
        for line in self:
            ratio = line.product_uom_id.ratio or line.product_id.uom_id.ratio
            line.margin = line.price_subtotal - line.total_cost / ratio
            line.margin_percent = not float_is_zero(line.price_subtotal, precision_rounding=line.currency_id.rounding) and line.margin / line.price_subtotal or 0

    @api.model
    def _load_pos_data_fields(self, config_id):
        params = super()._load_pos_data_fields(config_id)
        params += ['product_uom_id']
        return params