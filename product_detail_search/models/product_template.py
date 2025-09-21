# -*- coding: utf-8 -*-
# Odoo 18 — Server-side helper to fetch "التعبئة" (Pack) from UoM Price lines.
# It returns package_qty / package_price / package_name for a given product.

from odoo import api, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # ---------------- UoM helpers ----------------
    def _ratio_to_base(self, from_uom, to_base_uom):
        """How many base units are in 1 `from_uom`."""
        # Example: from_uom = Dozens, to_base_uom = Unit  => 12.0
        return from_uom._compute_quantity(1.0, to_base_uom)

    def _pref_key(self, uom):
        """
        Sort key to prefer a 'bigger' UoM (smaller factor) before others.
        Keeps the method generic no matter the UoM names used.
        """
        # (0, factor) for bigger; (1, factor) for others -> bigger comes first
        return (0 if getattr(uom, "uom_type", "") == "bigger" else 1, uom.factor or 1.0)

    # -------- Dynamic discovery of UoM-Price lines on product/template --------
    def _iter_uom_price_lines_dynamic(self, product):
        """
        Yield (uom, price) by scanning *any* One2many on product/product.template
        whose comodel has BOTH:
          - a UoM field: one of {'uom_id', 'uom'}
          - a price field: one of {'price','uom_price','amount','list_price','fixed_price'}
        This makes it compatible with many "sell in UoM" addons.
        """
        base_cat_id = product.uom_id.category_id.id
        price_fields = ("price", "uom_price", "amount", "list_price", "fixed_price")
        uom_fields = ("uom_id", "uom")

        def extract(recset):
            recset = recset.sudo()
            for rec in recset:
                # find UoM
                uom = None
                for uf in uom_fields:
                    if uf in rec._fields:
                        uom = getattr(rec, uf)
                        break
                if not uom or uom.category_id.id != base_cat_id:
                    continue

                # find price
                price = None
                for pf in price_fields:
                    if pf in rec._fields:
                        price = getattr(rec, pf)
                        break
                if price is None:
                    continue

                yield (uom, price)

        # 1) One2many fields on the product (variant)
        prod = product.sudo()
        for fname, field in prod._fields.items():
            if field.type != "one2many":
                continue
            # comodel must exist and contain a UoM field & a price field
            try:
                comodel = self.env[field.comodel_name]
            except Exception:
                continue
            if ("uom_id" not in comodel._fields and "uom" not in comodel._fields) or \
               not any(p in comodel._fields for p in price_fields):
                continue
            lines = getattr(prod, fname)
            if lines:
                yield from extract(lines)

        # 2) One2many fields on the template
        tmpl = product.product_tmpl_id.sudo()
        for fname, field in tmpl._fields.items():
            if field.type != "one2many":
                continue
            try:
                comodel = self.env[field.comodel_name]
            except Exception:
                continue
            if ("uom_id" not in comodel._fields and "uom" not in comodel._fields) or \
               not any(p in comodel._fields for p in price_fields):
                continue
            lines = getattr(tmpl, fname)
            if lines:
                yield from extract(lines)

    def _pick_best_uom_price(self, product):
        """
        Return (pack_uom, pack_price) from discovered lines, preferring:
          1) UoM with uom_type == 'bigger' (e.g., Dozens), then
          2) smallest factor (i.e., largest pack)
        If nothing found, returns (None, None).
        """
        candidates = list(self._iter_uom_price_lines_dynamic(product))
        if not candidates:
            return (None, None)
        candidates.sort(key=lambda t: self._pref_key(t[0]))
        return candidates[0][0], candidates[0][1]

    # ---------------- Public RPC used by the frontend ----------------
    @api.model
    def uom_pack_from_lines(self, product_id=None, product_tmpl_id=None):
        """
        RPC: Returns تعبئة info from UoM-Price lines.

        Args (one of):
          - product_id: ID of product.product
          - product_tmpl_id: ID of product.template (will map to a variant)

        Returns:
          {
            "has_pack": bool,
            "package_qty": float,       # e.g., 12.0
            "package_price": float,     # e.g., 72.0  (the line's price, currency-rounded)
            "package_name": str,        # e.g., "Dozens"
          }
        """
        Product = self.env["product.product"].sudo()

        product = False
        if product_id:
            product = Product.browse(product_id)
        elif product_tmpl_id:
            product = Product.search([("product_tmpl_id", "=", product_tmpl_id)], limit=1)

        if not product:
            return {"has_pack": False}

        currency = self.env.company.currency_id
        base_uom = product.uom_id

        pack_uom, line_price = self._pick_best_uom_price(product)
        if not pack_uom:
            return {"has_pack": False}

        qty_in_base = self._ratio_to_base(pack_uom, base_uom)
        return {
            "has_pack": True,
            "package_qty": qty_in_base,
            "package_price": currency.round(line_price),  # use the configured UoM line price
            "package_name": pack_uom.display_name,
        }
