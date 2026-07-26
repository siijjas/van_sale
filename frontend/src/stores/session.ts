import { defineStore } from 'pinia';
import type { UserSession, Item, CartLine, Customer, SalesOrderItem } from '../types';
import * as api from '../api/frappe';

interface State {
  session: UserSession | null;
  cart: CartLine[];
  returnCart: CartLine[];
  loadingSession: boolean;
  customer: Customer | null;
  currentOrderName: string | null;
  currencyCode: string | null;
  currencySymbol: string | null;
}

export const useSessionStore = defineStore('session', {
  state: (): State => ({
    session: null,
    cart: [],
    returnCart: [],
    loadingSession: true,
    customer: null,
    currentOrderName: null,
    currencyCode: null,
    currencySymbol: null,
  }),
  getters: {
    cartCount: (state) => state.cart.reduce((sum, line) => sum + line.qty, 0),
    cartTotal: (state) =>
      state.cart.reduce(
        (sum, line) => sum + line.qty * (line.rate ?? line.item.price_list_rate ?? line.item.standard_rate ?? 0),
        0,
      ),
    returnCartCount: (state) => state.returnCart.reduce((sum, line) => sum + line.qty, 0),
    returnCartTotal: (state) =>
      state.returnCart.reduce(
        (sum, line) => sum + line.qty * (line.rate ?? line.item.price_list_rate ?? line.item.standard_rate ?? 0),
        0,
      ),
    currencyDisplay: (state) => state.currencySymbol || state.currencyCode || '₹',
    driverConfig: (state) => state.session?.driver_config || null,
    isManager: (state) => Boolean(state.session?.is_manager),
    isDriver: (state) => Boolean(state.session?.is_driver),
  },
  actions: {
    async bootstrap() {
      try {
        this.session = await api.getSession();
        await this.fetchCurrency();
      } catch (e) {
        this.session = null;
      } finally {
        this.loadingSession = false;
      }
    },
    async login(username: string, password: string) {
      this.session = await api.login(username, password);
      await this.fetchCurrency();
    },
    async logout() {
      try {
        await api.logout();
      } catch (e: any) {
        // show logout error but still clear state
        alert(e?.message || 'Logout failed on server, clearing local session.');
      } finally {
        this.session = null;
        this.cart = [];
        this.returnCart = [];
        this.customer = null;
        this.currentOrderName = null;
      }
    },
    setCustomer(customer: Customer | null) {
      this.customer = customer;
    },
    setCurrentOrder(name: string | null) {
      this.currentOrderName = name;
    },
    setCartFromOrder(items: SalesOrderItem[]) {
      this.cart = items.map((line) => ({
        item: {
          item_code: line.item_code,
          item_name: line.item_name,
          description: '',
          stock_uom: line.stock_uom || '',
          item_group: '',
          price_list_rate: line.rate,
          standard_rate: line.rate,
        },
        qty: line.qty,
        rate: line.rate
      }));
    },
    async fetchCurrency() {
      try {
        const info = await api.getCompanyCurrencyInfo();
        this.currencyCode = info.currency;
        this.currencySymbol = info.symbol;
      } catch (_e) {
        // keep defaults
      }
    },
    addToCart(item: Item) {
      const idx = this.cart.findIndex((line) => line.item.item_code === item.item_code);
      if (idx > -1) {
        this.cart[idx].qty += 1;
      } else {
        this.cart.push({
          item,
          qty: 1,
          rate: item.price_list_rate ?? item.standard_rate
        });
      }
    },
    setQty(item: Item, qty: number) {
      const idx = this.cart.findIndex((line) => line.item.item_code === item.item_code);
      if (qty <= 0) {
        if (idx > -1) this.cart.splice(idx, 1);
        return;
      }
      if (idx > -1) {
        this.cart[idx].qty = qty;
      } else {
        this.cart.push({ item, qty, rate: item.price_list_rate ?? item.standard_rate });
      }
    },
    updateQty(itemCode: string, delta: number) {
      const idx = this.cart.findIndex((line) => line.item.item_code === itemCode);
      if (idx === -1) return;
      const newQty = this.cart[idx].qty + delta;
      if (newQty <= 0) {
        this.cart.splice(idx, 1);
      } else {
        this.cart[idx].qty = newQty;
      }
    },
    updateRate(itemCode: string, newRate: number) {
      const idx = this.cart.findIndex((line) => line.item.item_code === itemCode);
      if (idx > -1) {
        this.cart[idx].rate = newRate;
      }
    },
    clearCart() {
      this.cart = [];
      this.currentOrderName = null;
    },
    addToReturnCart(item: Item) {
      const idx = this.returnCart.findIndex((line) => line.item.item_code === item.item_code);
      if (idx > -1) {
        this.returnCart[idx].qty += 1;
      } else {
        this.returnCart.push({
          item,
          qty: 1,
          rate: item.price_list_rate ?? item.standard_rate
        });
      }
    },
    updateReturnQty(itemCode: string, delta: number) {
      const idx = this.returnCart.findIndex((line) => line.item.item_code === itemCode);
      if (idx === -1) return;
      const newQty = this.returnCart[idx].qty + delta;
      if (newQty <= 0) {
        this.returnCart.splice(idx, 1);
      } else {
        this.returnCart[idx].qty = newQty;
      }
    },
    clearReturnCart() {
      this.returnCart = [];
    },
  },
});
