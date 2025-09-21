/** @odoo-module **/

import { registry } from "@web/core/registry";

/**
 * Some menus open client actions by tag "product_detail_search_barcode_main_menu".
 * If your dashboard registered under a different key (e.g. "product_detail_search.dashboard"),
 * we alias it here so doAction can find it.
 *
 * Safe-by-design: wrapped in try/catch and no-ops if source key isn't found.
 */

const actions = registry.category("actions");
const TARGET_KEY = "product_detail_search_barcode_main_menu";

// Common source keys you might already be using in dashboard.js
const CANDIDATE_SOURCE_KEYS = [
    "product_detail_search.dashboard",
    "product_detail_search.main_menu",
    "product_detail_search.action",
];

(function registerAlias() {
    try {
        for (const src of CANDIDATE_SOURCE_KEYS) {
            try {
                const comp = actions.get(src);
                if (comp) {
                    actions.add(TARGET_KEY, comp);
                    // Stop at the first one that exists
                    return;
                }
            } catch (_e) {
                // ignore; try next candidate
            }
        }
        // If none were found, we leave the registry untouched.
        // This will make the missing-action problem obvious without crashing the webclient.
        console.warn(
            "[product_detail_search] No known dashboard action found to alias. " +
            "Ensure dashboard.js registers one of: " + CANDIDATE_SOURCE_KEYS.join(", ")
        );
    } catch (e) {
        console.warn("[product_detail_search] Failed to register action alias:", e);
    }
})();
