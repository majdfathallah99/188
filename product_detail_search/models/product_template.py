# -*- coding: utf-8 -*-
from odoo import api, models
import logging

_logger = logging.getLogger(__name__)
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # ---------------- utilities ----------------
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

        # 1) product by barcode or default_code
        product = Product.search(
            ["|", ("barcode", "=", scan), ("default_code", "=", scan)], limit=1
        )
        if product:
            return product, "variant"

        # 2) template by barcode or default_code
        tmpl = Template.search(
            ["|", ("barcode", "=", scan), ("default_code", "=", scan)], limit=1
        )
        if tmpl and tmpl.product_variant_id:
            return tmpl.product_variant_id, "template"

        # 3) packaging barcode -> resolve product (pricing will NOT use packaging)
        pack = Packaging.search([("barcode", "=", scan)], limit=1)
        if pack:
            if pack.product_id:
                return pack.product_id, "packaging"
            if pack.product_tmpl_id and pack.product_tmpl_id.product_variant_id:
                return pack.product_tmpl_id.product_variant_id, "packaging"

        return self.env["product.product"], False

    # --------- UoM helpers ---------
    def _ratio_to_base(self, from_uom, to_base_uom):
        """How many base units are in 1 `from_uom`."""
        return from_uom._compute_quantity(1.0, to_base_uom)

    def _sort_pref_bigger(self, uom):
        """Key to prefer 'bigger' UoM first (smaller factor == bigger)."""
        # factor can be 0 for reference; we still want bigger first
        return (0 if getattr(uom, "uom_type", "") == "bigger" else 1, uom.factor or 1.0)

    # --------- UoM price line discovery (covers many add-ons) ---------
    def _iter_uom_price_lines(self, product):
        """
        Yield tuples (uom, price) from various schemas:
          - One2many on product.product or product.template:
            multi_uom_price_ids / uom_price_ids / uom_prices_ids / uom_price_line_ids
          - Standalone models: product.multi.uom.price, product.tmpl.multi.uom.price,
            product.uom.price, product.uom.price.line
        """
        base_cat_id = product.uom_id.category_id.id

        # 1) O2M fields on product/product.template commonly used by UoM price modules
        o2m_field_names = [
            "multi_uom_price_ids",
            "uom_price_ids",
            "uom_prices_ids",
            "uom_price_line_ids",
        ]
        price_field_names = ("price", "uom_price", "amount", "list_price")
        uom_field_names = ("uom_id", "uom")

        def extract_from_record(recset):
            for rec in recset:
                # find uom field
                uom = None
                for fn in uom_field_names:
                    if fn in rec._fields:
                        uom = getattr(rec, fn)
                        break
                if not uom:
                    continue
                if uom.category_id.id != base_cat_id:
                    continue
                # find price field
                price = None
                for pf in price_field_names:
                    if pf in rec._fields:
                        price = getattr(rec, pf)
                        break
                if price is None:
                    continue
                yield (uom, price)

        # product first
        for field in o2m_field_names:
            if field in product._fields:
                lines = getattr(product.sudo(), field)
                if lines:
                    for t in extract_from_record(lines.sudo()):
                        yield t

        # then template
        tmpl = product.product_tmpl_id.sudo()
        for field in o2m_field_names:
            if field in tmpl._fields:
                lines = getattr(tmpl, field)
                if lines:
                    for t in extract_from_record(lines.sudo()):
                        yield t

        # 2) Standalone models used by some modules
        candidate_models = [
            "product.multi.uom.price",
            "product.tmpl.multi.uom.price",
            "product.uom.price",
            "product.uom.price.line",
        ]
        for model in candidate_models:
            if model not in self.env:
                continue
            Line = self.env[model].sudo()
            domain = []
            if "product_id" in Line._fields:
                domain.append(("product_id", "=", product.id))
            elif "product_tmpl_id" in Line._fields:
                domain.append(("product_tmpl_id", "=", tmpl.id))
            else:
                continue
            lines = Line.search(domain)
            for (uom, price) in extract_from_record(lines):
                yield (uom, price)

    def _pick_best_uom_price(self, product):
        """
        Return (pack_uom, pack_price) preferring:
          - UoM in same category
          - 'bigger' UoM first, then by largest ratio (i.e., smallest factor)
        """
        base = product.uom_id
        candidates = list(self._iter_uom_price_lines(product))
        if not candidates:
            return (None, None)
        # sort by preference
        candidates.sort(key=lambda t: self._sort_pref_bigger(t[0]))
        return candidates[0][0], candidates[0][1]

    # ---------------- public RPC ----------------
    @api.model
    def product_detail_search(self, scan):
        """
        Called from JS: this.orm.call('product.template','product_detail_search',[scan])
        Returns a dict consumed by your Find Product UI.
        """
        product, scanned_as = self._find_product_from_scan(scan)
        if not product:
            return {}

        product = product.with_context(lang=self.env.user.lang or "en_US")
        company = self.env.company
        currency = company.currency_id
        base_uom = product.uom_id
        base_cat = base_uom.category_id

        # ----- قطعة (unit) -----
        unit_price = product.lst_price

        # ----- التعبئة from UoM Price line (preferred) -----
        pack_uom, line_price = self._pick_best_uom_price(product)

        package_qty = 0.0
        package_price = 0.0
        package_name = False

        if pack_uom:
            package_qty = self._ratio_to_base(pack_uom, base_uom)  # e.g., Dozens -> 12
            package_price = currency.round(line_price)              # use the *line* price
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

        # payload
        return {
            # identity
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
            "package_qty": package_qty,         # e.g., 12
            "package_price": package_price,     # e.g., 72.00 from UoM Price line
            "package_name": package_name,       # e.g., "Dozens"

            # currency
            "currency_id": currency.id,
            "currency_symbol": currency.symbol,
        }
