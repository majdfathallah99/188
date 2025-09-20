# -*- coding: utf-8 -*-


from odoo import models,api


class PosSession(models.Model):
    _inherit = 'pos.session'

    def _process_pos_ui_product_product(self, products):
        product_ids = [product['id'] for product in products]
        multi_uom_prices = self.env['product.multi.uom.price'].search_read(
            [('product_id.product_variant_ids', 'in', product_ids)],
            ['product_id', 'uom_id', 'price', 'barcode']
        )

        multi_uom_prices_by_product = {}
        for price in multi_uom_prices:
            product_id = price['product_id'][0]
            if product_id not in multi_uom_prices_by_product:
                multi_uom_prices_by_product[product_id] = []
            multi_uom_prices_by_product[product_id].append({
                'id': price['uom_id'][0],
                'name': price['uom_id'][1],
                'price': price['price'],
                'barcode': price['barcode'],
            })

        for product in products:
            product['multi_uom_prices'] = multi_uom_prices_by_product.get(product['product_tmpl_id'][0], [])

        return super()._process_pos_ui_product_product(products)

    def _pos_ui_models_to_load(self):
        result = super()._pos_ui_models_to_load()
        new_model = 'product.multi.uom.price'
        if new_model not in result:
            result.append(new_model)
        return result

    @api.model
    def _load_pos_data_models(self, config_id):
        data = super()._load_pos_data_models(config_id)
        new_model = 'product.multi.uom.price'
        if new_model not in data:
            data += [new_model]
        return data


    def _loader_params_product_multi_uom_price(self):
        return {'search_params': {'domain': [], 'fields': ['product_id','variant_id', 'uom_id', 'price','barcode'],},}

    def _get_pos_ui_product_multi_uom_price(self, params):
        products_uom_price = self.env['product.multi.uom.price'].search_read(**params['search_params'])
        product_uom_price = {}
        if products_uom_price:
            for unit in products_uom_price:
                if not unit['product_id'][0] in product_uom_price:
                    product_uom_price[unit['product_id'][0]] = {}
                    product_uom_price[unit['product_id'][0]]['uom_id'] = {}
                product_uom_price[unit['product_id'][0]]['uom_id'][unit['uom_id'][0]] = {
                        'id'    : unit['uom_id'][0],
                        'name'  : unit['uom_id'][1],
                        'price' : unit['price'],
                        'barcode' : unit['barcode']}
        print(products_uom_price)
        return product_uom_price
