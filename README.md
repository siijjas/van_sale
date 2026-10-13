### Van Sale

Van sales and field sales order app for ERPNext: a mobile PWA for drivers and sales reps with orders, payments, stock, returns and POS-style cash shifts.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app van_sale
```

### Setup

The app serves two kinds of field staff from one PWA, chosen per **Van Profile** (Settings → Van Profiles in the app, or the Van Profile doctype):

- **Van Sales** — drivers with stock on board: orders, invoicing, delivery, returns, van loading, stock dashboard, and cash shifts.
- **Field Sales** — order takers without a van: orders and payments only; the back office invoices and delivers. An optional stock warehouse gives them read-only quantities. Shifts are optional.

Shifts work like POS Awesome's: an opening float per payment mode, expenses and cash deposits to the office recorded from the drawer (each posted as a Journal Entry), and a closing that counts every mode against the expected amount. Closings are aggregated by the shift's time window (driver + creation time), never by stamping ERPNext documents. A per-profile **variance tolerance** flags closings that are off (it never blocks); managers can close or reopen any shift.

After pulling changes, migrate and rebuild:

```bash
bench --site <your-site> migrate
cd apps/van_sale/frontend && npm run build
```

Enable the bench scheduler on the site if it is not already: the daily `van_sale.van_sale.tasks.notify_stale_shifts` job notifies managers of shifts left open from earlier days.

Tests run against a site with ERPNext set up:

```bash
bench --site <your-site> run-tests --app van_sale
```

See `PRD.md` for the full screen inventory, doctypes and API modules.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/van_sale
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
# van_sale
