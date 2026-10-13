export interface UserSession {
  user: string;
  full_name: string;
  sid: string;
  roles?: string[];
  is_manager?: boolean;
  is_driver?: boolean;
  driver_config?: DriverConfig | null;
  capabilities?: Capabilities;
}

export type ProfileType = 'Van Sales' | 'Field Sales';

/**
 * What the app lets this staff member do, computed server-side from their Van
 * Profile (utils._capabilities). Screens and buttons gate on these flags, never on
 * profile_type directly, and the endpoints enforce the same flags.
 */
export interface Capabilities {
  is_field_sales: boolean;
  can_invoice: boolean;
  can_deliver: boolean;
  can_return: boolean;
  can_load_stock: boolean;
  can_view_stock: boolean;
  uses_shifts: boolean;
  requires_open_shift: boolean;
}

// The runtime driver config served in UserSession. It is derived entirely from
// the driver's assigned Van Profile (see get_van_profile_for_driver on the
// backend) — `name` is the Van Profile name. There is no separate Driver
// Configuration record; Van Profile is the single source of truth.
export interface DriverConfig {
  name: string;
  profile_name?: string;
  profile_type?: ProfileType;
  company: string;
  /** Van Sales only. Field Sales profiles carry neither warehouse. */
  source_warehouse: string | null;
  van_warehouse: string | null;
  /** Field Sales only: catalog qty is read from here for display. */
  stock_warehouse?: string | null;
  delivery_route?: string;
  daily_credit_limit: number;
  low_stock_threshold: number;
  allow_offline_stock_dashboard: boolean;
  is_active: boolean;
  allowed_payment_modes: string[];
  selling_price_list?: string;
  currency?: string;
  taxes_and_charges?: string;
  apply_discount_on?: string;
  allow_rate_change?: boolean;
  allow_discount_change?: boolean;
  allow_sale_without_stock?: boolean;
  use_shifts?: boolean;
  require_open_shift?: boolean;
  variance_tolerance?: number;
  validate_stock_on_save?: boolean;
  ignore_pricing_rule?: boolean;
  disable_rounded_total?: boolean;
  print_format?: string;
  letter_head?: string;
  income_account?: string;
  expense_account?: string;
  cost_center?: string;
  write_off_account?: string;
  capabilities?: Capabilities;
}

export interface VanProfileDriver {
  driver_user: string;
  driver_full_name?: string;
}

export interface ShiftBalanceDetail {
  mode_of_payment: string;
  opening_amount: number;
}

export interface ActiveShift {
  name: string;
  driver: string;
  shift_date: string;
  status: string;
  company?: string;
  van_profile?: string | null;
  period_start: string | null;
  /** Set once closed; the shift's activity is everything created between period_start and period_end. */
  period_end?: string | null;
  closing_shift?: string | null;
  opening_float: number;
  balance_details: ShiftBalanceDetail[];
  notes?: string;
  /** Opened on an earlier day and never closed — must be closed before a new shift. */
  is_stale?: boolean;
}

export type VarianceStatus = 'Balanced' | 'Within Tolerance' | 'Exceeds Tolerance';

export interface ShiftTaxRow {
  account_head: string;
  rate: number;
  amount: number;
}

/** A draft Sales Order made during the shift and not submitted: not in any total. */
export interface ShiftDraftOrder {
  name: string;
  customer: string;
  customer_name: string | null;
  grand_total: number;
  creation: string;
}

/** Submitted activity on the shift's date from before the shift opened, claimed by no closing. */
export interface OutsideWindow {
  orders_count: number;
  orders_total: number;
  payments_count: number;
  payments_total: number;
}

export interface PaymentReconciliationRow {
  mode_of_payment: string;
  opening_amount: number;
  expected_amount: number;
  closing_amount: number;
  difference: number;
}

export interface ShiftClosingSummary {
  opening_shift: string;
  driver: string;
  driver_name: string;
  shift_date: string;
  /** Opened on an earlier day and never closed. */
  is_stale: boolean;
  period_start: string | null;
  payment_reconciliation: PaymentReconciliationRow[];
  total_sales: number;
  net_total: number;
  total_taxes: number;
  total_quantity: number;
  total_returns: number;
  taxes: ShiftTaxRow[];
  total_collections: number;
  total_expenses: number;
  /** Cash handed to the office mid-shift (Van Cash Movement, type Deposit). */
  total_deposits: number;
  total_opening_float: number;
  expected_cash: number;
  /** From the Van Profile; a net difference beyond it is flagged, never blocked. */
  variance_tolerance: number;
  draft_orders: ShiftDraftOrder[];
  outside_window: OutsideWindow;
}

