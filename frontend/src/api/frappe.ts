import type {
  UserSession,
  Customer,
  Item,
  SalesOrder,
  SalesOrderItem,
  OutstandingInvoice,
  PaymentReference,
  LedgerEntry,
  PaymentMode,
  SalesOrderSummary,
  CustomerSummary,
  DriverStockDashboard,
  TransferItemDetail,
  StockTransferLine,
  DriverSetupOptions,
  ActiveShift,
  ShiftBalanceDetail,
  ShiftClosingSummary,
  PaymentReconciliationRow,
  ItemSalesHistoryRow,
} from '../types';

let csrfTokenCache: string | undefined;
let cachedDriverContext: UserSession | null = null;

const CURRENCY_SYMBOLS: Record<string, string> = {
  AED: 'AED',
  EUR: 'EUR',
  GBP: 'GBP',
  INR: '₹',
  KWD: 'KWD',
  OMR: 'OMR',
  QAR: 'QAR',
  SAR: 'SAR',
  USD: '$',
};

const getCsrfToken = () => {
  if (csrfTokenCache) return csrfTokenCache;
  const stored = localStorage.getItem('csrf_token') || sessionStorage.getItem('csrf_token');
  if (stored) {
    csrfTokenCache = stored;
    return csrfTokenCache;
  }
  const fromDesk = (window as any).frappe?.csrf_token;
  if (fromDesk) {
    csrfTokenCache = fromDesk;
    return csrfTokenCache;
  }
  const injected = (window as any).csrf_token;
  if (injected) {
    csrfTokenCache = injected;
    return csrfTokenCache;
  }
  const meta = document.querySelector('meta[name="csrf-token"]') as HTMLMetaElement | null;
  if (meta?.content) {
    csrfTokenCache = meta.content;
    return csrfTokenCache;
  }
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]+)/);
  if (match) {
    csrfTokenCache = decodeURIComponent(match[1]);
    return csrfTokenCache;
  }
  return undefined;
};

// No network call; rely on cookie/meta/window. If unavailable, requests may fail and surface real error.
const refreshCsrfToken = async () => getCsrfToken();

const defaultHeaders = (): Record<string, string> => {
  const csrf = getCsrfToken();
  const headers: Record<string, string> = {
    'Accept': 'application/json',
  };
  if (csrf) {
    headers['X-Frappe-CSRF-Token'] = csrf;
  }
  return headers;
};

const getCurrencySymbolFallback = (currency: string | null | undefined) => {
  if (!currency) return null;
  return CURRENCY_SYMBOLS[currency] || currency;
};

// Frappe's `_server_messages` is a JSON-encoded array of JSON-encoded
// `{message, title, ...}` objects (double-encoded) — pull the human-readable
// `message` out of each rather than surfacing the raw encoded string.
function extractServerMessages(raw: unknown): string[] {
  if (!raw) return [];
  try {
    const list = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (!Array.isArray(list)) return [];
    return list
      .map((entry: unknown) => {
        if (typeof entry !== 'string') return '';
        try {
          const parsed = JSON.parse(entry);
          return typeof parsed === 'object' && parsed ? (parsed.message ?? '') : String(parsed);
        } catch (_e) {
          return entry;
        }
      })
      .map((m) => String(m).replace(/<[^>]*>/g, '').trim())
      .filter(Boolean);
  } catch (_e) {
    return [];
  }
}

function extractErrorMessage(data: Record<string, unknown>, fallback: string): string {
  const serverMessages = extractServerMessages(data._server_messages);
  if (serverMessages.length) return serverMessages.join(' ');
  if (typeof data.message === 'string' && data.message.trim()) {
    return data.message.replace(/<[^>]*>/g, '').trim();
  }
  if (typeof data.exception === 'string' && data.exception.trim()) {
    // e.g. "frappe.exceptions.PermissionError: You can only close your own shift."
    const firstLine = data.exception.split('\n')[0];
    return firstLine.replace(/^[\w.]+Error:\s*/, '').trim() || fallback;
  }
  return fallback;
}

