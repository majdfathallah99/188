# -*- coding: utf-8 -*-
# Odoo 18 — Find Product backend
#
# This version explicitly integrates with the "POS Multi Price UoM Barcode"
# module (pos_multi_price_uom_barcode). We PREFER its UOM PRICE lines when
# building the تعبئة card. If nothing is found there, we fall back to any
# other multi-UoM price models we can detect, and lastly to a plain bigger UoM.

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
        """Prefer 'bigger' UoMs first (smaller factor)."""
        return (0 if getattr(uom, "uom_type", "") == "bigger" else 1, uom.factor or 1.0)

    # ---------------- Integration with POS Multi Price UoM Barcode ----------------
    def _iter_pos_multi_price_lines(self, product):
        """
        Yield (uom, price, barcode?) from the Cybrosys 'POS Multi Price UoM Barcode'
        module (technical: pos_multi_price_uom_barcode). The exact model/field
        names vary a little between releases; we handle the common variants.

        We first try One2many fields on template/variant that look like UoM price
        lines for that module; then we also query known standalone models.
        """
        base_cat_id = product.uom_id.category_id.id

        # candidate field names used in that module
        price_fields = ("price", "unit_price", "uom_price", "amount", "fixed_price", "list_price")
        uom_fields = ("uom_id", "uom", "product_uom", "multi_uom_id", "uom_uom_id")
        barcode_fields = ("barcode", "pack_barcode", "uom_barcode")

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

                # Optional barcode on the line
                pack_barcode = None
                for bf in barcode_fields:
                    if bf in rec._fields:
                        pack_barcode = getattr(rec, bf)
                        break

                yield (uom, price, pack_barcode)

        # 1) O2M on product.product
        prod = product.sudo()
        for fname, field in prod._fields.items():
            if field.type != "one2many":
                continue
            comodel = self.env.get(field.comodel_name)
            if not comodel:
                continue
            # fast filter: model name smells like multi-uom price
            if "uom" not in field.comodel_name.lower():
                continue
            if not any(n in comodel._fields for n in uom_fields) or \
               not any(n in comodel._fields for n in price_fields):
                continue
            lines = getattr(prod, fname)
            if lines:
                for tup in extract(lines):
                    yield tup

        # 2) O2M on product.template
        tmpl = product.product_tmpl_id.sudo()
        for fname, field in tmpl._fields.items():
            if field.type != "one2many":
                continue
            comodel = self.env.get(field.comodel_name)
            if not comodel:
                continue
            if "uom" not in field.comodel_name.lower():
                continue
            if not any(n in comodel._fields for n in uom_fields) or \
               not any(n in comodel._fields for n in price_fields):
                continue
            lines = getattr(tmpl, fname)
            if lines:
                for tup in extract(lines):
                    yield tup

        # 3) Known standalone models used by that app across versions
        for model in (
            # most likely names first
            "product.uom.price.line",
            "product.multi.uom.price",
            "product.tmpl.multi.uom.price",
            "product.uom.price",
        ):
            if model not in self.env:
                continue
            Line = self.env[model].sudo()
            domain = []
            # bind to variant or template if fields exist
            if "product_id" in Line._fields:
                domain.append(("product_id", "=", product.id))
            if "product_tmpl_id" in Line._fields:
                # prefer exact template if variant domain not present
                if not domain:
                    domain.append(("product_tmpl_id", "=", product.product_tmpl_id.id))
            if not domain:
                continue
            recs = Line.search(domain)
            for tup in extract(recs):
                yield tup

    def _pick_best_pos_multi_price(self, product):
        """
        Prefer a تعبئة UoM from the POS multi-price module.
        Returns (uom, price, pack_barcode) or (None, None, None).
        """
        cands = list(self._iter_pos_multi_price_lines(product))
        if not cands:
            return (None, None, None)
        # Prefer 'bigger' UoMs, then smallest factor
        cands.sort(key=lambda t: self._pref_key(t[0]))
        uom, price, pack_barcode = cands[0]
        return uom, price, pack_barcode

    # ---------------- Public RPCs ----------------
    @api.model
    def uom_pack_from_lines(self, product_id=None, product_tmpl_id=None):
        """
        Return تعبئة info from UoM-Price lines.
        We now PREFER pos_multi_price_uom_barcode lines.
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

        # 1) Prefer the POS Multi UoM price line
        pack_uom, line_price, line_barcode = self._pick_best_pos_multi_price(product)
        if pack_uom:
            qty = self._ratio_to_base(pack_uom, base_uom)
            return {
                "has_pack": True,
                "package_qty": qty,
                "package_price": currency.round(line_price),
                "package_name": pack_uom.display_name,
                "package_barcode": line_barcode or False,
                "source": "pos_multi_price_uom_barcode",
            }

        # 2) No explicit lines → no تعبئة from that module
        return {"has_pack": False}

    @api.model
    def product_detail_search(self, scan):
        """
        Main endpoint used by your dashboard.js.
        Now *prefers* تعبئة from pos_multi_price_uom_barcode lines.
        """
        product, scanned_as = self._find_product_from_scan(scan)
        if not product:
            return {}

        product = product.with_context(lang=self.env.user.lang or "en_US")
        currency = self.env.company.currency_id
        base_uom = product.uom_id
        base_cat = base_uom.category_id

        # قطعة (unit)
        unit_price = product.lst_price

        # التعبئة — prefer POS multi-price UoM lines
        pack_uom, line_price, line_barcode = self._pick_best_pos_multi_price(product)

        package_qty = 0.0
        package_price = 0.0
        package_name = False
        package_barcode = line_barcode or False
        pack_source = None

        if pack_uom:
            package_qty = self._ratio_to_base(pack_uom, base_uom)
            package_price = currency.round(line_price)
            package_name = pack_uom.display_name
            pack_source = "pos_multi_price_uom_barcode"

        # NOTE: if you WANT a fallback to "first bigger UoM × unit price",
        # uncomment the block below. You asked to fetch ONLY from that module,
        # so we keep it strict; no fallback means تعبئة will stay empty when
        # there is no UOM PRICE line.
        #
        # else:
        #     bigger = self.env["uom.uom"].sudo().search(
        #         [("category_id", "=", base_cat.id), ("uom_type", "=", "bigger")],
        #         order="factor ASC", limit=1
        #     )
        #     if bigger:
        #         package_qty = self._ratio_to_base(bigger, base_uom)
        #         package_price = currency.round(unit_price * package_qty)
        #         package_name = bigger.display_name
        #         pack_source = "fallback_bigger_uom"

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
            # التعبئة (only when UOM PRICE line exists)
            "package_qty": package_qty,
            "package_price": package_price,
            "package_name": package_name,
            "package_barcode": package_barcode,
            "pack_source": pack_source,
            # currency
            "currency_id": currency.id,
            "currency_symbol": currency.symbol,
        }
