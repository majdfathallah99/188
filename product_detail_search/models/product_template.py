from odoo import models, api

class ProductTemplate(models.Model):
    _inherit = "product.template"

    # normalize Arabic/Persian digits and trim
    def _sanitize_code(self, code):
        s = (code or "").strip()
        trans = str.maketrans("٠١٢٣٤٥٦٧٨٩۰١٢٣٤٥٦٧٨٩", "01234567890123456789")
        return s.translate(trans)

    @api.model
    def product_detail_search(self, barcode):
        """
        product.barcode -> template.barcode -> packaging.barcode
        Then ALWAYS choose a packaging for the located product/template:
          1) if we scanned a packaging, use *that* packaging
          2) else prefer sales=True with the largest quantity
          3) else the largest quantity overall

        Robust to:
          - packaging quantity field name: contained_quantity / qty
          - packaging linkage: product_id (to tmpl) and/or product_tmpl_id
          - archived / multi-company (sudo + active_test=False)
        """
        code = self._sanitize_code(barcode)
        if not code:
            return False

        Product   = self.env["product.product"].sudo().with_context(active_test=False)
        Template  = self.env["product.template"].sudo().with_context(active_test=False)
        Packaging = self.env["product.packaging"].sudo().with_context(active_test=False)

        # ---------- locate product ----------
        product = Product.search([("barcode", "=", code)], limit=1)
        scanned_pack = False

        if not product:
            tmpl = Template.search([("barcode", "=", code)], limit=1)
            if tmpl:
                product = tmpl.product_variant_id or Product.search([("product_tmpl_id", "=", tmpl.id)], limit=1)

        if not product:
            scanned_pack = Packaging.search([("barcode", "=", code)], limit=1)
            if scanned_pack:
                # packaging may link via product_id (tmpl) or product_tmpl_id (older DBs)
                product = scanned_pack.product_id or (
                    hasattr(scanned_pack, "product_tmpl_id")
                    and Product.search([("product_tmpl_id", "=", scanned_pack.product_tmpl_id.id)], limit=1)
                )

        if not product:
            return False

        # ---------- helper funcs ----------
        def _qty_from_rec(pk):
            """Return integer qty from either contained_quantity or qty."""
            if not pk:
                return 0
            if hasattr(pk, "contained_quantity") and pk.contained_quantity is not None:
                try:
                    return int(pk.contained_quantity or 0)
                except Exception:
                    return int(float(pk.contained_quantity or 0))
            if hasattr(pk, "qty") and pk.qty is not None:
                try:
                    return int(pk.qty or 0)
                except Exception:
                    return int(float(pk.qty or 0))
            return 0

        def _build_pack_domain(prod):
            """
            Build a domain that works regardless of whether the packaging model
            has product_id (pointing to tmpl) and/or product_tmpl_id.
            """
            clauses = []
            # If product_id exists, decide whether it expects a product or template id
            if "product_id" in Packaging._fields:
                # Most DBs: product_id -> product.template
                comodel = Packaging._fields["product_id"].comodel_name
                if comodel == "product.template":
                    clauses.append(("product_id", "=", prod.product_tmpl_id.id))
                else:  # extremely rare: product_id -> product.product
                    clauses.append(("product_id", "=", prod.id))
            if "product_tmpl_id" in Packaging._fields:
                clauses.append(("product_tmpl_id", "=", prod.product_tmpl_id.id))

            if not clauses:
                return [("id", "=", 0)]  # no linkage fields -> nothing
            # OR all clauses together
            domain = []
            if len(clauses) == 1:
                domain = clauses
            else:
                # ["|", A, B, "|", (prev), C, ...]
                domain = ["|"] * (len(clauses) - 1)
                for c in clauses:
                    domain.append(c)
            return domain

        # ---------- pick display packaging ----------
        display_pack = False
        if scanned_pack and _qty_from_rec(scanned_pack) >= 1:
            display_pack = scanned_pack
        else:
            packs = Packaging.search(_build_pack_domain(product))
            if packs:
                # Prefer sales=True with the largest quantity
                sales_packs = packs
                if "sales" in Packaging._fields:
                    sales_packs = packs.filtered(lambda r: bool(getattr(r, "sales", False)))
                if sales_packs:
                    display_pack = max(sales_packs, key=_qty_from_rec)
                else:
                    display_pack = max(packs, key=_qty_from_rec)

        package_qty = _qty_from_rec(display_pack)
        unit_price  = product.list_price or 0.0
        package_price = unit_price * package_qty if package_qty else 0.0
        currency = product.currency_id or self.env.company.currency_id

        return [{
            "id": product.id,
            "name": product.display_name,
            "default_code": product.default_code or "",
            "uom": product.uom_id and product.uom_id.display_name or "",
            "price": unit_price,
            "package_qty": int(package_qty),
            "package_price": package_price,
            "currency_symbol": (currency and currency.symbol) or "",
            "scanned_as": "packaging" if scanned_pack else "product",
            "scanned_barcode": code,
        }]