const handleResponse = async (res: Response) => {
  if (!res.ok) {
    const text = await res.text();
    let data: Record<string, unknown> | null = null;
    try {
      data = JSON.parse(text);
    } catch (_e) {
      // Response body isn't JSON — fall through to the plain-text path below.
    }
    if (data && typeof data === 'object') {
      throw new Error(extractErrorMessage(data, res.statusText));
    }
    const plain = text.replace(/<[^>]*>/g, '').trim();
    throw new Error((plain ? plain.slice(0, 240) : '') || res.statusText);
  }
  return res.json();
};

export async function login(username: string, password: string): Promise<UserSession> {
  const res = await fetch('/api/method/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    credentials: 'include',
    body: JSON.stringify({ usr: username, pwd: password }),
  });
  const data = await handleResponse(res);
  if (data?.csrf_token) {
    csrfTokenCache = data.csrf_token;
    localStorage.setItem('csrf_token', data.csrf_token);
  } else {
    await refreshCsrfToken();
  }
  cachedDriverContext = null;
  return getSession();
}

export async function logout(): Promise<void> {
  await refreshCsrfToken();
  const res = await fetch('/api/method/logout', {
    method: 'POST',
    headers: { ...defaultHeaders() },
    credentials: 'include',
  });
  if (!res.ok) {
    // Clear local state even if server logout fails, but surface the message
    const text = await res.text();
    const err = text || res.statusText || 'Logout failed';
    csrfTokenCache = undefined;
    localStorage.removeItem('csrf_token');
    sessionStorage.removeItem('csrf_token');
    throw new Error(err);
  }
  csrfTokenCache = undefined;
  cachedDriverContext = null;
  localStorage.removeItem('csrf_token');
  sessionStorage.removeItem('csrf_token');
}

export async function getSession(): Promise<UserSession> {
  if (cachedDriverContext) {
    return cachedDriverContext;
  }

  const res = await fetch('/api/method/van_sale.van_sale.driver.get_app_context', {
    credentials: 'include',
    headers: defaultHeaders(),
  });
  const data = await handleResponse(res);
  const context = data.message as UserSession | undefined;
  if (!context?.user) {
    throw new Error('No active session');
  }
  cachedDriverContext = context;
  return context;
}

export async function searchCustomers(txt: string): Promise<Customer[]> {
  const params = new URLSearchParams({
    fields: JSON.stringify(['name', 'customer_name', 'customer_group', 'territory']),
    filters: JSON.stringify(txt ? [['Customer', 'customer_name', 'like', `%${txt}%`]] : []),
    page_length: '20',
    limit_start: '0',
  });
  const res = await fetch(`/api/resource/Customer?${params.toString()}`, {
    method: 'GET',
    credentials: 'include',
  });
  const data = await handleResponse(res);
  return (data.data || data.message || []) as Customer[];
}

export async function createCustomer(customerName: string, mobileNo?: string): Promise<Customer> {
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.sales.create_customer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    credentials: 'include',
    body: JSON.stringify({ customer_name: customerName, ...(mobileNo ? { mobile_no: mobileNo } : {}) }),
  });
  const data = await handleResponse(res);
  return data.message as Customer;
}

let cachedSellingPriceList: string | null = null;
let cachedDefaultCompany: string | null = null;
const cachedCompanyCurrency: Record<string, string> = {};
let cachedDefaultWarehouse: string | null = null;

export async function getDriverContext(): Promise<UserSession> {
  return getSession();
}

async function getSellingPriceList(): Promise<string | null> {
  if (cachedSellingPriceList !== null) return cachedSellingPriceList;
  try {
    const res = await fetch('/api/resource/Selling Settings/Selling Settings', {
      method: 'GET',
      headers: { ...defaultHeaders() },
      credentials: 'include',
    });
    const data = await handleResponse(res);
    cachedSellingPriceList = data.data?.selling_price_list || data.message?.selling_price_list || null;
    return cachedSellingPriceList;
  } catch (e) {
    cachedSellingPriceList = null;
    return null;
  }
}

