from odoo import api, models
from odoo.tools import float_round

class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def product_detail_search(self, raw_code):
        """Scan product/template/packaging barcode and return a single dict that
        now also includes UoM prices coming from `pos_multi_uom_price`:
        - uom_prices: [{uom_id, uom_name, price}, ...] (variant > template)
        """
        # --- 1) Normalize code (Arabic/Persian digits -> ASCII) ---
        def _normalize(code):
            if not code:
                return ""
            trans = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
            return code.translate(trans).strip()
        code = _normalize(raw_code)

        if not code:
            return False

        # --- 2) Resolve product from product/variant or packaging ---
        Product = self.env['product.product'].sudo()
        Tmpl = self.env['product.template'].sudo()
        Packaging = self.env['product.packaging'].sudo().with_context(active_test=False)

        product = Product.search([('barcode', '=', code)], limit=1)
        scanned_as = 'product'
        scanned_pack = None

        if not product:
            tmpl = Tmpl.search([('barcode', '=', code)], limit=1)
            if tmpl and tmpl.product_variant_id:
                product = tmpl.product_variant_id
                scanned_as = 'template'

        if not product:
            # packaging may link to product_id or product_tmpl_id
            scanned_pack = Packaging.search([('barcode', '=', code)], limit=1)
            if scanned_pack:
                if scanned_pack.product_id:
                    product = scanned_pack.product_id
                elif scanned_pack.product_tmpl_id and scanned_pack.product_tmpl_id.product_variant_id:
                    product = scanned_pack.product_tmpl_id.product_variant_id
                scanned_as = 'packaging'

        if not product:
            return False

        company = self.env.company
        currency = company.currency_id

        # --- 3) Compute basic unit/package view (existing behavior) ---
        # unit price
        unit_price = product.lst_price or 0.0

        # best/selected packaging (if any)
        package_qty = None
        package_price = None
        if scanned_pack:
            # use the scanned packaging as the display one
            qty = getattr(scanned_pack, 'qty', False) or getattr(scanned_pack, 'contained_quantity', False) or 1.0
            package_qty = qty
            package_price = float_round(unit_price * qty, precision_rounding=currency.rounding or 0.01)
        else:
            # optionally choose a "largest sales" packaging if you want (kept simple)
            pass

        # --- 4) NEW: collect UoM prices from pos_multi_uom_price (variant overrides template) ---
        uom_prices = []
        if 'product.multi.uom.price' in self.env and 'product.tmpl.multi.uom.price' in self.env:
            PriceVar = self.env['product.multi.uom.price'].sudo()
            PriceTpl = self.env['product.tmpl.multi.uom.price'].sudo()

            # build by uom_id; variant first
            by_uom = {}
            for rec in PriceVar.search([('product_id', '=', product.id)]):
                by_uom[rec.uom_id.id] = {
                    'uom_id': rec.uom_id.id,
                    'uom_name': rec.uom_id.display_name,
                    'price': float(rec.price or 0.0),
                }
            for rec in PriceTpl.search([('product_tmpl_id', '=', product.product_tmpl_id.id)]):
                if rec.uom_id.id not in by_uom:
                    by_uom[rec.uom_id.id] = {
                        'uom_id': rec.uom_id.id,
                        'uom_name': rec.uom_id.display_name,
                        'price': float(rec.price or 0.0),
                    }
            # sort by UoM ratio (bigger first) when possible
            try:
                Uom = self.env['uom.uom'].sudo()
                uom_prices = sorted(
                    by_uom.values(),
                    key=lambda d: Uom.browse(d['uom_id']).factor_inv,
                    reverse=True,
                )
            except Exception:
                uom_prices = list(by_uom.values())

        # --- 5) Build response ---
        res = {
            'product_id': product.id,
            'product_tmpl_id': product.product_tmpl_id.id,
            'name': product.display_name,
            'default_code': product.default_code or '',
            'uom': product.uom_id.display_name,
            'price': float(unit_price),
            'currency_symbol': currency.symbol,
            'scanned_as': scanned_as,
            'scanned_barcode': code,
            # packaging (if any)
            'package_qty': package_qty,
            'package_price': package_price,
            # NEW
            'uom_prices': uom_prices,
        }
        return [res]
