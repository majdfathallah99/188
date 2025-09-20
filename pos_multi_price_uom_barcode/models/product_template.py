# -*- coding: utf-8 -*-

from odoo import models, fields, _,api


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    multi_uom_price_id = fields.One2many('product.multi.uom.price', 'product_id', _("UOM price"))

    def write(self, vals):
        res = super(ProductTemplate, self).write(vals)

        if 'multi_uom_price_id' in vals:
            for template in self:
                if len(template.product_variant_ids) == 1:
                    variant = template.product_variant_ids[0]
                    uom_commands = []
                    variant.multi_uom_price_id = [(5, 0, 0)]
                    for uom_price in template.multi_uom_price_id:
                        uom_commands.append((0, 0,{
                            'variant_id': variant.id,
                            'uom_id': uom_price.uom_id.id,
                            'price': uom_price.price,
                            'barcode': uom_price.barcode
                        }))
                    variant.write({'multi_uom_price_id': uom_commands})
        return res

    @api.model
    def _load_pos_data_fields(self, config_id):
        res = super()._load_pos_data_fields(config_id)
        res += ['multi_uom_price_id']
        return res


class ProductProduct(models.Model):
    _inherit = 'product.product'

    multi_uom_price_id = fields.One2many('product.multi.uom.price', 'variant_id', _("UOM price"))
    lock_uom = fields.Boolean(compute="_compute_lock_uom")

    @api.depends('product_tmpl_id')
    def _compute_lock_uom(self):
        for product in self:
            product.lock_uom = False
            if len(product.product_tmpl_id.product_variant_ids) == 1:
                product.lock_uom = True
    @api.model
    def _load_pos_data_fields(self, config_id):
        res = super()._load_pos_data_fields(config_id)
        res += ['multi_uom_price_id']
        return res