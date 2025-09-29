# Copyright LGPL-3
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HrLeave(models.Model):
    _inherit = "hr.leave"

    @api.model
    def _today(self):
        return fields.Date.context_today(self)

    def _check_late_submission_policy(self):
        """Raise ValidationError if submission is too late per company policy."""
        for leave in self:
            company = leave.employee_id.company_id or self.env.company
            if not company.restrict_late_timeoff_submission:
                continue

            threshold = max(int(company.late_timeoff_threshold_days or 0), 0)
            # Resolve the 'start date' shown in the UI
            start_date = leave.request_date_from or (leave.date_from and leave.date_from.date())
            if not start_date:
                # If no date yet, skip
                continue

            today = fields.Date.context_today(leave)
            delta_days = (today - start_date).days
            if delta_days > threshold:
                msg = _(
                    "Late Time Off submission is blocked by company policy.\n"
                    "• Leave: %(name)s\n"
                    "• Start date: %(start)s\n"
                    "• Today: %(today)s\n"
                    "• Threshold: %(thr)s days\n"
                    "This request is %(late)s days late.",
                    name=leave.name or leave.display_name or leave.id,
                    start=start_date,
                    today=today,
                    thr=threshold,
                    late=delta_days,
                )
                raise ValidationError(msg)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_late_submission_policy()
        return records

    def write(self, vals):
        res = super().write(vals)
        self._check_late_submission_policy()
        return res

    def action_submit(self):
        self._check_late_submission_policy()
        return super().action_submit()

    def action_confirm(self):
        self._check_late_submission_policy()
        return super().action_confirm()
