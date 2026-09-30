import type { PeriodReport } from '../types';

// Printed in the browser (new window + window.print()), the same way watch_doctor
// prints its reports — no server-side PDF, so it doesn't depend on wkhtmltopdf being
// able to fetch the site's assets.

interface PrintOptions {
  currency: string;
  periodLabel: string;
  previousLabel: string;
  scope: string;
  formatDelta: (pct: number | null, delta: number) => string;
}

const esc = (v: unknown) =>
  String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
const num = (n?: number | null) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const qty = (n?: number | null) => (n || 0).toLocaleString(undefined, { maximumFractionDigits: 3 });
const day = (s: string) => new Date(`${s}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });

function table(headers: string[], rows: (string | number)[][], opts: { numeric?: number[]; total?: (string | number)[] } = {}) {
  const numeric = new Set(opts.numeric || []);
  const cell = (tag: 'td' | 'th', v: string | number, i: number) => `<${tag}${numeric.has(i) ? ' class="n"' : ''}>${v}</${tag}>`;
  if (!rows.length) return '<p class="muted">Nothing in this period.</p>';
  return `<table>
    <thead><tr>${headers.map((h, i) => cell('th', esc(h), i)).join('')}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((v, i) => cell('td', v, i)).join('')}</tr>`).join('')}</tbody>
    ${opts.total ? `<tfoot><tr>${opts.total.map((v, i) => cell('td', v, i)).join('')}</tr></tfoot>` : ''}
  </table>`;
}

