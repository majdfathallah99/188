{
    "name": "HR Time Off: Block Late Submissions",
    "summary": "Block Time Off requests whose start date is more than N days in the past (company policy).",
    "version": "18.0.1.0.0",
    "category": "Human Resources/Leaves",
    "author": "You",
    "license": "LGPL-3",
    "website": "https://example.com",
    "depends": ["hr", "hr_holidays"],
    "data": [
        "views/res_company_view.xml",
        "views/res_config_settings_view.xml"
    ],
    "installable": true,
    "application": false
}
