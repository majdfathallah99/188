# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
import logging

_logger = logging.getLogger(__name__)

# map Arabic numerals -> ASCII so scans like "١٢٣٤" work
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # ---------- helpers ----------
    @api.model
    def _normalize_scan(self, text):
        """Trim & convert Arabic digits to ASCII."""
        if not text:
            return ""
        if isinstance(text, (int, float)):
            text = str(text)
        return text.strip().translate(ARABIC_DIGITS)

    @api.model
    def _find_product_from_scan(self, scan):
        """
        Return (product.product record, scanned_as) where scanned_as ∈ {'variant','template','packaging', False}.
        We only use packaging to *identify* the product; pricing always uses UoM (not packaging).
        """
        scan = self._normalize_scan(scan)
        if not scan:
            return self.env["product.product"], False

        Product = self.env["product.product"].sudo()
        Template = self.env["product.template"].sudo()
        Packaging = self.env["product.packaging"].sudo()

        # try product variant: barcode or internal ref
        product = Product.search(
            ["|", ("barcode", "=", scan), ("default_code", "=", scan)], limit=1
        )
        if product:
            return product, "variant"

        # try template: barcode or internal ref
        tmpl = Template.search(
            ["|", ("barcode", "=", scan), ("default_code", "=", scan)], limit=1
        )
        if tmpl and tmpl.product_variant_id:
            return tmpl.product_variant_id, "template"

        # allow scanning a packaging barcode just to resolve the product (NOT for pricing)
        pack = Packaging.search([("barcode", "=", scan)], limit=1)
        if pack:
            if pack.product_id:
                return pack.product_id, "packaging"
            if pack.product_tmpl_id and pack.product_tmpl_id.product_variant_id:
                return pack.product_tmpl_id.product_variant_id, "packaging"

        return self.env["product.product"], False

    # ---------- public RPC ----------
    @api.model
    def product_detail_search(self, scan):
        """
        Called from JS: this.orm.call('product.template', 'product_detail_search', [scan])
        Returns a dict with:
          - price (unit, "قطعة")
          - package_qty / package_price / package_name (computed from UoM, NOT packaging)
          - uom_id/uom_name/uom_category_id, currency_symbol, etc.
        """
        product, scanned_as = self._find_product_from_scan(scan)
        if not product:
            return {}

        product = product.with_context(lang=self.env.user.lang or "en_US")
        company = self.env.company
        currency = company.currency_id

        # ----- Unit price ("قطعة"): catalog price per base UoM (no pricelist/discount/tax here)
        unit_price = product.lst_price  # float
        uom = product.uom_id

        # ----- Pick a "pack" UoM: first 'bigger' than reference in the same category
        Uom = self.env["uom.uom"].sudo()
        pack_uom = Uom.search(
            [
                ("category_id", "=", uom.category_id.id),
                ("uom_type", "=", "bigger"),
            ],
            order="factor ASC",  # smaller factor => bigger UoM (e.g., Dozens)
            limit=1,
        )

        package_qty = 0.0
        package_price = 0.0
        package_name = False

        if pack_uom:
            # how many base units in 1 pack_uom (e.g., 1 Dozen -> 12 Units)
            package_qty = pack_uom._compute_quantity(1.0, uom)
            package_price = currency.round(unit_price * package_qty)
            package_name = pack_uom.display_name

        return {
            # identity / context
            "product_id": product.id,
            "product_tmpl_id": product.product_tmpl_id.id,
            "product_display_name": product.display_name,
            "barcode": product.barcode,
            "scanned_term": self._normalize_scan(scan),
            "scanned_as": scanned_as,

            # unit ("قطعة")
            "price": unit_price,
            "uom_id": uom.id,
            "uom_name": uom.display_name,
            "uom_category_id": uom.category_id.id,

            # pack ("التعبئة") — from UoM, not packaging
            "package_qty": package_qty,         # e.g., 12
            "package_price": package_price,     # unit_price * 12 (rounded by currency)
            "package_name": package_name,       # e.g., "Dozens"

            # currency
            "currency_id": currency.id,
            "currency_symbol": currency.symbol,
        }
