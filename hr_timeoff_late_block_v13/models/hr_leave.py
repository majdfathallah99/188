from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HrLeave(models.Model):
    _inherit = "hr.leave"

    def _get_policy_company(self):
        self.ensure_one()
        return self.company_id or self.employee_id.company_id or self.env.company

    def _get_leave_start_date(self):
        self.ensure_one()
        return self.request_date_from or (self.date_from and self.date_from.date())

    def _get_threshold_days(self, company):
        return max(int(company.late_timeoff_threshold_days or 2), 0)

    def _is_late_beyond_threshold(self, threshold_days, today=None):
        self.ensure_one()
        today = today or fields.Date.context_today(self)
        start_date = self._get_leave_start_date()
        if not start_date:
            return False, 0
        if today <= start_date:
            return False, 0
        delta_days = (today - start_date).days
        return (delta_days > threshold_days), delta_days

    def _enforce_on_submitted(self):
        today = fields.Date.context_today(self)
        for leave in self:
            if leave.state not in ('confirm', 'validate1'):
                continue
            company = leave._get_policy_company()
            if not company or not getattr(company, 'restrict_late_timeoff_submission', False):
                continue
            threshold = self._get_threshold_days(company)
            is_late, delta = leave._is_late_beyond_threshold(threshold_days=threshold, today=today)
            if is_late:
                start_date = leave._get_leave_start_date()
                raise ValidationError(
                    _("Sorry, you cannot submit a Time Off request more than %(n)s day(s) after the start date.\nStart date: %(start)s — Today: %(today)s (difference: %(delta)s days).") % {
                        'n': threshold, 'start': start_date, 'today': today, 'delta': delta
                    }
                )

    def action_confirm(self):
        res = super().action_confirm()
        self._enforce_on_submitted()
        return res

    @api.constrains('state', 'request_date_from', 'date_from')
    def _constrain_late_submission_on_state(self):
        today = fields.Date.context_today(self)
        for leave in self:
            if leave.state in ('confirm', 'validate1'):
                company = leave._get_policy_company()
                if company and getattr(company, 'restrict_late_timeoff_submission', False):
                    threshold = self._get_threshold_days(company)
                    is_late, delta = leave._is_late_beyond_threshold(threshold_days=threshold, today=today)
                    if is_late:
                        start_date = leave._get_leave_start_date()
                        raise ValidationError(
                            _("Sorry, you cannot submit a Time Off request more than %(n)s day(s) after the start date.\nStart date: %(start)s — Today: %(today)s (difference: %(delta)s days).") % {
                                'n': threshold, 'start': start_date, 'today': today, 'delta': delta
                            }
                        )

    @api.model
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs._enforce_on_submitted()
        return recs

    def write(self, vals):
        res = super().write(vals)
        self._enforce_on_submitted()
        return res