import { createRouter, createWebHashHistory } from 'vue-router';
import { useSessionStore } from '../stores/session';
import DashboardView from '../views/DashboardView.vue';
import LoginView from '../views/LoginView.vue';
import CustomerSelectView from '../views/CustomerSelectView.vue';
import ItemCatalogView from '../views/ItemCatalogView.vue';
import CartView from '../views/CartView.vue';
import HistoryView from '../views/HistoryView.vue';
import OrderDetailView from '../views/OrderDetailView.vue';

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/', name: 'dashboard', component: DashboardView },
    { path: '/customers', name: 'customers', component: CustomerSelectView },
    { path: '/items', name: 'items', component: ItemCatalogView },
    { path: '/cart', name: 'cart', component: CartView },
    { path: '/history', name: 'history', component: HistoryView },
    { path: '/orders/:name', name: 'order-detail', component: OrderDetailView },
    { path: '/payment', name: 'payment', component: () => import('../views/PaymentEntryView.vue') },
    { path: '/ledger', name: 'ledger', component: () => import('../views/CustomerLedgerView.vue') },
    { path: '/stock', name: 'stock-dashboard', component: () => import('../views/DriverStockView.vue'), meta: { requiresDriverConfig: true } },
    { path: '/transfer', name: 'stock-transfer', component: () => import('../views/StockTransferView.vue'), meta: { requiresDriverConfig: true } },
    { path: '/driver-setup', name: 'driver-setup', redirect: { name: 'settings' } },
    { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue'), meta: { requiresManager: true } },
    { path: '/daily-log/:type', name: 'daily-log', component: () => import('../views/DailyLogView.vue') },
    { path: '/payment-detail/:name', name: 'payment-detail', component: () => import('../views/PaymentDetailView.vue') },
    { path: '/expenses', name: 'expenses', component: () => import('../views/ExpenseLogView.vue') },
    { path: '/return-items', name: 'return-items', component: () => import('../views/ReturnCatalogView.vue') },
    { path: '/return-cart', name: 'return-cart', component: () => import('../views/ReturnCartView.vue') },
    { path: '/shift/open', name: 'shift-open', component: () => import('../views/ShiftOpenView.vue') },
    { path: '/shift/close', name: 'shift-close', component: () => import('../views/ShiftCloseView.vue') },
    { path: '/eod', redirect: { name: 'shift-close' } },
    { path: '/van-profiles', name: 'van-profiles', component: () => import('../views/VanProfileView.vue'), meta: { requiresManager: true } },
  ],
});

router.beforeEach(async (to, _from, next) => {
  const store = useSessionStore();
  if (store.loadingSession) {
    await store.bootstrap();
  }
  if (to.name !== 'login' && !store.session) {
    return next({ name: 'login' });
  }
  if (to.name === 'login' && store.session) {
    return next({ name: 'dashboard' });
  }
  if (to.meta.requiresDriverConfig && !store.driverConfig && !store.isManager) {
    return next({ name: 'dashboard', query: { setup: 'driver-profile' } });
  }
  if (to.meta.requiresManager && !store.session?.is_manager) {
    return next({ name: 'dashboard' });
  }
  if (to.name === 'driver-setup' && !store.session?.is_manager) {
    return next({ name: 'dashboard' });
  }
  return next();
});

export default router;