export function printPeriodReport(r: PeriodReport, o: PrintOptions) {
  const t = r.totals;
  const html = `<!doctype html><html><head><meta charset="utf-8"><title>Van sales report · ${esc(o.periodLabel)}</title>
<style>
  @page { size: A4; margin: 14mm; }
  * { box-sizing: border-box; }
  body { font: 11px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; color: #111; margin: 0; }
  h1 { font-size: 18px; margin: 0; }
  h2 { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; margin: 18px 0 6px; padding-bottom: 3px; border-bottom: 1px solid #333; }
  .muted { color: #666; }
  .meta { margin: 4px 0 10px; color: #555; }
  .kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; }
  .kpi { border: 1px solid #ddd; border-radius: 6px; padding: 6px 8px; }
  .kpi b { display: block; font-size: 14px; font-variant-numeric: tabular-nums; }
  table { width: 100%; border-collapse: collapse; page-break-inside: auto; }
  tr { page-break-inside: avoid; }
  th, td { padding: 3px 5px; border-bottom: 1px solid #e3e3e3; text-align: left; vertical-align: top; }
  th { background: #f3f3f3; font-weight: 600; }
  .n { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
  tfoot td { font-weight: 700; border-top: 1px solid #333; border-bottom: none; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
</style></head><body>
  <h1>Van sales report</h1>
  <div class="meta">${esc(o.periodLabel)} · ${esc(o.scope)} · amounts in ${esc(o.currency)} · printed ${esc(new Date().toLocaleString())}</div>

  <div class="kpis">
    <div class="kpi">Sales<b>${num(t.sales)}</b><span class="muted">${t.orders_count} orders</span></div>
    <div class="kpi">Collections<b>${num(t.collections)}</b><span class="muted">${t.payments_count} payments</span></div>
    <div class="kpi">Expenses<b>${num(t.expenses)}</b><span class="muted">${t.expenses_count} entries</span></div>
    <div class="kpi">Returns<b>${num(t.returns)}</b><span class="muted">${t.returns_count} credit notes</span></div>
    <div class="kpi">Net cash<b>${num(t.net_cash)}</b><span class="muted">collections − expenses</span></div>
    <div class="kpi">Cash variance<b>${num(t.variance)}</b><span class="muted">${t.variance_shifts} of ${t.shifts_count} shifts off</span></div>
  </div>

  <h2>Compared with ${esc(o.previousLabel)}</h2>
  ${table(
    ['Metric', 'This period', 'Previous', 'Change'],
    r.comparison.map((c) => [
      esc(c.label),
      c.metric === 'orders_count' ? c.current : num(c.current),
      c.metric === 'orders_count' ? c.previous : num(c.previous),
      esc(o.formatDelta(c.delta_pct, c.delta)),
    ]),
    { numeric: [1, 2, 3] },
  )}

  <h2>By driver</h2>
  ${table(
    ['Driver', 'Van', 'Orders', 'Sales', 'Returns', 'Collected', 'Expenses', 'Net cash', 'Variance'],
    r.by_driver.map((d) => [esc(d.driver_name), esc(d.van_name), d.orders_count, num(d.sales), num(d.returns), num(d.collections), num(d.expenses), num(d.net_cash), num(d.variance)]),
    {
      numeric: [2, 3, 4, 5, 6, 7, 8],
      total: ['Total', '', t.orders_count, num(t.sales), num(t.returns), num(t.collections), num(t.expenses), num(t.net_cash), num(t.variance)],
    },
  )}

  ${r.daily.length > 1 ? `<h2>By day</h2>${table(
    ['Date', 'Sales', 'Returns', 'Collections', 'Expenses'],
    r.daily.filter((d) => d.sales || d.collections || d.expenses || d.returns)
      .map((d) => [esc(day(d.date)), num(d.sales), num(d.returns), num(d.collections), num(d.expenses)]),
    { numeric: [1, 2, 3, 4] },
  )}` : ''}

  <div class="two">
    <div><h2>Collections by mode</h2>${table(
      ['Mode', 'Count', 'Amount'],
      r.collections_by_mode.map((m) => [esc(m.mode_of_payment), m.count, num(m.amount)]),
      { numeric: [1, 2], total: ['Total', t.payments_count, num(t.collections)] },
    )}</div>
    <div><h2>Expenses by type</h2>${table(
      ['Type', 'Count', 'Amount'],
      r.expenses_by_type.map((e) => [esc(e.expense_type), e.count, num(e.amount)]),
      { numeric: [1, 2], total: ['Total', t.expenses_count, num(t.expenses)] },
    )}</div>
  </div>

  <h2>By item group</h2>
  ${table(
    ['Item group', 'Items', 'Sold', 'Returned', 'Net'],
    r.item_groups.map((g) => [esc(g.item_group), g.items, num(g.sold_amount), num(g.returned_amount), num(g.net_amount)]),
    { numeric: [1, 2, 3, 4] },
  )}

  <h2>Items</h2>
  ${table(
    ['Item', 'UOM', 'Sold qty', 'Returned qty', 'Net qty', 'Net amount'],
    r.items.map((i) => [`${esc(i.item_name || i.item_code)} <span class="muted">${esc(i.item_code)}</span>`, esc(i.uom), qty(i.sold_qty), qty(i.returned_qty), qty(i.net_qty), num(i.net_amount)]),
    { numeric: [2, 3, 4, 5] },
  )}
  <p class="muted">Quantities in stock UOM. Amounts after order discounts, before tax.</p>

  <h2>Top customers</h2>
  ${table(
    ['Customer', 'Orders', 'Sales'],
    r.customers.map((c) => [esc(c.customer_name || c.customer), c.orders_count, num(c.sales)]),
    { numeric: [1, 2] },
  )}

  <h2>Closed shifts</h2>
  ${table(
    ['Date', 'Driver', 'Shift', 'Sales', 'Collected', 'Expenses', 'Variance'],
    r.shifts.map((s) => [esc(day(s.shift_date)), esc(s.driver_name), esc(s.name), num(s.total_sales), num(s.total_collections), num(s.total_expenses), num(s.net_difference)]),
    { numeric: [3, 4, 5, 6] },
  )}
</body></html>`;

  const win = window.open('', '_blank', 'width=900,height=700');
  if (!win) {
    window.alert('Allow pop-ups for this site to print the report.');
    return;
  }
  win.document.open();
  win.document.write(html);
  win.document.close();
  let printed = false;
  const go = () => {
    if (printed || win.closed) return;
    printed = true;
    win.focus();
    win.print();
  };
  win.onload = go;
  // Some browsers never fire onload for document.write()'d pages.
  setTimeout(go, 600);
}
