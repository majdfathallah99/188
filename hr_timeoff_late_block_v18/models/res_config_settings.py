from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    restrict_late_timeoff_submission = fields.Boolean(
        related='company_id.restrict_late_timeoff_submission',
        readonly=False
    )
    late_timeoff_threshold_days = fields.Integer(
        related='company_id.late_timeoff_threshold_days',
        readonly=False
    )
