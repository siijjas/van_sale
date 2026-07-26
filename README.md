### Van Sale

Van sale application for ERPNext.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app van_sale
```

### Van Driver Setup

This app now includes van-sale specific workflow support:

- Driver Configuration: maps each system user to one van warehouse, one source warehouse, allowed payment modes, route, and daily limits.
- Driver Stock Dashboard: mobile stock snapshot for the assigned van warehouse with cached fallback.
- Stock Transfer: simplified Material Transfer flow from main warehouse to van warehouse with batch and serial capture.

After pulling these changes, run the schema migration and rebuild steps from your bench:

```bash
bench --site <your-site> migrate
cd apps/van_sale/frontend && npm run build
```

Managers can then open the PWA and use the Driver Setup screen to configure each driver before field use.

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
