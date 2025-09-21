/** UoM Pack Enricher: ensure the "التعبئة" card gets data from UoM Price lines. */
import { registry } from "@web/core/registry";

const service = {
    start(env) {
        const origCall = env.services.orm.call.bind(env.services.orm);

        env.services.orm.call = async (model, method, args = [], kwargs = {}) => {
            const res = await origCall(model, method, args, kwargs);

            try {
                // Only enrich responses from the product detail fetch
                const isDetail =
                    model === "product.template" &&
                    (method === "product_detail_search" || method === "product_detail_search_uom" || method === "product_detail_search_barcode");

                if (!isDetail || !res || typeof res !== "object") {
                    return res;
                }

                const hasPack = res.package_qty && res.package_price;
                if (hasPack) return res; // nothing to do

                // Figure out product identifier
                let productId = res.product_id;
                if (!productId && res.product_tmpl_id) {
                    const variants = await env.services.orm.searchRead(
                        "product.product",
                        [["product_tmpl_id", "=", res.product_tmpl_id]],
                        ["id"],
                        { limit: 1 }
                    );
                    productId = variants.length ? variants[0].id : null;
                }

                // Ask server for UoM Price line (our helper RPC)
                const payload = productId
                    ? await origCall("product.template", "uom_pack_from_lines", [productId, null])
                    : await origCall("product.template", "uom_pack_from_lines", [null, res.product_tmpl_id]);

                if (payload && payload.has_pack) {
                    res.package_qty = payload.package_qty;
                    res.package_price = payload.package_price;
                    res.package_name = payload.package_name;
                }
            } catch (e) {
                // Don't break the app if anything goes wrong
                console.warn("UoM Pack Enricher error:", e);
            }
            return res;
        };
    },
};

registry.category("services").add("uomPackEnricher", service);
export default service;
