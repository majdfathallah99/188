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

    def _ratio_to_base(self, from_uom, to_base_uom):
        """How many base units are in 1 `from_uom`."""
        return from_uom._compute_quantity(1.0, to_base_uom)

    def _pref_key(self, uom):
        """Prefer 'bigger' UoM first (smaller factor)."""
        return (0 if getattr(uom, "uom_type", "") == "bigger" else 1, uom.factor or 1.0)

    # ---------- Dynamic discovery of UoM-Price lines ----------
    def _iter_uom_price_lines_dynamic(self, product):
        """
        Yield (uom, price) from any One2many lines on product/product.template
        whose comodel has a UoM field and a price field.
        Works with many 'sell-in-UoM' add-ons (multi_uom_price, uom_price_ids, etc.).
        """
        base_cat_id = product.uom_id.category_id.id
        price_field_names = ("price", "uom_price", "amount", "list_price", "fixed_price")
        uom_field_names = ("uom_id", "uom")

        def extract(recset):
            recset = recset.sudo()
            for rec in recset:
                # UoM
                uom = None
                for fn in uom_field_names:
                    if fn in rec._fields:
                        uom = getattr(rec, fn)
                        break
                if not uom or uom.category_id.id != base_cat_id:
                    continue
                # Price
                price = None
                for pf in price_field_names:
                    if pf in rec._fields:
                        price = getattr(rec, pf)
                        break
                if price is None:
                    continue
                yield (uom, price)

        # Product (variant)
        prod = product.sudo()
        for fname, field in prod._fields.items():
            if field.type != "one2many":
                continue
            # comodel must have a UoM field and a price field
            try:
                comodel = self.env[field.comodel_name]
            except Exception:
                continue
            if "uom_id" not in comodel._fields and "uom" not in comodel._fields:
                continue
            if not any(p in comodel._fields for p in ("price", "uom_price", "amount", "list_price", "fixed_price")):
                continue
            lines = getattr(prod, fname)
            if lines:
                for tup in extract(lines):
                    yield tup

        # Template
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

    # ---------------- public RPC used by JS fallback ----------------
    @api.model
    def uom_pack_from_lines(self, product_id=None, product_tmpl_id=None):
        """
        Return تعبئة info from UoM Price lines.
        Args: product_id OR product_tmpl_id
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
            "package_price": currency.round(line_price),  # use the line's price (e.g., 72.00)
            "package_name": pack_uom.display_name,
        }
