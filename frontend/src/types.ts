export interface UserSession {
  user: string;
  full_name: string;
  sid: string;
  roles?: string[];
  is_manager?: boolean;
  is_driver?: boolean;
  driver_config?: DriverConfig | null;
}

// The runtime driver config served in UserSession. It is derived entirely from
// the driver's assigned Van Profile (see get_van_profile_for_driver on the
// backend) — `name` is the Van Profile name. There is no separate Driver
// Configuration record; Van Profile is the single source of truth.
export interface DriverConfig {
  name: string;
  profile_name?: string;
  company: string;
  source_warehouse: string;
  van_warehouse: string;
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
  validate_stock_on_save?: boolean;
  ignore_pricing_rule?: boolean;
  disable_rounded_total?: boolean;
  print_format?: string;
  letter_head?: string;
  income_account?: string;
  expense_account?: string;
  cost_center?: string;
  write_off_account?: string;
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
  opening_float: number;
  balance_details: ShiftBalanceDetail[];
  notes?: string;
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
  period_start: string | null;
  payment_reconciliation: PaymentReconciliationRow[];
  total_sales: number;
  total_collections: number;
  total_expenses: number;
  total_opening_float: number;
  expected_cash: number;
}

export interface VanProfile {
  name: string;
  profile_name: string;
  company: string;
  is_active: boolean;
  delivery_route?: string;
  default_cash_mode?: string;
  selling_price_list?: string;
  currency?: string;
  source_warehouse: string;
  van_warehouse: string;
  assigned_drivers: VanProfileDriver[];
  allowed_payment_modes: string[];
  allowed_customer_groups: string[];
  taxes_and_charges?: string;
  apply_discount_on: string;
  daily_credit_limit: number;
  low_stock_threshold: number;
  allow_rate_change: boolean;
  allow_discount_change: boolean;
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