// ─── Cash movements (cash_movement.py) ───────────────────────────────────────

export type CashMovementType = 'Expense' | 'Deposit';

export interface CashMovement {
  name: string;
  movement_type: CashMovementType;
  amount: number;
  posting_date: string;
  driver: string;
  opening_shift: string;
  expense_account: string | null;
  source_account: string;
  target_account: string;
  against_name: string | null;
  remarks: string | null;
  journal_entry: string | null;
  docstatus: number;
  creation: string;
}

export interface CashMovementContext {
  opening_shift: string | null;
  allow_expense: boolean;
  allow_cash_deposit: boolean;
  require_remarks: boolean;
  max_amount: number;
  cash_account: string | null;
  back_office_cash_account: string | null;
  default_expense_account: string | null;
  expense_accounts: Array<{ name: string; account_name: string }>;
  movements: CashMovement[];
}

export interface VanProfile {
  name: string;
  profile_name: string;
  profile_type: ProfileType;
  company: string;
  is_active: boolean;
  delivery_route?: string;
  default_cash_mode?: string;
  selling_price_list?: string;
  currency?: string;
  source_warehouse: string | null;
  van_warehouse: string | null;
  stock_warehouse?: string | null;
  assigned_drivers: VanProfileDriver[];
  allowed_payment_modes: string[];
  allowed_customer_groups: string[];
  taxes_and_charges?: string;
  apply_discount_on: string;
  daily_credit_limit: number;
  low_stock_threshold: number;
  allow_rate_change: boolean;
  allow_discount_change: boolean;
  allow_sale_without_stock: boolean;
  use_shifts: boolean;
  require_open_shift: boolean;
  variance_tolerance?: number;
  validate_stock_on_save: boolean;
  allow_offline_stock_dashboard: boolean;
  ignore_pricing_rule: boolean;
  disable_rounded_total: boolean;
  print_format?: string;
  letter_head?: string;
  income_account?: string;
  expense_account?: string;
  cost_center?: string;
  write_off_account?: string;
  // Cash movements (expenses & deposits from the drawer)
  allow_expense: boolean;
  allow_cash_deposit: boolean;
  cash_account?: string | null;
  back_office_cash_account?: string | null;
  cash_movement_max_amount: number;
  require_cash_movement_remarks: boolean;
  allowed_expense_accounts: string[];
  capabilities?: Capabilities;
}

export interface VanProfileOptions {
  warehouses: Array<{ name: string; company: string }>;
  payment_modes: PaymentMode[];
  routes: Array<{ name: string }>;
  customer_groups: Array<{ name: string }>;
  companies: Array<{ name: string; default_currency?: string }>;
  price_lists: Array<{ name: string }>;
  tax_templates: Array<{ name: string; company: string }>;
  currencies: Array<{ name: string }>;
  print_formats: Array<{ name: string; doc_type: string }>;
  users: Array<{ name: string; full_name: string }>;
  cash_accounts: Array<{ name: string; account_name: string; company: string; account_type: string }>;
  expense_accounts: Array<{ name: string; account_name: string; company: string }>;
  cost_centers: Array<{ name: string; company: string }>;
}

export interface DriverSetupOptions {
  users: Array<{ name: string; full_name: string }>;
  warehouses: Array<{ name: string; company: string }>;
  payment_modes: PaymentMode[];
  routes: Array<{ name: string }>;
  companies: Array<{ name: string; default_currency?: string }>;
}


export interface Customer {
  name: string;
  customer_name: string;
  customer_group: string;
  territory: string;
  image?: string;
}

export interface Item {
  item_code: string;
  item_name: string;
  description: string;
  stock_uom: string;
  image?: string;
  item_group: string;
  standard_rate?: number;
  price_list_rate?: number;
  actual_qty?: number;
  has_batch_no?: boolean;
  has_serial_no?: boolean;
}

export interface ItemSalesHistoryRow {
  sales_order: string;
  transaction_date: string;
  customer: string;
  customer_name: string;
  qty: number;
  rate: number;
  amount: number;
}

export interface InvoiceStockShortage {
  item_code: string;
  item_name: string;
  stock_uom: string;
  required_qty: number;
  available_qty: number;
  short_qty: number;
}

export interface InvoiceStockCheck {
  allow_sale_without_stock: boolean;
  short_items: InvoiceStockShortage[];
}

export interface CartLine {
  item: Item;
  qty: number;
  rate?: number;
}

export interface SalesOrderItem {
  item_code: string;
  item_name: string;
  qty: number;
  rate: number;
  amount: number;
  delivery_date?: string;
  stock_uom?: string;
  price_list_rate?: number;
}

