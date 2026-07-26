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

const handleResponse = async (res: Response) => {
  if (!res.ok) {
    const text = await res.text();
    try {
      const data = JSON.parse(text);
      throw new Error(data._server_messages || data.message || res.statusText);
    } catch (_e) {
      const plain = text.replace(/<[^>]*>?/gm, '').trim();
      const snippet = plain ? plain.slice(0, 240) : res.statusText;
      throw new Error(snippet || res.statusText);
    }
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
const DEFAULT_ORDER_TYPE = 'Sales';
const buildPaymentSchedule = (amount: number, date: string) => [
  {
    doctype: 'Payment Schedule',
    parentfield: 'payment_schedule',
    parenttype: 'Sales Order',
    idx: 1,
    due_date: date,
    invoice_portion: 100,
    payment_amount: amount,
    base_payment_amount: amount,
    description: 'Full Payment',
  },
];

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
    fields: JSON.stringify(['name as item_code', 'item_name', 'description', 'stock_uom', 'image', 'item_group']),
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

  const priceList = (await getSellingPriceList()) || DEFAULT_SELLING_PRICE_LIST;
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

    if (customer) {
      await fetchPrices([
        ['Item Price', 'customer', '=', customer],
        ['Item Price', 'selling', '=', 1],
        ['Item Price', 'item_code', 'in', codes],
      ]);
    }

    await fetchPrices([
      ['Item Price', 'price_list', '=', priceList],
      ['Item Price', 'selling', '=', 1],
      ['Item Price', 'item_code', 'in', codes],
    ]);

    const missingCodes = codes.filter((c) => priceMap[c] === undefined);
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
}): Promise<SalesOrder> {
  const session = await getSession().catch(() => null);
  const driverConfig = session?.driver_config;

  // Prefer Van Profile / Driver Config values; fall back to global defaults.
  const [company, globalPriceList] = await Promise.all([getDefaultCompany(), getSellingPriceList()]);
  const priceList = driverConfig?.selling_price_list || globalPriceList;
  const taxesAndCharges = driverConfig?.taxes_and_charges || null;
  const profileCurrency = driverConfig?.currency || null;
  const currency = profileCurrency || await getCompanyCurrency(company);
  const today = new Date().toISOString().slice(0, 10);
  await refreshCsrfToken();
  const netTotal = payload.items.reduce((sum, i) => sum + i.qty * (i.rate ?? 0), 0);
  const grandTotal = netTotal;
  const paySchedule = buildPaymentSchedule(grandTotal, today);

  const res = await fetch('/api/method/frappe.client.insert', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    credentials: 'include',
    body: JSON.stringify({
      doc: {
        doctype: 'Sales Order',
        customer: payload.customer,
        transaction_date: today,
        delivery_date: today,
        ...(company ? { company } : {}),
        ...(priceList ? { selling_price_list: priceList } : {}),
        ...(currency ? { currency, price_list_currency: currency, company_currency: currency } : {}),
        ...(taxesAndCharges ? { taxes_and_charges: taxesAndCharges } : { taxes_and_charges: null, taxes: [] }),
        conversion_rate: 1,
        plc_conversion_rate: 1,
        order_type: DEFAULT_ORDER_TYPE,
        payment_terms_template: null,
        payment_schedule: paySchedule,
        net_total: netTotal,
        base_net_total: netTotal,
        total: netTotal,
        base_total: netTotal,
        total_net_weight: 0,
        grand_total: grandTotal,
        base_grand_total: grandTotal,
        items: payload.items.map((i, idx) => ({
          doctype: 'Sales Order Item',
          parenttype: 'Sales Order',
          parentfield: 'items',
          idx: idx + 1,
          item_code: i.item_code,
          item_name: i.item_name,
          qty: i.qty,
          rate: i.rate ?? 0,
          price_list_rate: i.price_list_rate ?? i.rate ?? 0,
          delivery_date: today,
          amount: i.amount ?? i.qty * (i.rate ?? 0),
          stock_uom: i.stock_uom,
        })),
      },
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

export async function updateSalesOrder(name: string, payload: { items: SalesOrderItem[]; customer: string }) {
  await refreshCsrfToken();
  const [existing, session] = await Promise.all([
    getSalesOrder(name).catch(() => null),
    getSession().catch(() => null),
  ]);
  const driverConfig = session?.driver_config;
  const taxesAndCharges = driverConfig?.taxes_and_charges || null;
  const currency = await getCompanyCurrency(existing?.company);
  const netTotal = payload.items.reduce((sum, i) => sum + i.qty * (i.rate ?? 0), 0);
  const grandTotal = netTotal;
  const paySchedule = buildPaymentSchedule(
    grandTotal,
    existing?.delivery_date || existing?.transaction_date || new Date().toISOString().slice(0, 10),
  );
  const res = await fetch(`/api/resource/Sales Order/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    credentials: 'include',
    body: JSON.stringify({
      selling_price_list: existing?.selling_price_list,
      company: existing?.company,
      naming_series: existing?.naming_series,
      order_type: existing?.order_type || DEFAULT_ORDER_TYPE,
      ...(currency ? { currency, price_list_currency: currency, company_currency: currency } : {}),
      conversion_rate: 1,
      plc_conversion_rate: 1,
      payment_terms_template: null,
      payment_schedule: paySchedule,
      ...(taxesAndCharges ? { taxes_and_charges: taxesAndCharges } : { taxes_and_charges: null, taxes: [] }),
      net_total: netTotal,
      base_net_total: netTotal,
      total: netTotal,
      base_total: netTotal,
      total_net_weight: 0,
      grand_total: grandTotal,
      base_grand_total: grandTotal,
      items: payload.items.map((i, idx) => ({
        doctype: 'Sales Order Item',
        parenttype: 'Sales Order',
        parentfield: 'items',
        idx: idx + 1,
        item_code: i.item_code,
        item_name: i.item_name,
        qty: i.qty,
        rate: i.rate ?? 0,
        price_list_rate: i.price_list_rate ?? i.rate ?? 0,
        delivery_date: i.delivery_date,
        stock_uom: i.stock_uom,
        amount: i.amount ?? i.qty * (i.rate ?? 0),
      })),
      customer: payload.customer,
      modified: existing?.modified,
    }),
  });
  const data = await handleResponse(res);
  return (data.data || data.message) as SalesOrder;
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

export async function createSalesInvoice(salesOrder: string): Promise<string> {
  await refreshCsrfToken();
  const res = await fetch('/api/method/van_sale.van_sale.sales.create_sales_invoice', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...defaultHeaders() },
    credentials: 'include',
    body: JSON.stringify({ sales_order: salesOrder }),
  });
  const data = await handleResponse(res);
  return (data.message || data.data) as string;
}

export async function recentOrders(owner: string): Promise<SalesOrder[]> {
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
    filters: JSON.stringify([
      ['Sales Order', 'owner', '=', owner],
      ['Sales Order', 'docstatus', '!=', 2],
    ]),
    order_by: 'creation desc',
    page_length: '20',
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

export async function createSalesReturn(customer: string, items: { item_code: string; qty: number }[]): Promise<string> {
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