async function getDefaultCompany(): Promise<string | null> {
  if (cachedDefaultCompany !== null) return cachedDefaultCompany;
  const context = await getSession().catch(() => null);
  if (context?.driver_config?.company) {
    cachedDefaultCompany = context.driver_config.company;
    return cachedDefaultCompany;
  }
  try {
    const res = await fetch('/api/resource/Global Defaults/Global Defaults', {
      method: 'GET',
      headers: { ...defaultHeaders() },
      credentials: 'include',
    });
    const data = await handleResponse(res);
    cachedDefaultCompany = data.data?.default_company || data.message?.default_company || null;
    return cachedDefaultCompany;
  } catch (_e) {
    cachedDefaultCompany = null;
    return null;
  }
}

async function getCompanyCurrency(company?: string | null): Promise<string | null> {
  const comp = company || (await getDefaultCompany());
  if (!comp) return null;
  if (cachedCompanyCurrency[comp]) return cachedCompanyCurrency[comp];
  try {
    const res = await fetch(`/api/resource/Company/${encodeURIComponent(comp)}?fields=${encodeURIComponent('["default_currency"]')}`, {
      method: 'GET',
      headers: { ...defaultHeaders() },
      credentials: 'include',
    });
    const data = await handleResponse(res);
    const currency = data.data?.default_currency || data.message?.default_currency || null;
    if (currency) cachedCompanyCurrency[comp] = currency;
    return currency;
  } catch (_e) {
    return null;
  }
}

export async function getCompanyCurrencyInfo(): Promise<{ currency: string | null; symbol: string | null }> {
  const currency = await getCompanyCurrency();
  const symbol = getCurrencySymbolFallback(currency);
  return { currency, symbol };
}

async function getDefaultWarehouse(): Promise<string | null> {
  if (cachedDefaultWarehouse !== null) return cachedDefaultWarehouse;
  const context = await getSession().catch(() => null);
  if (context?.driver_config?.van_warehouse) {
    cachedDefaultWarehouse = context.driver_config.van_warehouse;
    return cachedDefaultWarehouse;
  }
  const company = await getDefaultCompany();
  if (!company) {
    cachedDefaultWarehouse = null;
    return null;
  }
  try {
    const res = await fetch(
      `/api/resource/Company/${encodeURIComponent(company)}?fields=${encodeURIComponent('["default_warehouse","default_receipt_warehouse"]')}`,
      {
        method: 'GET',
        headers: { ...defaultHeaders() },
        credentials: 'include',
      },
    );
    const data = await handleResponse(res);
    cachedDefaultWarehouse =
      data.data?.default_warehouse ||
      data.data?.default_receipt_warehouse ||
      data.message?.default_warehouse ||
      data.message?.default_receipt_warehouse ||
      null;
    return cachedDefaultWarehouse;
  } catch (_e) {
    cachedDefaultWarehouse = null;
    return null;
  }
}

