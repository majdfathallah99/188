# -*- coding: utf-8 -*-


{
    
    'name': "FlexiUnit POS: Dynamic Pricing & Barcodes and UoM Price Printing Labels",
    'summary': 'POS UOM Price barcode, Pos multi UOM price Barcode Multi UOM for Products in POS product multi uom on point of sales multi uom point of sales multiple uom allow multiple uom on pos multiple uom on point of sale multi uom pos different uom on pos multi unit of measure point of sale multi unit of measure POS Multi UoM Price barcode Multi uom Price Management for POS Products Product Multi UOM This module allow to use multiple units of measure for products in point of sale.Measurment|Unit Of Measure|Multiple Units|Measurement of multi unit This module allow to use multiple units of measure for products in point of sale.Measurment|Unit Of Measure|Multiple Units|Measurement of multi unit This application allow POS user to select the multiple unit of measurement for single product, Which is configurable from the product template level. POS multi uom price | Multiple Unit Of Measurement In POS | Multi UOM Configure In POS | Odoo Multi UOM , multi uom, configure multi uom in pos, pos multi uom configure, pos uom app,product multi uom in pos, Allows you to sell one product in different units of measure in POS, multi pos Sell products in different units of measure, with unique barcodes and prices.POS Secondary UOM/Qty/Price ',
    'category': 'Point of Sale',
    'version': '18.0',
    "author": "Khaled Hassan",
    'website': "https://apps.odoo.com/apps/modules/browse?search=Khaled+hassan",
    'description': """This module enhances Odoo POS to support multiple Units of Measure (UoM) per product with custom prices and dedicated barcodes. It enables businesses to sell products in different units (e.g., bottles, packs, or kilograms) directly from the POS, with automatic price adjustments and accurate inventory tracking.""",
    'depends': ['point_of_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_view.xml',
        'views/report_template.xml',
    ],
    'installable': True,
    'auto_install': False,
    'assets': {
        'point_of_sale._assets_pos':  [
            'pos_multi_price_uom_barcode/static/src/js/models.js',
            'pos_multi_price_uom_barcode/static/src/js/multi_uom_price.js',
            'pos_multi_price_uom_barcode/static/src/js/TicketScreen.js',
            'pos_multi_price_uom_barcode/static/src/xml/*',
        ],
    },
    'currency': 'EUR',
    'price': '50',
    'license': 'OPL-1',
    'images': ['static/description/main_screenshot.png'],
}
