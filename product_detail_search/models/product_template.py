# -*- coding: utf-8 -*-
from odoo import api, models
import logging

_logger = logging.getLogger(__name__)
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # ---------- utils ----------
    @api.model
    def _normalize_scan(self, text):
        if not text:
            return ""
        if isinstance(text, (int, float)):
            text = str(text)
        return text.strip().translate(ARABIC_DIGITS)

    @api.model
    def _find_product_from_scan(self, scan):
        """Return (product.product, scanned_as)."""
        scan = self._normalize_scan(scan)
        Product = self.env["product.product"].sudo()
        Template = self.env["product.template"].sudo()
        Packaging = self.env["product.packaging"].sudo()

        if not scan:
            return self.env["product.product"], False

        # 1) product by barcode or code
        product = Product.search(
            ["|", ("barcode", "=", scan), ("default_code", "=", scan)], limit=1
        )
        if product:
            return product, "variant"

        # 2) template by barcode or code
        tmpl = Template.search(
            ["|", ("barcode", "=", scan), ("default_code", "=", scan)], limit=1
        )
        if tmpl and tmpl.product_variant_id:
            return tmpl.product_variant_id, "template"

        # 3) packaging barcode (identify product only)
        pack = Packaging.search([("barcode", "=", scan)], limit=1)
        if pack:
            if pack.product_id:
                return pack.product_id, "packaging"
            if pack.product_tmpl_id and pack.product_tmpl_id.product_variant_id:
                return pack.product_tmpl_id.product_variant_id, "packaging"

        return self.env["product.product"], False

    # ---------- UoM helpers ----------
    def _ratio_to_base(self, from_uom, to_base_uom):
        """How many base units in 1 `from_uom`."""
        return from_uom._compute_quantity(1.0, to_base_uom)

    def _pref_key(self, uom):
        """Prefer bigger UoM first (smaller factor), then anything else."""
        return (0 if getattr(uom, "uom_type", "") == "bigger" else 1, uom.factor or 1.0)

    # ---------- Dynamic discovery of UoM-Price lines ----------
    def _iter_uom_price_lines_dynamic(self, product):
        """
        Yield (uom, price) from any One2many lines on product/product.template
        whose comodel has a UoM field and a price field.
        Works with many modules (multi_uom_price, uom_price_ids, etc.).
        """
        base_cat_id = product.uom_id.category_id.id
        price_field_names = ("price", "uom_price", "amount", "list_price", "fixed_price")
        uom_field_names = ("uom_id", "uom")

        def extract(recset):
            for rec in recset.sudo():
                # UoM field
                uom = None
                for fn in uom_field_names:
                    if fn in rec._fields:
                        uom = getattr(rec, fn)
                        break
                if not uom:
                    continue
                if uom.category_id.id != base_cat_id:
                    continue
                # Price field
                price = None
                for pf in price_field_names:
                    if pf in rec._fields:
                        price = getattr(rec, pf)
                        break
                if price is None:
                    continue
                yield (uom, price)

        # 1) One2many on product (variant)
        for fname, field in product._fields.items():
            if field.type != "one2many":
                continue
            try:
                comodel = self.env[field.comodel_name]
            except Exception:
                continue
            # Quick schema check
            if "uom_id" not in comodel._fields and "uom" not in comodel._fields:
                continue
            if not any(p in comodel._fields for p in ("price", "uom_price", "amount", "list_price", "fixed_price")):
                continue
            lines = getattr(product.sudo(), fname)
            if lines:
                for tup in extract(lines):
                    yield tup

        # 2) One2many on template
        tmpl = product.product_tmpl_id.sudo()
        for fname, field in tmpl._fields.items():
            if field.type != "one2many":
                continue
            try:
                comodel = self.env[field.comodel_name]
            except Exception:
                continue
            if "uom_id" not in comodel._fields and "uom" not in comodel._fields:
                continue
            if not any(p in comodel._fields for p in ("price", "uom_price", "amount", "list_price", "fixed_price")):
                continue
            lines = getattr(tmpl, fname)
            if lines:
                for tup in extract(lines):
                    yield tup

    def _pick_best_uom_price(self, product):
        """Return (pack_uom, pack_price) or (None, None)."""
        candidates = list(self._iter_uom_price_lines_dynamic(product))
        if not candidates:
            return (None, None)
        candidates.sort(key=lambda t: self._pref_key(t[0]))
        return candidates[0][0], candidates[0][1]

    # ---------- Public RPC ----------
    @api.model
    def product_detail_search(self, scan):
        """
        JS calls: this.orm.call('product.template','product_detail_search',[scan])
        Returns dict consumed by the Find Product UI.
        """
        product, scanned_as = self._find_product_from_scan(scan)
        if not product:
            return {}

        product = product.with_context(lang=self.env.user.lang or "en_US")
        company = self.env.company
        currency = company.currency_id
        base_uom = product.uom_id
        base_cat = base_uom.category_id

        # قطعة (unit)
        unit_price = product.lst_price

        # التعبئة from UoM-Price lines (preferred)
        pack_uom, line_price = self._pick_best_uom_price(product)

        package_qty = 0.0
        package_price = 0.0
        package_name = False

        if pack_uom:
            package_qty = self._ratio_to_base(pack_uom, base_uom)   # e.g., Dozens -> 12
            package_price = currency.round(line_price)               # use line's price (e.g., 72.00)
            package_name = pack_uom.display_name
        else:
            # Fallback: first 'bigger' UoM × unit price
            bigger = self.env["uom.uom"].sudo().search(
                [("category_id", "=", base_cat.id), ("uom_type", "=", "bigger")],
                order="factor ASC",
                limit=1,
            )
            if bigger:
                package_qty = self._ratio_to_base(bigger, base_uom)
                package_price = currency.round(unit_price * package_qty)
                package_name = bigger.display_name

        return {
            "product_id": product.id,
            "product_tmpl_id": product.product_tmpl_id.id,
            "product_display_name": product.display_name,
            "barcode": product.barcode,
            "scanned_term": self._normalize_scan(scan),
            "scanned_as": scanned_as,

            # قطعة
            "price": unit_price,
            "uom_id": base_uom.id,
            "uom_name": base_uom.display_name,
            "uom_category_id": base_cat.id,

            # التعبئة
            "package_qty": package_qty,
            "package_price": package_price,
            "package_name": package_name,

            # currency
            "currency_id": currency.id,
            "currency_symbol": currency.symbol,
        }