const DEFAULT_SELLING_PRICE_LIST = 'Standard Selling';
const DEFAULT_NAMING_SERIES = 'SO-';
export async function listItems(search?: string, customer?: string): Promise<Item[]> {
  const filters = [['is_sales_item', '=', 1], ['disabled', '=', 0]];
  const or_filters = search
    ? [
      ['item_name', 'like', `%${search}%`],
      ['item_code', 'like', `%${search}%`],
      ['name', 'like', `%${search}%`],
      ['description', 'like', `%${search}%`],
    ]
    : undefined;

  const params = new URLSearchParams({
    fields: JSON.stringify(['name as item_code', 'item_name', 'description', 'stock_uom', 'image', 'item_group', 'standard_rate']),
    filters: JSON.stringify(filters.map((f) => ['Item', ...f])),
    ...(or_filters ? { or_filters: JSON.stringify(or_filters.map((f) => ['Item', ...f])) } : {}),
    page_length: '40',
  });

  const res = await fetch(`/api/resource/Item?${params.toString()}`, {
    method: 'GET',
    credentials: 'include',
  });
  const data = await handleResponse(res);
  const items = (data.data || data.message || []) as Item[];

  // Prefer the driver's own Van Profile price list (their "special" pricing,
  // e.g. "For special customers") over the global Selling Settings default —
  // matching what createSalesOrder() already does. Falling back to the global
  // default here was the bug: a driver assigned a special price list never
  // actually saw their special prices in the catalog.
  const session = await getSession().catch(() => null);
  const globalPriceList = (await getSellingPriceList()) || DEFAULT_SELLING_PRICE_LIST;
  const priceList = session?.driver_config?.selling_price_list || globalPriceList;
  const defaultWarehouse = await getDefaultWarehouse();
  if (!items.length) {
    return items;
  }

  try {
    const codes = items.map((i) => i.item_code);
    const priceMap: Record<string, number> = {};
    const stockMap: Record<string, number> = {};

    const fetchPrices = async (filters: any[]) => {
      const priceParams = new URLSearchParams({
        fields: JSON.stringify(['item_code', 'price_list_rate']),
        filters: JSON.stringify(filters),
        page_length: String(codes.length),
      });
      const priceRes = await fetch(`/api/resource/Item Price?${priceParams.toString()}`, {
        method: 'GET',
        credentials: 'include',
      });
      const priceData = await handleResponse(priceRes);
      (priceData.data || priceData.message || []).forEach((row: any) => {
        if (row.item_code && priceMap[row.item_code] === undefined) {
          priceMap[row.item_code] = row.price_list_rate;
        }
      });
    };

    // 1. Customer-specific price (negotiated per customer) — highest priority.
    if (customer) {
      await fetchPrices([
        ['Item Price', 'customer', '=', customer],
        ['Item Price', 'selling', '=', 1],
        ['Item Price', 'item_code', 'in', codes],
      ]);
    }

    // 2. The driver's own ("special") price list.
    await fetchPrices([
      ['Item Price', 'price_list', '=', priceList],
      ['Item Price', 'selling', '=', 1],
      ['Item Price', 'item_code', 'in', codes],
    ]);

    // 3. The standard price list specifically, as the named "backup" — not
    // just any other price list, so an unrelated/misconfigured list can't be
    // picked up by accident.
    let missingCodes = codes.filter((c) => priceMap[c] === undefined);
    if (missingCodes.length && priceList !== DEFAULT_SELLING_PRICE_LIST) {
      await fetchPrices([
        ['Item Price', 'price_list', '=', DEFAULT_SELLING_PRICE_LIST],
        ['Item Price', 'selling', '=', 1],
        ['Item Price', 'item_code', 'in', missingCodes],
      ]);
    }

    // 4. Last resort: any other selling price at all (covers the standard
    // list itself being missing/misconfigured).
    missingCodes = codes.filter((c) => priceMap[c] === undefined);
    if (missingCodes.length) {
      await fetchPrices([
        ['Item Price', 'selling', '=', 1],
        ['Item Price', 'item_code', 'in', missingCodes],
      ]);
    }

    const fetchBins = async (filters: any[]) => {
      const binParams = new URLSearchParams({
        fields: JSON.stringify(['item_code', 'actual_qty']),
        filters: JSON.stringify(filters),
        page_length: String(Math.max(codes.length, 20)),
      });
      const binRes = await fetch(`/api/resource/Bin?${binParams.toString()}`, {
        method: 'GET',
        credentials: 'include',
      });
      const binData = await handleResponse(binRes);
      (binData.data || binData.message || []).forEach((row: any) => {
        if (row.item_code) {
          stockMap[row.item_code] = (stockMap[row.item_code] || 0) + (row.actual_qty || 0);
        }
      });
    };

    if (defaultWarehouse) {
      await fetchBins([
        ['item_code', 'in', codes],
        ['warehouse', '=', defaultWarehouse],
      ]);
    }

    // If default warehouse had no stock rows, fall back to all warehouses
    const hasAnyStock = codes.some((c) => stockMap[c] !== undefined);
    if (!hasAnyStock) {
      await fetchBins([['item_code', 'in', codes]]);
    }

    return items.map((item) => ({
      ...item,
      price_list_rate: priceMap[item.item_code],
      actual_qty: stockMap[item.item_code] ?? null,
      standard_rate: priceMap[item.item_code] ?? item.standard_rate,
    }));
  } catch (_e) {
    return items;
  }
}

