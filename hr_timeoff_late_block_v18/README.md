# HR Time Off: Block Late Submissions (Odoo 18)

Blocks creating/submitting Time Off requests when the start date is more than N days in the past.

## Configuration
- Open **Settings → Companies → Your Company → Configuration → HR Policies**.
- Or **Settings → Employees** (Time Off block) if available.
- Enable **Block Late Time Off Submissions**.
- Set **Late Time Off Threshold (days)** (0 = any past start date is blocked).

## Notes
- Enforced on create/write and on submit/confirm actions.
- Per-company policy (multi-company safe).
- Uses `fields.Date.context_today` to respect user timezone.