export interface SalesOrder {
  name: string;
  customer: string;
  customer_name: string;
  transaction_date: string;
  modified?: string;
  grand_total: number;
  total_taxes_and_charges?: number;
  status: string;
  owner: string;
  docstatus: number;
  items: SalesOrderItem[];
  selling_price_list?: string;
  company?: string;
  delivery_date?: string;
  naming_series?: string;
  order_type?: string;
  per_billed?: number;
  per_delivered?: number;
  additional_discount_percentage?: number;
  discount_amount?: number;
  apply_discount_on?: string;
}
export interface OutstandingInvoice {
  name: string;
  posting_date: string;
  grand_total: number;
  outstanding_amount: number;
  allocated_amount?: number; // UI state
  checked?: boolean; // UI state
}

export interface PaymentReference {
  name: string;
  grand_total: number;
  outstanding_amount: number;
  allocated_amount: number;
}

export interface LedgerEntry {
  posting_date: string;
  voucher_type: string;
  voucher_no: string;
  debit: number;
  credit: number;
  account: string;
}

export interface PaymentMode {
  name: string;
  type: string;
}

export interface SalesOrderSummary {
  name: string;
  transaction_date: string;
  grand_total: number;
  advance_paid: number;
}

export interface CustomerSummary {
  outstanding_balance: number;
  last_invoice?: {
    name: string;
    posting_date: string;
    grand_total: number;
  };
  last_payment?: {
    name: string;
    posting_date: string;
    paid_amount: number;
  };
}

export interface DriverStockItem {
  item_code: string;
  item_name: string;
  stock_uom: string;
  image?: string;
  actual_qty: number;
  reserved_qty: number;
  projected_qty: number;
  has_batch_no: boolean;
  has_serial_no: boolean;
  is_low_stock: boolean;
}

export interface DriverStockDashboard {
  warehouse: string;
  source_warehouse: string;
  company: string;
  low_stock_threshold: number;
  generated_at: string;
  summary: {
    item_count: number;
    low_stock_count: number;
    total_available_qty: number;
    total_reserved_qty: number;
  };
  items: DriverStockItem[];
}

export interface TransferItemDetail {
  item_code: string;
  item_name: string;
  description?: string;
  stock_uom: string;
  image?: string;
  has_batch_no: boolean;
  has_serial_no: boolean;
  source_warehouse: string;
  van_warehouse: string;
  source_qty: number;
  van_qty: number;
  batches: Array<{
    batch_no: string;
    available_qty: number;
  }>;
  serial_nos: string[];
}

export interface StockTransferLine {
  item_code: string;
  item_name: string;
  stock_uom: string;
  qty: number;
  batch_no?: string;
  serial_nos?: string[];
  available_qty: number;
  has_batch_no: boolean;
  has_serial_no: boolean;
}

export interface ShiftReportReconciliationRow {
  mode_of_payment: string;
  opening_amount: number;
  expected_amount: number;
  /** Counted / difference only exist on a closing report — an open shift hasn't been counted. */
  closing_amount: number | null;
  difference: number | null;
}

export interface ShiftReportItem {
  item_code: string;
  item_name: string;
  uom: string;
  sold_qty: number;
  sold_amount: number;
  returned_qty: number;
  returned_amount: number;
  net_qty: number;
}

/** Shift summary (open shift snapshot) or closing report (closed shift) — see shift_report.py. */
export interface ShiftReport {
  report_type: 'summary' | 'closing';
  generated_at: string;
  shift: {
    opening_shift: string;
    closing_shift: string | null;
    driver: string;
    driver_name: string;
    van_profile: string | null;
    company: string;
    currency: string | null;
    shift_date: string;
    period_start: string | null;
    period_end: string | null;
    status: string;
    closed_by?: string | null;
    notes: string | null;
  };
  totals: {
    total_sales: number;
    net_total: number;
    total_taxes: number;
    total_quantity: number;
    total_returns: number;
    variance_tolerance?: number;
    variance_status?: VarianceStatus;
    draft_orders_count?: number;
    total_collections: number;
    total_expenses: number;
    total_deposits: number;
    total_opening_float: number;
    expected_cash: number;
    net_difference?: number;
    sales_orders_count: number;
    invoices_count: number;
    invoiced_total: number;
    returns_count: number;
    returns_total: number;
    net_invoiced: number;
    payments_count: number;
    expenses_count: number;
    deposits_count: number;
  };
  payment_reconciliation: ShiftReportReconciliationRow[];
  collections: Array<{ mode_of_payment: string; count: number; amount: number }>;
  taxes: ShiftTaxRow[];
  /** Legacy expense logs and cash movements of type Expense; expense_type is the account name for the latter. */
  expenses: ShiftReportCashRow[];
  deposits: ShiftReportCashRow[];
  items: ShiftReportItem[];
  /** Only on a summary: drafts can still be submitted while the shift is open. */
  draft_orders: ShiftDraftOrder[];
}