export async function createSalesOrder(payload: {
  customer: string;
  items: SalesOrderItem[];
  discountPercent?: number;
  discountAmount?: number;
}): Promise<SalesOrder> {
  // The document is assembled server-side by van_sale.van_sale.sales.create_sales_order:
  // company, price list, currency, taxes, payment schedule and every total come from the
  // driver's Van Profile and ERPNext's own calculation, not from this client. That is what
  // lets the Van Sales Driver role hold read-only DocPerms on Sales Order.
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.sales.create_sales_order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    credentials: 'include',
    body: JSON.stringify({
      customer: payload.customer,
      items: payload.items.map((i) => ({ item_code: i.item_code, qty: i.qty, rate: i.rate ?? 0 })),
      discount_percent: payload.discountPercent || 0,
      discount_amount: payload.discountAmount || 0,
    }),
  });
  const data = await handleResponse(res);
  return data.message as SalesOrder;
}

export async function getSalesOrder(name: string): Promise<SalesOrder> {
  const res = await fetch(`/api/resource/Sales Order/${encodeURIComponent(name)}`, {
    method: 'GET',
    headers: { ...defaultHeaders() },
    credentials: 'include',
  });
  const data = await handleResponse(res);
  return (data.data || data.message) as SalesOrder;
}

export async function updateSalesOrder(
  name: string,
  payload: { items: SalesOrderItem[]; customer: string; discountPercent?: number; discountAmount?: number },
): Promise<SalesOrder> {
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.sales.update_sales_order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    credentials: 'include',
    body: JSON.stringify({
      name,
      customer: payload.customer,
      items: payload.items.map((i) => ({ item_code: i.item_code, qty: i.qty, rate: i.rate ?? 0 })),
      discount_percent: payload.discountPercent || 0,
      discount_amount: payload.discountAmount || 0,
    }),
  });
  const data = await handleResponse(res);
  return data.message as SalesOrder;
}

export async function submitSalesOrder(name: string): Promise<SalesOrder> {
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.sales.submit_sales_order', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    credentials: 'include',
    body: JSON.stringify({ name }),
  });
  const data = await handleResponse(res);
  return (data.data || data.message) as SalesOrder;
}

export async function getItemSalesHistory(itemCode: string, customer?: string, limit = 20): Promise<ItemSalesHistoryRow[]> {
  const params = new URLSearchParams({
    item_code: itemCode,
    limit: String(limit),
    ...(customer ? { customer } : {}),
  });
  const res = await fetch(`/api/method/van_sale.van_sale.sales.get_item_sales_history?${params.toString()}`, {
    method: 'GET',
    headers: { ...defaultHeaders() },
    credentials: 'include',
  });
  const data = await handleResponse(res);
  return (data.message || []) as ItemSalesHistoryRow[];
}

export async function createSalesInvoice(
  salesOrder: string,
  options?: { markAsPaid?: boolean; modeOfPayment?: string },
): Promise<string> {
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.sales.create_sales_invoice', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    credentials: 'include',
    body: JSON.stringify({
      sales_order: salesOrder,
      ...(options?.markAsPaid
        ? { mark_as_paid: 1, mode_of_payment: options.modeOfPayment }
        : {}),
    }),
  });
  const data = await handleResponse(res);
  return (data.message || data.data) as string;
}

export interface RecentOrdersOptions {
  search?: string;
  fromDate?: string;
  toDate?: string;
  limitStart?: number;
  pageLength?: number;
}

