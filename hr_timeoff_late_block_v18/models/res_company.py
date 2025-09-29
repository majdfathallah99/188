from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResCompany(models.Model):
    _inherit = "res.company"

    restrict_late_timeoff_submission = fields.Boolean(
        string="Block Late Time Off Submissions",
        help="If enabled, employees cannot submit a Time Off request whose start date "
             "is more than the configured number of days in the past."
    )
    late_timeoff_threshold_days = fields.Integer(
        string="Late Time Off Threshold (days)",
        default=2,
        help="Maximum allowed lateness in days for a Time Off request start date. "
             "Example: 2 means a leave starting on the 1st cannot be submitted on/after the 4th."
    )

    def _check_threshold_non_negative(self):
        for company in self:
            if company.late_timeoff_threshold_days is not None and company.late_timeoff_threshold_days < 0:
                raise ValidationError(_("Late Time Off Threshold must be 0 or a positive integer."))

    @api.constrains('late_timeoff_threshold_days')
    def _constrains_threshold(self):
        self._check_threshold_non_negative()
