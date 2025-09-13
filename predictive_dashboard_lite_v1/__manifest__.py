# -*- coding: utf-8 -*-
{
    'name': 'Predictive Dashboard Lite',
    'version': '1.1.3',
    'summary': 'Predictive analytics for Sales & Inventory with XLSX export and alerts (Odoo 18 CE)',
    'description': '''
Forecast sales & stock with multiple methods (SMA/WMA/ETS), warehouse/location filters,
category aggregation, XLSX export, and low-stock activities/email alerts.
''',
    'category': 'Sales/Inventory',
    'website': 'https://example.com',
    'author': 'Your Name',
    'license': 'LGPL-3',
    'depends': ['sale_management', 'stock', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/predictive_menu.xml',
        'views/predictive_wizard_views.xml',
        'views/predictive_line_views.xml',
        'report/predictive_report.xml',
        'report/predictive_report_action.xml',
        'data/ir_cron_demo.xml'
    ],
    'assets': {
        'web.assets_backend': [
        ]
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}