export async function recentOrders(owner: string, options?: RecentOrdersOptions): Promise<SalesOrder[]> {
  const filters: any[] = [
    ['Sales Order', 'owner', '=', owner],
    ['Sales Order', 'docstatus', '!=', 2],
  ];
  if (options?.fromDate) filters.push(['Sales Order', 'transaction_date', '>=', options.fromDate]);
  if (options?.toDate) filters.push(['Sales Order', 'transaction_date', '<=', options.toDate]);

  const search = options?.search?.trim();
  const orFilters = search
    ? [
      ['Sales Order', 'customer_name', 'like', `%${search}%`],
      ['Sales Order', 'name', 'like', `%${search}%`],
    ]
    : undefined;

  const params = new URLSearchParams({
    fields: JSON.stringify([
      'name',
      'customer',
      'customer_name',
      'transaction_date',
      'grand_total',
      'status',
      'owner',
      'docstatus',
    ]),
    filters: JSON.stringify(filters),
    ...(orFilters ? { or_filters: JSON.stringify(orFilters) } : {}),
    order_by: 'creation desc',
    page_length: String(options?.pageLength ?? 20),
    limit_start: String(options?.limitStart ?? 0),
  });
  const res = await fetch(`/api/resource/Sales Order?${params.toString()}`, {
    method: 'GET',
    credentials: 'include',
  });
  const data = await handleResponse(res);
  return (data.data || data.message || []) as SalesOrder[];
}

export async function findDraftOrder(customer: string, owner?: string): Promise<SalesOrder | null> {
  const filters: any[] = [
    ['Sales Order', 'customer', '=', customer],
    ['Sales Order', 'docstatus', '=', 0],
  ];
  if (owner) {
    filters.push(['Sales Order', 'owner', '=', owner]);
  }
  const params = new URLSearchParams({
    fields: JSON.stringify(['name']),
    filters: JSON.stringify(filters),
    order_by: 'creation desc',
    page_length: '1',
  });
  const res = await fetch(`/api/resource/Sales Order?${params.toString()}`, {
    method: 'GET',
    credentials: 'include',
  });
  const data = await handleResponse(res);
  const list = (data.data || data.message || []) as { name: string }[];
  if (!list.length) return null;
  return getSalesOrder(list[0].name);
}

export async function getOutstandingInvoices(customer: string): Promise<OutstandingInvoice[]> {
  const res = await fetch(`/api/method/van_sale.van_sale.finance.get_outstanding_invoices?customer=${encodeURIComponent(customer)}`, {
    method: 'GET',
    credentials: 'include',
  });
  const data = await handleResponse(res);
  return (data.message || []) as OutstandingInvoice[];
}

export async function getPaymentModes(): Promise<PaymentMode[]> {
  const res = await fetch('/api/method/van_sale.van_sale.finance.get_payment_modes', {
    method: 'GET',
    credentials: 'include',
  });
  const data = await handleResponse(res);
  return (data.message || []) as PaymentMode[];
}

export async function getAllPaymentModes(): Promise<PaymentMode[]> {
  const res = await fetch('/api/method/van_sale.van_sale.driver.get_driver_setup_options', {
    method: 'GET',
    credentials: 'include',
    headers: defaultHeaders(),
  });
  const data = await handleResponse(res);
  return (data.message?.payment_modes || []) as PaymentMode[];
}

export async function getSalesOrders(customer: string): Promise<SalesOrderSummary[]> {
  const params = new URLSearchParams({ customer });
  const res = await fetch(`/api/method/van_sale.van_sale.sales.get_sales_orders?${params.toString()}`, {
    headers: defaultHeaders(),
    credentials: 'include',
  });
  const data = await handleResponse(res);
  return (data.message || []) as SalesOrderSummary[];
}

export async function getCustomerSummary(customer: string): Promise<CustomerSummary> {
  const params = new URLSearchParams({ customer });
  const res = await fetch(`/api/method/van_sale.van_sale.finance.get_customer_summary?${params.toString()}`, {
    headers: defaultHeaders(),
    credentials: 'include',
  });
  const data = await handleResponse(res);
  return data.message as CustomerSummary;
}

export async function createPaymentEntry(
  customer: string,
  modeOfPayment: string,
  paidAmount: number,
  references: PaymentReference[],
  salesOrder?: string,
): Promise<string> {
  const payload: any = {
    customer,
    mode_of_payment: modeOfPayment,
    paid_amount: paidAmount,
    references: JSON.stringify(references),
  };

  if (salesOrder) {
    payload.sales_order = salesOrder;
  }

  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.finance.create_payment_entry', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    credentials: 'include',
    body: JSON.stringify(payload),
  });
  const data = await handleResponse(res);
  return data.message;
}

