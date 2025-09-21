# -*- coding: utf-8 -*-
from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # ----------------- helpers -----------------
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

        # 1) variant by barcode or default_code
        product = Product.search(
            ["|", ("barcode", "=", scan), ("default_code", "=", scan)],
            limit=1,
        )
        if product:
            return product, "variant"

        # 2) template by barcode or default_code
        tmpl = Template.search(
            ["|", ("barcode", "=", scan), ("default_code", "=", scan)],
            limit=1,
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

    # ---- UoM Price line picker (works with several popular modules) ----
    def _extract_line_price_and_uom(self, product):
        """
        Try common models:
          - product.multi.uom.price
          - product.tmpl.multi.uom.price
          - product.uom.price
          - product.uom.price.line
        Return (line_price, pack_uom) or (None, None).
        """
        candidates = [
            "product.multi.uom.price",
            "product.tmpl.multi.uom.price",
            "product.uom.price",
            "product.uom.price.line",
        ]
        base_uom = product.uom_id
        base_cat = base_uom.category_id

        for model in candidates:
            if model not in self.env:
                continue
            Line = self.env[model].sudo()

            # Figure out the relational field present on this model
            domain = []
            if "product_id" in Line._fields:
                domain.append(("product_id", "=", product.id))
            elif "product_tmpl_id" in Line._fields:
                domain.append(("product_tmpl_id", "=", product.product_tmpl_id.id))
            else:
                # Not a supported schema
                continue

            # Optional company filter if present
            if "company_id" in Line._fields:
                domain.append(("company_id", "in", [self.env.company.id, False]))

            # Pull candidate lines
            lines = Line.search(domain)
            if not lines:
                continue

            # Extract usable lines: need a UoM and a price field
            usable = []
            for l in lines:
                uom = getattr(l, "uom_id", False) or getattr(l, "uom", False)
                # different modules name price differently
                price = None
                for fname in ("price", "uom_price", "amount", "list_price"):
                    if fname in l._fields:
                        price = getattr(l, fname)
                        break
                if not uom or price is None:
                    continue
                if uom.category_id.id != base_cat.id:
                    continue  # must be same category as product
                usable.append((uom, price, l))

            if not usable:
                continue

            # Prefer 'bigger' UoM; otherwise take the first
            # Sort by factor ascending: bigger UoM has smaller factor
            usable.sort(key=lambda tup: tup[0].factor or 0.0)
            pick = None
            for uom, price, l in usable:
                if getattr(uom, "uom_type", None) == "bigger":
                    pick = (price, uom)
                    break
            if not pick:
                uom, price, _l = usable[0][0], usable[0][1], usable[0][2]
                pick = (price, uom)

            return pick  # (line_price, pack_uom)

        return (None, None)

    # ----------------- public RPC -----------------
    @api.model
    def product_detail_search(self, scan):
        """
        Called by JS: this.orm.call('product.template','product_detail_search',[scan])
        Returns dict with:
          - price (unit 'قطعة')
          - package_qty/package_price/package_name ('التعبئة') from UoM Price line if available,
            else from a bigger UoM in the same category.
        """
        product, scanned_as = self._find_product_from_scan(scan)
        if not product:
            return {}

        product = product.with_context(lang=self.env.user.lang or "en_US")
        company = self.env.company
        currency = company.currency_id

        # ---- قطعة (unit) ----
        unit_price = product.lst_price
        base_uom = product.uom_id
        base_cat = base_uom.category_id

        # ---- التعبئة from UoM Price line (preferred) ----
        line_price, pack_uom = self._extract_line_price_and_uom(product)

        package_qty = 0.0
        package_price = 0.0
        package_name = False

        if pack_uom:
            package_qty = pack_uom._compute_quantity(1.0, base_uom)  # e.g., Dozens -> 12 Units
            # IMPORTANT: use the line's price, not unit_price * qty
            package_price = currency.round(line_price)
            package_name = pack_uom.display_name
        else:
            # fallback: if there is ANY bigger UoM, compute from unit price
            bigger = self.env["uom.uom"].sudo().search(
                [("category_id", "=", base_cat.id), ("uom_type", "=", "bigger")],
                order="factor ASC",
                limit=1,
            )
            if bigger:
                package_qty = bigger._compute_quantity(1.0, base_uom)
                package_price = currency.round(unit_price * package_qty)
                package_name = bigger.display_name

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

            # التعبئة (from UoM Price line if present)
            "package_qty": package_qty,       # e.g., 12
            "package_price": package_price,   # e.g., 72.00 from the line
            "package_name": package_name,     # e.g., "Dozens"

            # currency
            "currency_id": currency.id,
            "currency_symbol": currency.symbol,
        }
