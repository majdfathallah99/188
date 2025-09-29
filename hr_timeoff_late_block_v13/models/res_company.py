from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResCompany(models.Model):
    _inherit = "res.company"

    restrict_late_timeoff_submission = fields.Boolean(
        string="Block late Time Off submissions",
        help="When enabled, employees cannot submit a Time Off request older than the configured threshold (days) from the leave start date.",
        groups="base.group_system,hr.group_hr_manager",
    )
    late_timeoff_threshold_days = fields.Integer(
        string="Late Time Off threshold (days)",
        default=2,
        help="Number of days after the leave start date after which submissions are blocked. 0 = block any past date.",
        groups="base.group_system,hr.group_hr_manager",
    )

    @api.constrains('late_timeoff_threshold_days')
    def _check_threshold_non_negative(self):
        for company in self:
            if company.late_timeoff_threshold_days < 0:
                raise ValidationError(_("Late Time Off threshold must be 0 or a positive number."))