export async function getCustomerLedger(
  customer: string,
  fromDate?: string,
  toDate?: string,
): Promise<{ opening_balance: number; entries: LedgerEntry[] }> {
  const params = new URLSearchParams({ customer });
  if (fromDate) params.append('from_date', fromDate);
  if (toDate) params.append('to_date', toDate);

  const res = await fetch(`/api/method/van_sale.van_sale.finance.get_customer_ledger?${params.toString()}`, {
    method: 'GET',
    credentials: 'include',
  });
  const data = await handleResponse(res);
  return data.message;
}

export async function getDailySummary(): Promise<{ sales_orders: { count: number; total: number }; payments: { count: number; total: number } }> {
  const res = await fetch('/api/method/van_sale.van_sale.sales.get_daily_summary', {
    method: 'GET',
    credentials: 'include',
  });
  const data = await handleResponse(res);
  return data.message;
}
export async function getDailyLog(doctype: 'Sales Order' | 'Payment Entry') {
  const params = new URLSearchParams({
    doctype,
    _: Date.now().toString()
  });
  const res = await fetch(`/api/method/van_sale.van_sale.sales.get_daily_log?${params.toString()}`, {
    method: 'GET',
    credentials: 'include',
  });
  const data = await handleResponse(res);
  return data.message || [];
}

export async function getPaymentEntry(name: string) {
  const res = await fetch(`/api/resource/Payment Entry/${name}`, {
    method: 'GET',
    credentials: 'include',
  });
  const data = await handleResponse(res);
  return data.data;
}

export async function getDriverStockDashboard(forceRefresh = false): Promise<DriverStockDashboard> {
  const params = new URLSearchParams();
  if (forceRefresh) {
    params.set('force_refresh', '1');
  }
  const suffix = params.toString() ? `?${params.toString()}` : '';
  const res = await fetch(`/api/method/van_sale.van_sale.inventory.get_driver_stock_dashboard${suffix}`, {
    method: 'GET',
    credentials: 'include',
    headers: defaultHeaders(),
  });
  const data = await handleResponse(res);
  return data.message as DriverStockDashboard;
}

export async function searchTransferItems(search = ''): Promise<Item[]> {
  const params = new URLSearchParams();
  if (search.trim()) params.set('search', search.trim());
  const res = await fetch(`/api/method/van_sale.van_sale.inventory.search_transfer_items?${params.toString()}`, {
    method: 'GET',
    credentials: 'include',
    headers: defaultHeaders(),
  });
  const data = await handleResponse(res);
  return (data.message || []) as Item[];
}

export async function getTransferItemDetail(itemCode: string): Promise<TransferItemDetail> {
  const params = new URLSearchParams({ item_code: itemCode });
  const res = await fetch(`/api/method/van_sale.van_sale.inventory.get_transfer_item_detail?${params.toString()}`, {
    method: 'GET',
    credentials: 'include',
    headers: defaultHeaders(),
  });
  const data = await handleResponse(res);
  return data.message as TransferItemDetail;
}

export async function createStockTransfer(lines: StockTransferLine[], remarks = '') {
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.inventory.create_stock_transfer', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    body: JSON.stringify({
      items: JSON.stringify(lines.map((line) => ({
        item_code: line.item_code,
        qty: line.qty,
        batch_no: line.batch_no,
        serial_nos: line.serial_nos || [],
      }))),
      remarks,
      submit: 1,
    }),
  });
  const data = await handleResponse(res);
  return data.message as {
    name: string;
    docstatus: number;
    posting_date: string;
    from_warehouse: string;
    to_warehouse: string;
  };
}

export async function getDriverSetupOptions(): Promise<DriverSetupOptions> {
  const res = await fetch('/api/method/van_sale.van_sale.driver.get_driver_setup_options', {
    method: 'GET',
    credentials: 'include',
    headers: defaultHeaders(),
  });
  const data = await handleResponse(res);
  return data.message as DriverSetupOptions;
}

