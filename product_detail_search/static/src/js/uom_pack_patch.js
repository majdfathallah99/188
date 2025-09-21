# -*- coding: utf-8 -*-
# Odoo 18 — Product details for "Find Product" screen.
# - Unit card (قطعة): product.lst_price
# - Pack card (التعبئة): from UoM-Price lines (multi-uom addons), else first "bigger" UoM × unit price

from odoo import api, models
import logging

_logger = logging.getLogger(__name__)

# Allow scanning Arabic numerals like "١٢٣٤"
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------
    @api.model
    def _normalize_scan(self, text):
        """Trim and convert Arabic digits to ASCII for consistent lookups."""
        if not text:
            return ""
        if isinstance(text, (int, float)):
            text = str(text)
        return text.strip().translate(ARABIC_DIGITS)

    @api.model
    def _find_product_from_scan(self, scan):
        """
        Resolve a product.product and tag how it was found:
          returns (product, scanned_as) where scanned_as ∈ {'variant','template','packaging', False}
        """
        scan = self._normalize_scan(scan)
        Product = self.env["product.product"].sudo()
        Template = self.env["product.template"].sudo()
        Packaging = self.env["product.packaging"].sudo()

        if not scan:
            return self.env["product.product"], False

        # 1) product by barcode or internal reference
        product = Product.search(
            ["|", ("barcode", "=", scan), ("default_code", "=", scan)],
            limit=1,
        )
        if product:
            return product, "variant"

        # 2) template by barcode or internal reference
        tmpl = Template.search(
            ["|", ("barcode", "=", scan), ("default_code", "=", scan)],
            limit=1,
        )
        if tmpl and tmpl.product_variant_id:
            return tmpl.product_variant_id, "template"

        # 3) packaging barcode — only for identification (pricing will NOT use packaging)
        pack = Packaging.search([("barcode", "=", scan)], limit=1)
        if pack:
            if pack.product_id:
                return pack.product_id, "packaging"
            if pack.product_tmpl_id and pack.product_tmpl_id.product_variant_id:
                return pack.product_tmpl_id.product_variant_id, "packaging"

        return self.env["product.product"], False

    # -------------------------------------------------------------------------
    # UoM helpers
    # -------------------------------------------------------------------------
    def _ratio_to_base(self, from_uom, to_base_uom):
        """Return how many base units are contained in 1 `from_uom`."""
        # Example: Dozens (from_uom) to Unit (to_base_uom) => 12.0
        return from_uom._compute_quantity(1.0, to_base_uom)

    def _pref_key(self, uom):
        """
        Sort key to prefer a 'bigger' UoM (smaller factor) before others.
        Makes picking deterministic across modules.
        """
        return (0 if getattr(uom, "uom_type", "") == "bigger" else 1, uom.factor or 1.0)

    # -------------------------------------------------------------------------
    # Discover UoM-Price lines across popular "sell in UoM" schemas
    # -------------------------------------------------------------------------
    def _iter_uom_price_lines_dynamic(self, product):
        """
        Yield (uom, price) by scanning *any* One2many on product / product.template
        whose comodel has BOTH:
          - a UoM field in {'uom_id', 'uom'}
          - a price field in {'price','uom_price','amount','list_price','fixed_price'}
        This makes it compatible with many multi-UoM add-ons.
        """
        base_cat_id = product.uom_id.category_id.id
        price_fields = ("price", "uom_price", "amount", "list_price", "fixed_price")
        uom_fields = ("uom_id", "uom")

        def extract(recset):
            recset = recset.sudo()
            for rec in recset:
                # UoM
                uom = None
                for uf in uom_fields:
                    if uf in rec._fields:
                        uom = getattr(rec, uf)
                        break
                if not uom or uom.category_id.id != base_cat_id:
                    continue
                # Price
                price = None
                for pf in price_fields:
                    if pf in rec._fields:
                        price = getattr(rec, pf)
                        break
                if price is None:
                    continue
                yield (uom, price)

        # Variant-level O2M lines
        prod = product.sudo()
        for fname, field in prod._fields.items():
            if field.type != "one2many":
                continue
            comodel = self.env.get(field.comodel_name)
            if not comodel:
                continue
            if ("uom_id" not in comodel._fields and "uom" not in comodel._fields) or \
               not any(p in comodel._fields for p in price_fields):
                continue
            lines = getattr(prod, fname)
            if lines:
                yield from extract(lines)

        # Template-level O2M lines
        tmpl = product.product_tmpl_id.sudo()
        for fname, field in tmpl._fields.items():
            if field.type != "one2many":
                continue
            comodel = self.env.get(field.comodel_name)
            if not comodel:
                continue
            if ("uom_id" not in comodel._fields and "uom" not in comodel._fields) or \
               not any(p in comodel._fields for p in price_fields):
                continue
            lines = getattr(tmpl, fname)
            if lines:
                yield from extract(lines)

        # Some addons use standalone models; try the common ones as a bonus
        for model in (
            "product.multi.uom.price",
            "product.tmpl.multi.uom.price",
            "product.uom.price",
            "product.uom.price.line",
        ):
            if model not in self.env:
                continue
            Line = self.env[model].sudo()
            domain = []
            if "product_id" in Line._fields:
                domain.append(("product_id", "=", product.id))
            elif "product_tmpl_id" in Line._fields:
                domain.append(("product_tmpl_id", "=", product.product_tmpl_id.id))
            else:
                continue
            for (uom, price) in extract(Line.search(domain)):
                yield (uom, price)

    def _pick_best_uom_price(self, product):
        """
        Return (pack_uom, pack_price) from discovered lines, preferring:
          1) UoM with uom_type == 'bigger', then
          2) smallest factor (i.e., largest pack)
        If none found, return (None, None).
        """
        candidates = list(self._iter_uom_price_lines_dynamic(product))
        if not candidates:
            return (None, None)
        candidates.sort(key=lambda t: self._pref_key(t[0]))
        return candidates[0][0], candidates[0][1]

    # -------------------------------------------------------------------------
    # Public RPC (can be called from JS directly if you want)
    # -------------------------------------------------------------------------
    @api.model
    def uom_pack_from_lines(self, product_id=None, product_tmpl_id=None):
        """
        Return تعبئة info from UoM-Price lines.
        Args: product_id OR product_tmpl_id (one is enough).
        """
        Product = self.env["product.product"].sudo()
        if product_id:
            product = Product.browse(product_id)
        elif product_tmpl_id:
            product = Product.search([("product_tmpl_id", "=", product_tmpl_id)], limit=1)
        else:
            return {"has_pack": False}

        if not product:
            return {"has_pack": False}

        currency = self.env.company.currency_id
        base_uom = product.uom_id

        pack_uom, line_price = self._pick_best_uom_price(product)
        if not pack_uom:
            return {"has_pack": False}

        qty = self._ratio_to_base(pack_uom, base_uom)
        return {
            "has_pack": True,
            "package_qty": qty,
            "package_price": currency.round(line_price),  # exact configured price
            "package_name": pack_uom.display_name,
        }

    # -------------------------------------------------------------------------
    # Main endpoint used by your screen
    # -------------------------------------------------------------------------
    @api.model
    def product_detail_search(self, scan):
        """
        Called from JS: this.orm.call('product.template', 'product_detail_search', [scan])
        Returns a dict that your XML/JS already knows how to render:
          - Unit ("قطعة"):  price, uom_name
          - Pack ("التعبئة"): package_qty, package_price, package_name
        """
        product, scanned_as = self._find_product_from_scan(scan)
        if not product:
            return {}

        # context for translations / currency rounding
        product = product.with_context(lang=self.env.user.lang or "en_US")
        company = self.env.company
        currency = company.currency_id

        # ----- Unit card (قطعة) -----
        unit_price = product.lst_price
        base_uom = product.uom_id
        base_cat = base_uom.category_id

        # ----- تعبئة (prefer UoM-Price lines) -----
        pack_uom, line_price = self._pick_best_uom_price(product)

        package_qty = 0.0
        package_price = 0.0
        package_name = False

        if pack_uom:
            package_qty = self._ratio_to_base(pack_uom, base_uom)      # e.g., Dozens -> 12
            package_price = currency.round(line_price)                  # use the *line* price (e.g., 72.00)
            package_name = pack_uom.display_name
        else:
            # Fallback: first 'bigger' UoM × unit price (keeps old behavior when no lines configured)
            bigger = self.env["uom.uom"].sudo().search(
                [("category_id", "=", base_cat.id), ("uom_type", "=", "bigger")],
                order="factor ASC",
                limit=1,
            )
            if bigger:
                package_qty = self._ratio_to_base(bigger, base_uom)
                package_price = currency.round(unit_price * package_qty)
                package_name = bigger.display_name

        # ----- payload -----
        return {
            # identity / context
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
            "package_qty": package_qty,        # e.g., 12
            "package_price": package_price,    # e.g., 72.00 (from UoM line)
            "package_name": package_name,      # e.g., "Dozens"

            # currency
            "currency_id": currency.id,
            "currency_symbol": currency.symbol,
        }