export interface ShiftReportCashRow {
  name: string;
  expense_type: string;
  notes: string | null;
  amount: number;
  journal_entry: string | null;
}

export interface ShiftClosingListRow {
  name: string;
  opening_shift: string;
  driver: string;
  driver_name: string;
  shift_date: string;
  period_start: string | null;
  period_end: string | null;
  total_sales: number;
  total_collections: number;
  net_difference: number;
  variance_status?: VarianceStatus | null;
  closed_by?: string | null;
  draft_orders_count?: number;
}

// ─── Manager reports (manager_report.py) ─────────────────────────────────────

export interface FleetTotals {
  orders_count: number;
  sales: number;
  invoices_count: number;
  invoiced: number;
  returns_count: number;
  returns: number;
  payments_count: number;
  collections: number;
  expenses_count: number;
  expenses: number;
  deposits_count?: number;
  deposits?: number;
  shifts_count: number;
  variance: number;
  variance_shifts: number;
  /** Closings whose variance exceeds the profile tolerance. */
  flagged_shifts?: number;
  draft_orders?: number;
  net_sales: number;
  net_cash: number;
  avg_order: number;
  return_rate: number;
}

export interface FleetDriverInfo {
  driver: string;
  driver_name: string;
  van_profile: string;
  van_name: string;
  profile_type?: ProfileType;
  delivery_route?: string | null;
  uses_shifts?: boolean;
}

export type FleetDriverRow = FleetDriverInfo & FleetTotals;

export interface ManagerDashboardVan extends FleetDriverRow {
  shift_status: 'open' | 'closed' | 'stale' | 'none';
  opening_shift: string | null;
  closing_shift: string | null;
  shift_since: string | null;
  expected_cash: number | null;
  net_difference: number | null;
  variance_status?: VarianceStatus | null;
  draft_orders_count?: number;
}

export interface ManagerAlert {
  level: 'warning' | 'danger' | 'info';
  kind: 'stale_shift' | 'variance' | 'no_shift' | 'draft_orders';
  driver: string;
  reference: string | null;
  title: string;
  body: string;
  amount?: number;
}

export interface ManagerDashboard {
  date: string;
  totals: FleetTotals & { open_shifts?: number; closed_shifts?: number; expected_cash_open?: number };
  vans: ManagerDashboardVan[];
  alerts: ManagerAlert[];
}

export interface PeriodComparisonRow {
  metric: keyof FleetTotals;
  label: string;
  current: number;
  previous: number;
  delta: number;
  delta_pct: number | null;
}

export interface PeriodDailyRow {
  date: string;
  sales: number;
  collections: number;
  expenses: number;
  returns: number;
}

export interface PeriodItemRow {
  item_code: string;
  item_name: string;
  item_group: string | null;
  uom: string;
  sold_qty: number;
  sold_amount: number;
  returned_qty: number;
  returned_amount: number;
  net_qty: number;
  net_amount: number;
}

export interface PeriodShiftRow {
  name: string;
  opening_shift: string;
  driver: string;
  driver_name: string;
  van_name?: string | null;
  shift_date: string;
  period_start: string | null;
  period_end: string | null;
  total_sales: number;
  total_collections: number;
  total_expenses: number;
  expected_cash: number;
  net_difference: number;
  variance_status?: VarianceStatus | null;
  variance_tolerance?: number;
  draft_orders_count?: number;
  closed_by?: string | null;
}

export interface PeriodReport {
  period: { from_date: string; to_date: string; days: number; previous_from: string; previous_to: string };
  totals: FleetTotals;
  previous: FleetTotals;
  comparison: PeriodComparisonRow[];
  daily: PeriodDailyRow[];
  by_driver: FleetDriverRow[];
  collections_by_mode: Array<{ mode_of_payment: string; count: number; amount: number }>;
  expenses_by_type: Array<{ expense_type: string; count: number; amount: number }>;
  items: PeriodItemRow[];
  item_groups: Array<{ item_group: string; sold_amount: number; returned_amount: number; net_amount: number; items: number }>;
  customers: Array<{ customer: string; customer_name: string; orders_count: number; sales: number }>;
  shifts: PeriodShiftRow[];
}

export interface FleetOptions {
  drivers: FleetDriverInfo[];
  vans: Array<{ van_profile: string; van_name: string }>;
}
