# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

def post_init_fix_actions(cr, registry):
    """Force-fix the client action type/tag and re-link the Inventory menu."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    MODULE = 'product_detail_search'
    TAG = 'product_detail_search_barcode_main_menu'

    # 1) Ensure the client action exists and is typed
    xmlid_action = f'{MODULE}.product_detail_search_barcode_action_main_menu'
    act = env.ref(xmlid_action, raise_if_not_found=False)
    if not act:
        act = env['ir.actions.client'].create({
            'name': 'Find Product Barcode',
            'type': 'ir.actions.client',
            'tag': TAG,
        })
        env['ir.model.data'].create({
            'name': 'product_detail_search_barcode_action_main_menu',
            'module': MODULE,
            'model': 'ir.actions.client',
            'res_id': act.id,
            'noupdate': False,
        })
    else:
        act.write({'type': 'ir.actions.client', 'tag': TAG})

    # 2) Point our Inventory menu to this action
    menu_xmlid = f'{MODULE}.product_detail_search_barcode_menu'
    menu = env.ref(menu_xmlid, raise_if_not_found=False)
    if menu:
        menu.write({'action': f'ir.actions.client,{act.id}'})

    # 3) Optional: fix app tile action if present
    app_xmlid = f'{MODULE}.action_product_detail_search_app'
    app_act = env.ref(app_xmlid, raise_if_not_found=False)
    if app_act:
        app_act.write({'type': 'ir.actions.client', 'tag': TAG})

    # 4) Hardening: any client action with our tag but wrong/missing type -> fix
    for other in env['ir.actions.client'].search([('tag', '=', TAG)]):
        if other.type != 'ir.actions.client':
            other.write({'type': 'ir.actions.client'})
