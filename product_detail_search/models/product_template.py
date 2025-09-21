# -*- coding: utf-8 -*-
# Odoo 18 — server RPCs for the Find Product screen
# - product_detail_search(scan): returns Unit (قطعة) and Pack (التعبئة) info
# - uom_pack_from_lines(product_id=None, product_tmpl_id=None): get تعبئة from UoM-Price lines

from odoo import api, models
import logging

_logger = logging.getLogger(__name__)

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # ---------------- utils ----------------
    @api.model
    def _normalize_scan(self, text):
        if not text:
            return ""
        if isinstance(text, (int, float)):
            text = str(text)
        return text.strip().translate(ARABIC_DIGITS)

    @api.model
    def _find_product_from_scan(self, scan):
        """Return (product.product, scanned_as). Accepts product/template code or barcode, or packaging barcode."""
        scan = self._normalize_scan(scan)
        Product = self.env["product.product"].sudo()
        Template = self.env["product.template"].sudo()
        Packaging = self.env["product.packaging"].sudo()

        if not scan:
            return self.env["product.product"], False

        # product by barcode / default_code
        product = Product.search(
            ["|", ("barcode", "=", scan), ("default_code", "=", scan)], limit=1
        )
        if product:
            return product, "variant"

        # template by barcode / default_code
        tmpl = Template.search(
            ["|", ("barcode", "=", scan), ("default_code", "=", scan)], limit=1
        )
        if tmpl and tmpl.product_variant_id:
            return tmpl.product_variant_id, "template"

        # packaging barcode (identify only)
        pack = Packaging.search([("barcode", "=", scan)], limit=1)
        if pack:
            if pack.product_id:
                return pack.product_id, "packaging"
            if pack.product_tmpl_id and pack.product_tmpl_id.product_variant_id:
                return pack.product_tmpl_id.product_variant_id, "packaging"

        return self.env["product.product"], False

    # ---------------- UoM helpers ----------------
    def _ratio_to_base(self, from_uom, to_base_uom):
        """How many base units are in 1 `from_uom` (e.g., Dozens→Unit = 12)."""
        return from_uom._compute_quantity(1.0, to_base_uom)

    def _pref_key(self, uom):
        """Prefer 'bigger' UoM first (smaller factor)."""
        return (0 if getattr(uom, "uom_type", "") == "bigger" else 1, uom.factor or 1.0)

    # ---------------- Discover UoM-Price lines dynamically ----------------
    def _iter_uom_price_lines_dynamic(self, product):
        """
        Yield (uom, price) from any One2many on product/product.template whose comodel
        has a UoM field (uom_id/uom) and a price field (price/uom_price/amount/list_price/fixed_price).
        Works across many “sell-in-UoM” addons.
        """
        base_cat_id = product.uom_id.category_id.id
        price_fields = ("price", "uom_price", "amount", "list_price", "fixed_price")
        uom_fields = ("uom_id", "uom")

        def extract(recset):
            recset = recset.sudo()
            for rec in recset:
                uom = None
                for uf in uom_fields:
                    if uf in rec._fields:
                        uom = getattr(rec, uf)
                        break
                if not uom or uom.category_id.id != base_cat_id:
                    continue
                price = None
                for pf in price_fields:
                    if pf in rec._fields:
                        price = getattr(rec, pf)
                        break
                if price is None:
                    continue
                yield (uom, price)

        # variant O2M
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

        # template O2M
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

        # Try a few common standalone models
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
        """Return (pack_uom, pack_price) preferring 'bigger' UoMs; else (None, None)."""
        cands = list(self._iter_uom_price_lines_dynamic(product))
        if not cands:
            return (None, None)
        cands.sort(key=lambda t: self._pref_key(t[0]))
        return cands[0][0], cands[0][1]

    # ---------------- Public RPCs ----------------
    @api.model
    def uom_pack_from_lines(self, product_id=None, product_tmpl_id=None):
        """
        Return تعبئة info from UoM-Price lines.
        Args: product_id OR product_tmpl_id.
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
            "package_price": currency.round(line_price),
            "package_name": pack_uom.display_name,
        }

    @api.model
    def product_detail_search(self, scan):
        """
        Main endpoint used by your dashboard.js.
        Returns dict with unit (قطعة) and pack (التعبئة) fields.
        """
        product, scanned_as = self._find_product_from_scan(scan)
        if not product:
            return {}

        product = product.with_context(lang=self.env.user.lang or "en_US")
        currency = self.env.company.currency_id
        base_uom = product.uom_id
        base_cat = base_uom.category_id

        # قطعة
        unit_price = product.lst_price

        # تعبئة from UoM-Price lines (preferred)
        pack_uom, line_price = self._pick_best_uom_price(product)
        package_qty = 0.0
        package_price = 0.0
        package_name = False
        if pack_uom:
            package_qty = self._ratio_to_base(pack_uom, base_uom)
            package_price = currency.round(line_price)
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
            "package_qty": package_qty,
            "package_price": package_price,
            "package_name": package_name,
            # currency
            "currency_id": currency.id,
            "currency_symbol": currency.symbol,
        }