export async function createSalesReturn(
  customer: string,
  items: { item_code: string; qty: number; rate?: number }[],
): Promise<string> {
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.sales.create_sales_return', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    body: JSON.stringify({ customer, items }),
  });
  const data = await handleResponse(res);
  return data.message;
}

export async function getActiveShift(): Promise<ActiveShift | null> {
  const res = await fetch('/api/method/van_sale.van_sale.shift.get_active_shift', {
    method: 'GET',
    credentials: 'include',
    headers: defaultHeaders(),
  });
  const data = await handleResponse(res);
  return (data.message as ActiveShift | null) ?? null;
}

export async function openShift(balanceDetails: ShiftBalanceDetail[], notes?: string): Promise<ActiveShift> {
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.shift.open_shift', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    body: JSON.stringify({ balance_details: JSON.stringify(balanceDetails), notes }),
  });
  const data = await handleResponse(res);
  return data.message as ActiveShift;
}

export async function getShiftClosingSummary(): Promise<ShiftClosingSummary> {
  const res = await fetch('/api/method/van_sale.van_sale.shift.get_shift_closing_summary', {
    method: 'GET',
    credentials: 'include',
    headers: defaultHeaders(),
  });
  const data = await handleResponse(res);
  return data.message as ShiftClosingSummary;
}

export async function closeShift(
  openingShift: string,
  reconciliation: PaymentReconciliationRow[],
  notes?: string,
): Promise<{ name: string; net_difference: number }> {
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.shift.close_shift', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    body: JSON.stringify({
      opening_shift: openingShift,
      reconciliation: JSON.stringify(reconciliation),
      notes,
    }),
  });
  const data = await handleResponse(res);
  return data.message;
}

export async function getRouteExpenses(): Promise<any[]> {
  const res = await fetch('/api/method/van_sale.van_sale.finance.get_route_expenses', {
    method: 'GET',
    credentials: 'include',
    headers: defaultHeaders(),
  });
  const data = await handleResponse(res);
  return data.message || [];
}

export async function submitRouteExpense(expenseType: string, amount: number, notes?: string): Promise<string> {
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.finance.submit_route_expense', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    body: JSON.stringify({ expense_type: expenseType, amount, notes }),
  });
  const data = await handleResponse(res);
  return data.message;
}

export function downloadPdf(doctype: string, name: string) {
  const url = `/api/method/frappe.utils.print_format.download_pdf?doctype=${encodeURIComponent(doctype)}&name=${encodeURIComponent(name)}&format=Standard&no_letterhead=0`;
  window.open(url, '_blank');
}

// ─── Van Profile API ─────────────────────────────────────────────────────────

export async function listVanProfiles(): Promise<import('../types').VanProfile[]> {
  const res = await fetch('/api/method/van_sale.van_sale.van_profile.list_van_profiles', {
    method: 'GET',
    credentials: 'include',
    headers: defaultHeaders(),
  });
  const data = await handleResponse(res);
  return (data.message || []) as import('../types').VanProfile[];
}

export async function getVanProfileOptions(): Promise<import('../types').VanProfileOptions> {
  const res = await fetch('/api/method/van_sale.van_sale.van_profile.get_van_profile_options', {
    method: 'GET',
    credentials: 'include',
    headers: defaultHeaders(),
  });
  const data = await handleResponse(res);
  return data.message as import('../types').VanProfileOptions;
}

export async function saveVanProfile(payload: Partial<import('../types').VanProfile>): Promise<import('../types').VanProfile> {
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.van_profile.save_van_profile', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    body: JSON.stringify({ payload: JSON.stringify(payload) }),
  });
  const data = await handleResponse(res);
  return data.message as import('../types').VanProfile;
}

export async function deleteVanProfile(name: string): Promise<void> {
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.van_profile.delete_van_profile', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    body: JSON.stringify({ name }),
  });
  await handleResponse(res);
}

export async function assignDriverToProfile(driverUser: string, vanProfile: string): Promise<void> {
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.van_profile.assign_driver_to_profile', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    body: JSON.stringify({ driver_user: driverUser, van_profile: vanProfile }),
  });
  await handleResponse(res);
}
