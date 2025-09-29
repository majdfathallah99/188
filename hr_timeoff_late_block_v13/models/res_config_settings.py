from odoo import models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    restrict_late_timeoff_submission = fields.Boolean(
        related='company_id.restrict_late_timeoff_submission',
        readonly=False,
        string='Block late Time Off submissions',
        help='When enabled, employees cannot submit a Time Off request older than the configured threshold (days) from the leave start date.',
        groups="base.group_system,hr.group_hr_manager",
    )
    late_timeoff_threshold_days = fields.Integer(
        related='company_id.late_timeoff_threshold_days',
        readonly=False,
        string='Late submission threshold (days)',
        groups="base.group_system,hr.group_hr_manager",
    )