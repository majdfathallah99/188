# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta, date
from collections import defaultdict, OrderedDict
import io
import base64
try:
    import xlsxwriter
except Exception:
    xlsxwriter = None


def _daterange(d1, d2):
    cur = d1
    while cur <= d2:
        yield cur
        cur = cur + timedelta(days=1)


class PredictiveDashboardWizard(models.TransientModel):
    _name = 'predictive.dashboard.wizard'
    _description = 'Predictive Dashboard Wizard'

    # اسم التشغيل + عداد السطور لعرضهما في List View
    name = fields.Char(
        string='Run Name',
        default=lambda self: _('Run @ %s') % fields.Datetime.now(),
        help='Label for this compute run'
    )
    line_count = fields.Integer(
        string='Lines',
        compute='_compute_line_count',
        help='Number of forecast lines in this run'
    )

    # --- KPI fields (للاستخدام في كروت الداشبورد) ---
    kpi_total_items = fields.Integer(string='Items')
    kpi_total_forecast = fields.Float(string='Total Forecast')
    kpi_total_onhand = fields.Float(string='Total On Hand')
    kpi_at_risk_count = fields.Integer(string='At Risk (≤ Warn Days)')

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, required=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    location_ids = fields.Many2many('stock.location', string='Locations', domain=[('usage', '=', 'internal')])
    product_category_id = fields.Many2one('product.category', string='Product Category')
    date_from = fields.Date(string='From', default=lambda self: date.today() - timedelta(days=60), required=True)
    date_to = fields.Date(string='To', default=lambda self: date.today(), required=True)
    horizon_days = fields.Integer(string='Forecast Horizon (days)', default=30)
    top_n = fields.Integer(string='Top N', default=20, help='Limit to top N by demand')
    group_by = fields.Selection([('product', 'Product'), ('category', 'Category')], default='product', required=True)
    method = fields.Selection([
        ('sma', 'Simple Moving Average'),
        ('wma', 'Weighted Moving Average'),
        ('ets', 'Exponential Smoothing')
    ], default='sma', required=True)
    wma_window = fields.Integer(string='WMA Window (days)', default=7)
    ets_alpha = fields.Float(string='ETS Alpha (0-1)', default=0.3)
    use_stock_based = fields.Boolean(
        string='Use Stock Moves (outgoing/incoming)', default=False,
        help='If off, uses sales order lines.'
    )
    include_returns = fields.Boolean(string='Include Returns (stock-based only)', default=True)
    warn_threshold_days = fields.Integer(string='Warn if Days till Shortage ≤', default=7)
    create_activities = fields.Boolean(string='Create Activities', default=False)
    send_email_notifications = fields.Boolean(string='Email Current User', default=False)
    line_ids = fields.One2many('predictive.dashboard.line', 'wizard_id', string='Lines')
    state = fields.Selection([('draft', 'Draft'), ('ready', 'Ready')], default='draft')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    # ---------------------------
    # Fix mojibake (wrong-encoded Arabic like Ø§Ù„...)
    # ---------------------------
    def _fix_mojibake(self, s):
        """Attempt to fix UTF-8 text mis-decoded as latin-1 (e.g., Ø§Ù„...)."""
        if not s:
            return s
        try:
            bad_markers = ('Ã', 'Â', 'Ø', 'Ù', 'Ð', 'Ý')
            if any(ch in s for ch in bad_markers):
                return s.encode('latin1').decode('utf-8')
        except Exception:
            pass
        return s

    def _location_domain(self):
        dom = [('usage', '=', 'internal')]
        if self.location_ids:
            dom = [('id', 'in', self.location_ids.ids)]
        elif self.warehouse_id:
            dom = [('id', 'child_of', self.warehouse_id.view_location_id.id)]
        return dom

    def _sale_domain(self):
        dom = [
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.company_id', '=', self.company_id.id),
            ('product_id.type', '!=', 'service'),
            ('order_id.date_order', '>=', self.date_from),
            ('order_id.date_order', '<=', self.date_to),
        ]
        if self.product_category_id:
            dom.append(('product_id.categ_id', 'child_of', self.product_category_id.id))
        if self.warehouse_id:
            dom.append(('order_id.warehouse_id', '=', self.warehouse_id.id))
        return dom

    def _stock_move_domain(self):
        dom = [
            ('company_id', '=', self.company_id.id),
            ('state', '=', 'done'),
            ('product_id.type', '!=', 'service'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]
        if self.product_category_id:
            dom.append(('product_id.categ_id', 'child_of', self.product_category_id.id))
        return dom

    def _read_daily_demand(self):
        series = defaultdict(lambda: defaultdict(float))
        if self.use_stock_based:
            dom = self._stock_move_domain()
            internal_locs = self.env['stock.location'].search(self._location_domain())
            internal_ids = set(internal_locs.ids)
            moves = self.env['stock.move'].search(dom)
            for mv in moves:
                src_internal = mv.location_id.id in internal_ids
                dst_internal = mv.location_dest_id.id in internal_ids
                qty = mv.product_qty
                delta = 0.0
                if src_internal and not dst_internal:
                    delta = qty  # outgoing sale
                elif dst_internal and not src_internal:
                    delta = -qty if self.include_returns else 0.0  # return to stock
                if not delta:
                    continue
                day = fields.Date.to_date(mv.date)
                key = mv.product_id.id if self.group_by == 'product' else mv.product_id.categ_id.id
                series[key][day] += delta
        else:
            Sol = self.env['sale.order.line']
            lines = Sol.search(self._sale_domain())
            for l in lines:
                d = fields.Date.to_date(l.order_id.date_order)
                qty = l.product_uom_qty
                key = l.product_id.id if self.group_by == 'product' else l.product_id.categ_id.id
                series[key][d] += qty

        ordered = {}
        for key, dmap in series.items():
            od = OrderedDict()
            cur = self.date_from
            while cur <= self.date_to:
                od[cur] = dmap.get(cur, 0.0)
                cur += timedelta(days=1)
            ordered[key] = od
        return ordered

    def _rate_from_series(self, daily_series):
        values = list(daily_series.values())
        n = len(values) if values else 1
        if self.method == 'sma':
            return sum(values) / float(max(n, 1))
        elif self.method == 'wma':
            w = int(self.wma_window or 1)
            w = min(w, n)
            if w <= 0:
                return 0.0
            weights = list(range(1, w + 1))
            recent = values[-w:]
            num = sum(v * weights[i] for i, v in enumerate(recent))
            den = sum(weights)
            return (num / den) if den else 0.0
        else:
            alpha = self.ets_alpha if 0.0 <= self.ets_alpha <= 1.0 else 0.3
            s = 0.0
            init = True
            for v in values:
                if init:
                    s = v
                    init = False
                else:
                    s = alpha * v + (1 - alpha) * s
            return s

    def _name_for_key(self, key):
        """Return display name for product/category with mojibake fix."""
        if self.group_by == 'product':
            # إخفاء الكود الافتراضي من display_name لو كان مفعّل
            prod = self.env['product.product'].browse(key).with_context(display_default_code=False)
            name = prod.display_name or prod.name or str(key)
            return self._fix_mojibake(name)
        else:
            cat = self.env['product.category'].browse(key)
            return self._fix_mojibake(cat.display_name)

    def _uom_for_key(self, key):
        if self.group_by == 'product':
            return self.env['product.product'].browse(key).uom_id
        return False

    def _onhand_for_key(self, key):
        Quant = self.env['stock.quant']
        dom = [('company_id', '=', self.company_id.id)]
        locs = self.env['stock.location'].search(self._location_domain())
        if locs:
            dom.append(('location_id', 'in', locs.ids))
        if self.group_by == 'product':
            dom.append(('product_id', '=', key))
            qty = sum(q.quantity for q in Quant.search(dom))
            return qty
        else:
            total = 0.0
            quants = Quant.search(dom)
            for q in quants:
                if q.product_id.categ_id and (q.product_id.categ_id.id == key or q.product_id.categ_id.child_of(key)):
                    total += q.quantity
            return total

    def _post_alerts(self, lines):
        if not (self.create_activities or self.send_email_notifications):
            return
        user = self.env.user
        partner = user.partner_id
        for l in lines:
            if l.days_until_shortage and l.days_until_shortage <= self.warn_threshold_days:
                summary = _('Low-stock alert: %s') % (l.display_key,)
                note = _('On hand: %.2f, Daily rate: %.4f, Shortage date: %s') % (
                    l.stock_onhand or 0.0, l.daily_rate or 0.0, l.shortage_date or 'N/A'
                )
                if self.create_activities:
                    self.env['mail.activity'].create({
                        'res_model_id': self.env['ir.model']._get_id('res.users'),
                        'res_id': user.id,
                        'user_id': user.id,
                        'summary': summary,
                        'note': note,
                        'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                        'date_deadline': fields.Date.today(),
                    })
                if self.send_email_notifications and partner.email:
                    mail = self.env['mail.mail'].create({
                        'subject': summary,
                        'email_to': partner.email,
                        'body_html': '<p>%s</p><p>%s</p>' % (summary, note),
                    })
                    mail.send()

    def action_compute(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('Start date must be before end date.'))
        self.line_ids.unlink()

        series_by_key = self._read_daily_demand()
        lines_vals = []
        for key, od in series_by_key.items():
            daily_rate = self._rate_from_series(od)
            forecast_next = daily_rate * self.horizon_days
            onhand = self._onhand_for_key(key) or 0.0
            days_left = (onhand / daily_rate) if daily_rate > 0 else 0.0
            shortage_date = False
            if daily_rate > 0 and onhand > 0:
                shortage_date = date.today() + timedelta(days=int(days_left))
            lines_vals.append({
                'wizard_id': self.id,
                'key_ref': str(key),
                'display_key': self._name_for_key(key),
                'uom_id': self._uom_for_key(key).id if self._uom_for_key(key) else False,
                'qty_window': sum(od.values()),
                'window_days': len(od),
                'daily_rate': daily_rate,
                'forecast_qty': forecast_next,
                'stock_onhand': onhand,
                'days_until_shortage': days_left if daily_rate > 0 else 0.0,
                'shortage_date': shortage_date,
            })

        lines_vals.sort(key=lambda v: v.get('forecast_qty', 0.0), reverse=True)
        if self.top_n and self.top_n > 0:
            lines_vals = lines_vals[:self.top_n]

        created = self.env['predictive.dashboard.line'].create(lines_vals)
        self.state = 'ready'

        # ---- حساب الـ KPIs بعد إنشاء السطور ----
        self.kpi_total_items = len(created)
        self.kpi_total_forecast = sum(created.mapped('forecast_qty'))
        self.kpi_total_onhand = sum(created.mapped('stock_onhand'))
        self.kpi_at_risk_count = sum(
            1 for l in created
            if (l.days_until_shortage or 0) and l.days_until_shortage <= self.warn_threshold_days
        )
        # -----------------------------------------

        self._post_alerts(created)

        return {
            'type': 'ir.actions.act_window',
            'name': _('Predictive Dashboard'),
            'res_model': 'predictive.dashboard.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_export_xlsx(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Nothing to export. Compute first.'))
        if xlsxwriter is None:
            raise UserError(_('xlsxwriter not available on server.'))

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})
        ws = wb.add_worksheet('Forecast')
        headers = [
            'Key', 'UoM', 'Qty in Window', 'Window Days', 'Daily Rate',
            'Forecast', 'On Hand', 'Days till Shortage', 'Shortage Date'
        ]
        for c, h in enumerate(headers):
            ws.write(0, c, h)
        row = 1
        for l in self.line_ids:
            ws.write(row, 0, l.display_key or '')
            ws.write(row, 1, l.uom_id.display_name if l.uom_id else '')
            ws.write(row, 2, l.qty_window or 0.0)
            ws.write(row, 3, l.window_days or 0)
            ws.write(row, 4, l.daily_rate or 0.0)
            ws.write(row, 5, l.forecast_qty or 0.0)
            ws.write(row, 6, l.stock_onhand or 0.0)
            ws.write(row, 7, l.days_until_shortage or 0.0)
            ws.write(row, 8, str(l.shortage_date or ''))
            row += 1
        wb.close()
        output.seek(0)
        data = base64.b64encode(output.read())

        attach = self.env['ir.attachment'].create({
            'name': 'predictive_forecast.xlsx',
            'type': 'binary',
            'datas': data,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=1' % attach.id,
            'target': 'self',
        }

    def action_print_report(self):
        """
        Return the QWeb PDF action.
        - يحاول عبر XMLID
        - إن لم يوجد: يبحث بالتسمية التقنية
        - إن لم يوجد: يُنشئ ir.actions.report ثم يطبع
        """
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Nothing to print. Compute first.'))

        # 1) حاول بـ XMLID
        try:
            return self.env.ref('predictive_dashboard_lite_v1.action_predictive_report').report_action(self)
        except ValueError:
            pass  # ننتقل للبدائل

        # 2) البحث بالخصائص
        Report = self.env['ir.actions.report'].sudo()
        report = Report.search([
            ('report_type', '=', 'qweb-pdf'),
            ('report_name', '=', 'predictive_dashboard_lite_v1.predictive_report_tmpl'),
            ('model', '=', 'predictive.dashboard.wizard'),
        ], limit=1)

        # 3) إنشاء السجل إن لم يوجد
        if not report:
            report = Report.create({
                'name': 'Predictive Report',
                'model': 'predictive.dashboard.wizard',
                'report_type': 'qweb-pdf',
                'report_name': 'predictive_dashboard_lite_v1.predictive_report_tmpl',
                'print_report_name': "'predictive_report_' + (object.company_id.name or '')",
            })

        # 4) تنفيذ الطباعة
        try:
            return report.report_action(self)
        except Exception as e:
            raise UserError(_(
                "Template not found or invalid.\n"
                "Ensure this template exists and loads:\n"
                "- predictive_dashboard_lite_v1.predictive_report_tmpl\n\n"
                "Original error: %s") % str(e))


class PredictiveDashboardLine(models.TransientModel):
    _name = 'predictive.dashboard.line'
    _description = 'Predictive Dashboard Line'
    _order = 'forecast_qty desc'

    wizard_id = fields.Many2one('predictive.dashboard.wizard', required=True, ondelete='cascade')
    key_ref = fields.Char(string='Key Ref')
    display_key = fields.Char(string='Key')
    uom_id = fields.Many2one('uom.uom', string='UoM')
    qty_window = fields.Float(string='Qty in Window')
    window_days = fields.Integer(string='Window Days')
    daily_rate = fields.Float(string='Daily Rate')
    forecast_qty = fields.Float(string='Forecast (Horizon)')
    stock_onhand = fields.Float(string='On Hand')
    days_until_shortage = fields.Float(string='Days till Shortage')
    shortage_date = fields.Date(string='Est. Shortage Date')
