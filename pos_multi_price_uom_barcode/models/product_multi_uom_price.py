# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class multi_uom(models.Model):
    _name = 'product.multi.uom.price'
    _description = 'Product multiple uom price'

    product_id = fields.Many2one('product.template',
                                 _('Product'),
                                 readonly=True)
    variant_id = fields.Many2one('product.product',
                                 _('Product'),
                                 readonly=True)
    category_id = fields.Many2one('uom.category',compute="_compute_category_id")
    uom_id = fields.Many2one('uom.uom',
                             string=_("Unit of Measure"),
                             domain="[('category_id', '=', category_id)]",
                             required=True)
    price = fields.Float(_('Price'),
                         required=True,
                         digits='Product Price')
    barcode = fields.Char(
        'Barcode', copy=False, index='btree_not_null',
        help="International Article Number used for product identification.")

    # EHdlF Convinación Producto-UOM debe ser única
    _sql_constraints = [
        ('product_multi_uom_price_uniq',
         'UNIQUE (product_id,uom_id)',
         _('Product-UOM must be unique and there are duplicates!'))]

    def action_open_label_layout(self):
        action = self.env['ir.actions.act_window']._for_xml_id('product.action_open_label_layout')
        cntxt = {'final_barcode': self.barcode,
                 'final_price': self.price}
        if self.product_id:
            cntxt.update({'default_product_tmpl_ids': self.product_id.ids})
        elif self.variant_id:
            cntxt.update({'default_product_ids': self.variant_id.ids})
        action['context'] = cntxt
        return action

    @api.onchange('uom_id')
    def _onchange_uom_id(self):
        for record in self:
            if record.product_id:
                record.price = record.product_id.list_price * record.uom_id.factor_inv
            elif record.variant_id:
                record.price = record.variant_id.lst_price * record.uom_id.factor_inv

    @api.constrains('uom_id')
    def _constrains_uom_id(self):
        for record in self:
            if record.product_id and record.uom_id == record.product_id.uom_id:
                raise ValidationError(_('Must provide uom different than that of the product!'))
            elif record.variant_id and record.variant_id.uom_id == record.uom_id:
                raise ValidationError(_('Must provide uom different than that of the product!'))

    @api.model
    def _load_pos_data_domain(self, data):
        return []

    @api.model
    def _load_pos_data_fields(self, config_id):
        return ['id', 'product_id','variant_id','uom_id', 'barcode', 'price']

    def _load_pos_data(self, data):
        domain = self._load_pos_data_domain(data)
        fields = self._load_pos_data_fields(data['pos.config']['data'][0]['id'])
        datas = self.search_read(domain, fields, load=False)
        for data in datas:
            data['name'] = self.env['uom.uom'].browse(data['uom_id']).name
        return {
            'data': datas,
            'fields': fields,
        }

    @api.depends('variant_id','product_id')
    def _compute_category_id(self):
        for record in self:
            record.category_id = False
            if record.variant_id:
                record.category_id = record.variant_id.product_tmpl_id.uom_id.category_id
            elif record.product_id:
                record.category_id = record.product_id.uom_id.category_id