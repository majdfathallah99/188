/** @odoo-module **/
import { registry } from "@web/core/registry";

const uomPackEnricher = {
  dependencies: ["orm"],
  start(env, { orm }) {
    const origCall = orm.call.bind(orm);
    orm.call = async (model, method, args = [], kwargs = {}) => {
      const res = await origCall(model, method, args, kwargs);
      try {
        const isTarget = model === "product.template" &&
          ["product_detail_search","product_detail_search_uom","product_detail_search_barcode"].includes(method);
        if (!isTarget || !res || typeof res !== "object") return res;
        if (res.package_qty && res.package_price) return res;

        let productId = res.product_id || null;
        const tmplId = res.product_tmpl_id || null;
        if (!productId && tmplId) {
          const variants = await orm.searchRead(
            "product.product", [["product_tmpl_id","=",tmplId]], ["id"], { limit: 1 }
          );
          productId = variants?.length ? variants[0].id : null;
        }
        const payload = await origCall(
          "product.template", "uom_pack_from_lines", [productId || null, tmplId || null], {}
        );
        if (payload?.has_pack) {
          res.package_qty = payload.package_qty;
          res.package_price = payload.package_price;
          res.package_name = payload.package_name;
        }
      } catch (e) {
        console.warn("uomPackEnricher error:", e);
      }
      return res;
    };
  },
};
registry.category("services").add("uomPackEnricher", uomPackEnricher);
export default uomPackEnricher;
