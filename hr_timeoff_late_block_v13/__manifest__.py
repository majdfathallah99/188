{
    'name': 'Time Off: Block Late Submissions',
    'summary': 'Block Time Off requests submitted after a configurable number of days from the start date.',
    'version': '17.0.1.0.13',
    'author': 'ChatGPT',
    'website': 'https://example.com',
    'license': 'LGPL-3',
    'category': 'Human Resources/Time Off',
    'depends': ['hr', 'hr_holidays'],
    'data': [
        'views/res_config_settings_view.xml'
    ],
    'installable': True,
    'application': False,
}