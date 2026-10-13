<template>
  <WorkspacePage eyebrow="Manager · sales staff" title="Sales profiles" description="Reusable configuration for van drivers and field sales staff." width="wide">
    <template #actions>
      <AppButton v-if="selectedProfile" variant="secondary" size="sm" icon="plus" @click="startNew">New</AppButton>
    </template>

    <div class="grid gap-5 lg:grid-cols-[320px,1fr]">
      <!-- List -->
      <aside class="space-y-3" :class="selectedProfile ? 'hidden lg:block' : ''">
        <SearchBar v-model="searchQuery" placeholder="Search profiles…" />
        <SkeletonList v-if="loading" :rows="4" height="4.5rem" />
        <div v-else class="space-y-2">
          <AppCard
            v-for="p in filteredProfiles"
            :key="p.name"
            padding="sm"
            interactive
            :class="selectedProfile?.name === p.name ? 'ring-2 ring-primary' : ''"
            @click="selectProfile(p)"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="truncate font-bold text-foreground">{{ p.profile_name }}</span>
              <StatusBadge :tone="p.is_active ? 'success' : 'neutral'" :dot="false">{{ p.is_active ? 'Active' : 'Draft' }}</StatusBadge>
            </div>
            <p class="mt-1 truncate text-sm text-muted">{{ p.company }}</p>
            <p class="mt-1 text-xs text-subtle">
              <span class="font-semibold" :class="p.profile_type === 'Field Sales' ? 'text-info' : 'text-primary'">{{ p.profile_type || 'Van Sales' }}</span>
              · {{ p.assigned_drivers?.length || 0 }} staff
            </p>
          </AppCard>
          <AppButton variant="secondary" block icon="plus" @click="startNew">Create profile</AppButton>
          <EmptyState v-if="!filteredProfiles.length" icon="user" title="No profiles" description="Create your first sales profile." />
        </div>
      </aside>

      <!-- Editor -->
      <div v-if="!selectedProfile" class="hidden lg:flex">
        <EmptyState class="w-full" icon="sliders" title="Nothing selected" description="Pick a profile or create a new one." />
      </div>

      <div v-else class="space-y-4 pb-28">
        <button class="flex items-center gap-1 text-sm font-semibold text-primary lg:hidden" @click="selectedProfile = null">
          <AppIcon name="chevron-left" :size="16" /> Profiles
        </button>

        <AppAlert v-if="errorMsg" tone="danger" title="Couldn't save profile" :message="errorMsg" />

        <!-- Identity -->
        <FormSection title="Identity & core" icon="user">
          <FormField label="Profile type" required :hint="isFieldSales ? 'Staff take orders and collect payments. Invoicing, delivery and returns stay in the back office.' : 'Staff load a van, sell and deliver from it, take returns and reconcile cash at shift close.'">
            <SegmentedControl
              :model-value="form.profile_type || 'Van Sales'"
              :options="[{ value: 'Van Sales', label: 'Van Sales' }, { value: 'Field Sales', label: 'Field Sales' }]"
              @update:modelValue="setProfileType"
            />
          </FormField>
          <div class="grid gap-4 md:grid-cols-2">
            <FormField label="Profile name" required>
              <BaseInput v-model="form.profile_name" :placeholder="isFieldSales ? 'e.g. North Region Field Team' : 'e.g. Riyadh Van Fleet'" />
            </FormField>
            <FormField label="Company" required>
              <BaseSelect v-model="form.company" placeholder="Select company">
                <option v-for="c in options.companies" :key="c.name" :value="c.name">{{ c.name }}</option>
              </BaseSelect>
            </FormField>
          </div>
          <ToggleRow v-model="form.is_active" label="Profile is active" />
        </FormSection>

        <!-- Warehouses -->
        <FormSection :title="isFieldSales ? 'Stock display & routing' : 'Warehouses & routing'" icon="boxes">
          <div class="grid gap-4 md:grid-cols-2">
            <template v-if="!isFieldSales">
              <FormField label="Main warehouse" required>
                <BaseSelect v-model="form.source_warehouse" placeholder="Select source warehouse">
                  <option v-for="w in filteredWarehouses" :key="w.name" :value="w.name">{{ w.name }}</option>
                </BaseSelect>
              </FormField>
              <FormField label="Van warehouse" required>
                <BaseSelect v-model="form.van_warehouse" placeholder="Select van warehouse">
                  <option v-for="w in filteredWarehouses" :key="w.name" :value="w.name">{{ w.name }}</option>
                </BaseSelect>
              </FormField>
            </template>
            <FormField v-else label="Stock warehouse (display only)" hint="Catalog shows available qty from here for information. It never blocks an order.">
              <BaseSelect v-model="form.stock_warehouse" placeholder="Company default warehouse">
                <option v-for="w in filteredWarehouses" :key="w.name" :value="w.name">{{ w.name }}</option>
              </BaseSelect>
            </FormField>
            <FormField label="Delivery route (territory)">
              <BaseSelect v-model="form.delivery_route" placeholder="Optional route restriction">
                <option v-for="r in options.routes" :key="r.name" :value="r.name">{{ r.name }}</option>
              </BaseSelect>
            </FormField>
          </div>
        </FormSection>

        <!-- Customer access -->
        <FormSection title="Customer access" icon="users" :badge="`${form.allowed_customer_groups?.length || 0}`">
          <p class="text-xs text-muted">Restrict staff on this profile to customers in these groups. Leave empty to allow all groups (still subject to the delivery route above, if set).</p>
          <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <label
              v-for="group in options.customer_groups"
              :key="group.name"
              class="flex cursor-pointer items-center gap-3 rounded-2xl border p-3 transition"
              :class="(form.allowed_customer_groups || []).includes(group.name) ? 'border-success/40 bg-success/[0.06]' : 'border-line hover:bg-card-muted'"
            >
              <input type="checkbox" :value="group.name" v-model="form.allowed_customer_groups" class="h-4 w-4 accent-primary" />
              <span class="text-sm font-semibold text-foreground">{{ group.name }}</span>
            </label>
          </div>
        </FormSection>

        <!-- Drivers -->
        <FormSection :title="isFieldSales ? 'Assigned sales staff' : 'Assigned drivers'" icon="users" :badge="`${form.assigned_drivers?.length || 0}`">
          <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <label
              v-for="user in options.users"
              :key="user.name"
              class="flex cursor-pointer items-start gap-3 rounded-2xl border p-3 transition"
              :class="isDriverAssigned(user.name) ? 'border-primary/40 bg-primary/[0.06]' : 'border-line hover:bg-card-muted'"
            >
              <input type="checkbox" class="mt-0.5 h-4 w-4 accent-primary" :checked="isDriverAssigned(user.name)" @change="toggleDriver(user.name)" />
              <div class="min-w-0">
                <p class="truncate text-sm font-semibold text-foreground">{{ user.full_name }}</p>
                <p class="truncate text-xs text-muted">{{ user.name }}</p>
              </div>
            </label>
          </div>
        </FormSection>

        <!-- Controls -->
        <FormSection title="Operational controls" icon="sliders">
          <div class="grid gap-4 md:grid-cols-2">
            <FormField label="Daily credit limit" hint="Max credit sales per day.">
              <BaseInput v-model="form.daily_credit_limit" type="number" inputmode="decimal" prefix="$" placeholder="0.00" />
            </FormField>
            <FormField v-if="!isFieldSales" label="Low stock threshold" hint="Alert when van stock drops below this.">
              <BaseInput v-model="form.low_stock_threshold" type="number" inputmode="numeric" />
            </FormField>
          </div>
          <div class="grid gap-2 md:grid-cols-2">
            <ToggleRow v-model="form.allow_rate_change" label="Allow modifying item rates" />
            <ToggleRow v-model="form.allow_discount_change" label="Allow modifying discounts" />
            <ToggleRow v-if="!isFieldSales" v-model="form.allow_sale_without_stock" label="Allow selling items not in van stock" />
            <ToggleRow v-if="!isFieldSales" v-model="form.hide_unavailable_items" label="Hide items not in van stock from the catalog" />
            <ToggleRow v-if="!isFieldSales" v-model="form.allow_credit_sale" label="Allow credit sales (invoice now, collect later)" />
            <ToggleRow v-if="!isFieldSales" v-model="form.allow_return" label="Allow returns" />
            <ToggleRow v-model="form.show_customer_balance" label="Show customer balance and ledger" />
            <ToggleRow v-model="form.allow_create_customer" label="Allow creating new customers" />
            <ToggleRow v-if="form.allow_create_customer" v-model="form.allow_duplicate_customer_names" label="Allow duplicate customer names" />
            <ToggleRow v-model="form.use_shifts" label="Use shifts (opening float, cash reconciliation at close)" />
            <ToggleRow v-if="form.use_shifts" v-model="form.require_open_shift" label="Require an open shift to sell, collect or log expenses" />
            <ToggleRow v-if="form.use_shifts" v-model="form.allow_driver_close_shift" label="Staff can close their own shift (off: managers only)" />
            <ToggleRow v-if="form.use_shifts" v-model="form.hide_expected_amount" label="Blind cash count (hide expected amounts at close)" />
          </div>
          <div v-if="!isFieldSales && form.allow_return" class="grid gap-4 md:grid-cols-2">
            <FormField label="Return validity (days)" hint="Items can only be returned if the customer bought them within this many days. 0 = no limit.">
              <BaseInput v-model="form.return_validity_days" type="number" inputmode="numeric" placeholder="0" />
            </FormField>
          </div>
          <div v-if="form.use_shifts" class="grid gap-4 md:grid-cols-2">
            <FormField label="Variance tolerance" hint="A closing whose counted cash is off by more than this is flagged for you. 0 flags any difference. Never blocks closing.">
              <BaseInput v-model="form.variance_tolerance" type="number" inputmode="decimal" prefix="$" placeholder="0.00" />
            </FormField>
          </div>
          <div class="grid gap-2 md:grid-cols-2">
            <ToggleRow v-if="!isFieldSales" v-model="form.validate_stock_on_save" label="Strictly validate stock on save" />
            <ToggleRow v-if="!isFieldSales" v-model="form.allow_offline_stock_dashboard" label="Enable offline stock dashboard" />
            <ToggleRow v-model="form.ignore_pricing_rule" label="Ignore active pricing rules" />
          </div>
        </FormSection>

        <!-- Pricing & tax -->
        <FormSection title="Pricing & tax" icon="receipt">
          <div class="grid gap-4 md:grid-cols-2">
            <FormField label="Selling price list">
              <BaseSelect v-model="form.selling_price_list" placeholder="Default from selling settings">
                <option v-for="p in options.price_lists" :key="p.name" :value="p.name">{{ p.name }}</option>
              </BaseSelect>
            </FormField>
            <FormField label="Currency">
              <BaseSelect v-model="form.currency" placeholder="Company default">
                <option v-for="c in options.currencies" :key="c.name" :value="c.name">{{ c.name }}</option>
              </BaseSelect>
            </FormField>
            <FormField label="Taxes & charges template">
              <BaseSelect v-model="form.taxes_and_charges" placeholder="None (calculate dynamically)">
                <option v-for="t in filteredTaxTemplates" :key="t.name" :value="t.name">{{ t.name }}</option>
              </BaseSelect>
            </FormField>
            <FormField label="Apply discount on">
              <BaseSelect v-model="form.apply_discount_on">
                <option value="Grand Total">Grand Total</option>
                <option value="Net Total">Net Total</option>
              </BaseSelect>
            </FormField>
            <FormField v-if="form.allow_discount_change" label="Max discount %" hint="Largest order discount staff may give. 0 = no cap.">
              <BaseInput v-model="form.max_discount_percent" type="number" inputmode="decimal" min="0" max="100" placeholder="0" />
            </FormField>
          </div>
          <div class="grid gap-2 md:grid-cols-2">
            <ToggleRow v-model="form.use_customer_price_list" label="Use the customer's own price list when they have one" />
            <ToggleRow v-model="form.allow_zero_rated_items" label="Allow zero rated items (lines priced at 0)" />
          </div>
        </FormSection>

        <!-- Cash movements -->
        <FormSection v-if="form.use_shifts" title="Cash movements (expenses & deposits)" icon="banknote">
          <p class="text-xs text-muted">Cash leaving the drawer mid-shift. Each entry posts a Journal Entry that credits the drawer account and debits the expense or back-office account, and the shift closing deducts it from expected cash.</p>
          <div class="grid gap-2 md:grid-cols-3">
            <ToggleRow v-model="form.allow_expense" label="Allow expenses" />
            <ToggleRow v-model="form.allow_cash_deposit" label="Allow deposits to office" />
            <ToggleRow v-model="form.require_cash_movement_remarks" label="Require remarks" />
            <ToggleRow v-model="form.allow_cancel_cash_movement" label="Staff can cancel their own (while the shift is open)" />
          </div>
          <div class="grid gap-4 md:grid-cols-2">
            <FormField label="Cash drawer account" hint="Blank: the Default Cash Mode's account for this company.">
              <BaseSelect v-model="form.cash_account" placeholder="From default cash mode">
                <option v-for="a in filteredCashAccounts" :key="a.name" :value="a.name">{{ a.name }}</option>
              </BaseSelect>
            </FormField>
            <FormField v-if="form.allow_cash_deposit" label="Back office cash account" hint="Where deposits land. Blank: company default cash account.">
              <BaseSelect v-model="form.back_office_cash_account" placeholder="Company default cash account">
                <option v-for="a in filteredCashAccounts" :key="a.name" :value="a.name">{{ a.name }}</option>
              </BaseSelect>
            </FormField>
            <FormField v-if="form.allow_expense" label="Default expense account" hint="Pre-selected on a new expense.">
              <BaseSelect v-model="form.expense_account" placeholder="None">
                <option v-for="a in selectableExpenseAccounts" :key="a.name" :value="a.name">{{ a.account_name }}</option>
              </BaseSelect>
            </FormField>
            <FormField label="Cost center" hint="For the Journal Entries. Blank: company default.">
              <BaseSelect v-model="form.cost_center" placeholder="Company default">
                <option v-for="c in filteredCostCenters" :key="c.name" :value="c.name">{{ c.name }}</option>
              </BaseSelect>
            </FormField>
            <FormField label="Max amount per movement" hint="0 = no limit.">
              <BaseInput v-model="form.cash_movement_max_amount" type="number" inputmode="decimal" placeholder="0.00" />
            </FormField>
          </div>
          <template v-if="form.allow_expense">
            <div class="flex items-center justify-between gap-3">
              <p class="text-xs font-bold uppercase tracking-wider text-muted">Allowed expense accounts <span class="font-medium normal-case tracking-normal">· empty = all</span></p>
              <span class="rounded-full bg-card-muted px-2.5 py-1 text-xs font-bold text-muted">{{ form.allowed_expense_accounts?.length || 0 }}</span>
            </div>
            <SearchBar v-model="expenseAccountSearch" placeholder="Filter accounts…" />
            <div class="grid max-h-72 gap-2 overflow-y-auto sm:grid-cols-2 lg:grid-cols-3">
              <label
                v-for="a in filteredExpenseAccounts"
                :key="a.name"
                class="flex cursor-pointer items-center gap-3 rounded-2xl border p-3 transition"
                :class="(form.allowed_expense_accounts || []).includes(a.name) ? 'border-success/40 bg-success/[0.06]' : 'border-line hover:bg-card-muted'"
              >
                <input type="checkbox" :value="a.name" v-model="form.allowed_expense_accounts" class="h-4 w-4 accent-primary" />
                <span class="truncate text-sm font-semibold text-foreground">{{ a.account_name }}</span>
              </label>
            </div>
          </template>
        </FormSection>

        <!-- Payment modes -->
        <FormSection title="Allowed payment modes" icon="wallet">
          <div class="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <label
              v-for="mode in options.payment_modes"
              :key="mode.name"
              class="flex cursor-pointer items-center gap-3 rounded-2xl border p-3 transition"
              :class="(form.allowed_payment_modes || []).includes(mode.name) ? 'border-success/40 bg-success/[0.06]' : 'border-line hover:bg-card-muted'"
            >
              <input type="checkbox" :value="mode.name" v-model="form.allowed_payment_modes" class="h-4 w-4 accent-primary" />
              <span class="text-sm font-semibold text-foreground">{{ mode.name }}</span>
            </label>
          </div>
          <FormField v-if="form.use_shifts" label="Default cash mode" hint="Which mode counts as the cash drawer for shift reconciliation. Falls back to a cash-type mode above, then the generic &quot;Cash&quot; record, if left blank.">
            <BaseSelect v-model="form.default_cash_mode" placeholder="Auto-detect">
              <option v-for="mode in allowedCashModes" :key="mode.name" :value="mode.name">{{ mode.name }}</option>
            </BaseSelect>
          </FormField>
        </FormSection>
      </div>
    </div>

    <StickyBar v-if="selectedProfile">
      <AppButton size="lg" block icon="save" :disabled="!isValid" :loading="isSaving" @click="saveProfile">
        {{ isSaving ? 'Saving…' : selectedProfile.name ? 'Update profile' : 'Save profile' }}
      </AppButton>
    </StickyBar>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, defineComponent, h } from 'vue';
import { listVanProfiles, getVanProfileOptions, saveVanProfile } from '../api/frappe';
import type { VanProfile, VanProfileOptions } from '../types';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppAlert, AppIcon, FormField, BaseInput, BaseSelect, SearchBar, StatusBadge, SkeletonList, EmptyState, StickyBar, SegmentedControl } from '../components/ui';

// Collapsible-free section wrapper used throughout the editor.
const FormSection = defineComponent({
  props: { title: { type: String, required: true }, icon: { type: String, required: true }, badge: { type: String, default: '' } },
  setup(props, { slots }) {
    return () =>
      h(AppCard, { padding: 'none' }, () => [
        h('div', { class: 'flex items-center justify-between border-b border-line px-4 py-3 md:px-5' }, [
          h('div', { class: 'flex items-center gap-2.5' }, [
            h('span', { class: 'flex h-8 w-8 items-center justify-center rounded-xl bg-primary/12 text-primary' }, [h(AppIcon, { name: props.icon, size: 16 })]),
            h('h3', { class: 'text-sm font-bold text-foreground' }, props.title),
          ]),
          props.badge ? h('span', { class: 'rounded-full bg-card-muted px-2.5 py-1 text-xs font-bold text-muted' }, props.badge) : null,
        ]),
        h('div', { class: 'space-y-4 p-4 md:p-5' }, slots.default?.()),
      ]);
  },
});

// Theme-aware checkbox row used for boolean settings.
const ToggleRow = defineComponent({
  props: { modelValue: { type: Boolean, default: false }, label: { type: String, required: true } },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () =>
      h('label', { class: 'flex cursor-pointer items-center gap-3 rounded-2xl border border-line bg-card-muted px-3.5 py-3' }, [
        h('input', {
          type: 'checkbox',
          checked: props.modelValue,
          class: 'h-4 w-4 accent-primary',
          onChange: (e: Event) => emit('update:modelValue', (e.target as HTMLInputElement).checked),
        }),
        h('span', { class: 'text-sm font-medium text-foreground' }, props.label),
      ]);
  },
});

const loading = ref(true);
const isSaving = ref(false);
const errorMsg = ref('');
const profiles = ref<VanProfile[]>([]);
const searchQuery = ref('');
const selectedProfile = ref<VanProfile | Partial<VanProfile> | null>(null);

const options = ref<VanProfileOptions>({
  warehouses: [],
  payment_modes: [],
  routes: [],
  customer_groups: [],
  companies: [],
  price_lists: [],
  tax_templates: [],
  currencies: [],
  print_formats: [],
  users: [],
  cash_accounts: [],
  expense_accounts: [],
  cost_centers: [],
});

const defaultForm = (): Partial<VanProfile> => ({
  profile_name: '',
  profile_type: 'Van Sales',
  company: '',
  is_active: true,
  source_warehouse: '',
  van_warehouse: '',
  stock_warehouse: '',
  delivery_route: '',
  default_cash_mode: '',
  selling_price_list: '',
  currency: '',
  taxes_and_charges: '',
  apply_discount_on: 'Grand Total',
  daily_credit_limit: 0,
  low_stock_threshold: 5,
  allow_rate_change: false,
  allow_discount_change: false,
  allow_sale_without_stock: false,
  use_shifts: true,
  require_open_shift: false,
  variance_tolerance: 0,
  validate_stock_on_save: false,
  allow_offline_stock_dashboard: true,
  ignore_pricing_rule: false,
  disable_rounded_total: false,
  print_format: '',
  letter_head: '',
  income_account: '',
  expense_account: '',
  cost_center: '',
  write_off_account: '',
  allow_expense: true,
  allow_cash_deposit: true,
  cash_account: '',
  back_office_cash_account: '',
  cash_movement_max_amount: 0,
  require_cash_movement_remarks: false,
  allowed_expense_accounts: [],
  allowed_payment_modes: [],
  allowed_customer_groups: [],
  assigned_drivers: [],
  // POS-profile style controls
  max_discount_percent: 0,
  use_customer_price_list: false,
  allow_zero_rated_items: false,
  allow_credit_sale: true,
  allow_return: true,
  return_validity_days: 0,
  hide_unavailable_items: false,
  show_customer_balance: true,
  allow_create_customer: true,
  allow_duplicate_customer_names: false,
  hide_expected_amount: false,
  allow_driver_close_shift: true,
  allow_cancel_cash_movement: false,
});

const form = ref<Partial<VanProfile>>(defaultForm());

const filteredProfiles = computed(() => {
  const q = searchQuery.value.toLowerCase();
  return profiles.value.filter((p) => p.profile_name.toLowerCase().includes(q) || p.company.toLowerCase().includes(q));
});
const filteredWarehouses = computed(() =>
  form.value.company ? options.value.warehouses.filter((w) => w.company === form.value.company) : options.value.warehouses,
);
const filteredTaxTemplates = computed(() =>
  form.value.company ? options.value.tax_templates.filter((t) => t.company === form.value.company) : options.value.tax_templates,
);
const expenseAccountSearch = ref('');
const byCompany = <T extends { company: string }>(rows: T[]) =>
  form.value.company ? rows.filter((r) => r.company === form.value.company) : rows;
const filteredCashAccounts = computed(() => byCompany(options.value.cash_accounts || []));
const filteredCostCenters = computed(() => byCompany(options.value.cost_centers || []));
const companyExpenseAccounts = computed(() => byCompany(options.value.expense_accounts || []));
const filteredExpenseAccounts = computed(() => {
  const q = expenseAccountSearch.value.toLowerCase();
  return q ? companyExpenseAccounts.value.filter((a) => a.account_name.toLowerCase().includes(q) || a.name.toLowerCase().includes(q)) : companyExpenseAccounts.value;
});
// The default must be one of the allowed accounts once any are chosen.
const selectableExpenseAccounts = computed(() => {
  const allowed = new Set(form.value.allowed_expense_accounts || []);
  return allowed.size ? companyExpenseAccounts.value.filter((a) => allowed.has(a.name)) : companyExpenseAccounts.value;
});
const allowedCashModes = computed(() => {
  const allowed = new Set(form.value.allowed_payment_modes || []);
  return options.value.payment_modes.filter((m) => m.type === 'Cash' && (allowed.size === 0 || allowed.has(m.name)));
});

const isFieldSales = computed(() => form.value.profile_type === 'Field Sales');

// Switching type resets what the other type can't use, mirroring the server-side
// VanProfile._validate_profile_type() so the form never shows stale values.
function setProfileType(type: string) {
  form.value.profile_type = type as VanProfile['profile_type'];
  if (type === 'Field Sales') {
    form.value.source_warehouse = '';
    form.value.van_warehouse = '';
    form.value.allow_sale_without_stock = false;
    form.value.validate_stock_on_save = false;
    form.value.allow_offline_stock_dashboard = false;
    // Field staff default to no shifts; a manager can switch them back on.
    if (!selectedProfile.value?.name) form.value.use_shifts = false;
  } else {
    form.value.stock_warehouse = '';
    if (!selectedProfile.value?.name) form.value.use_shifts = true;
  }
  if (!form.value.use_shifts) form.value.require_open_shift = false;
}

const isValid = computed(() => {
  if (!form.value.profile_name || !form.value.company) return false;
  if (isFieldSales.value) return true;
  return (
    !!form.value.source_warehouse &&
    !!form.value.van_warehouse &&
    form.value.source_warehouse !== form.value.van_warehouse
  );
});

function isDriverAssigned(username: string): boolean {
  return form.value.assigned_drivers?.some((d) => d.driver_user === username) || false;
}
function toggleDriver(username: string) {
  if (!form.value.assigned_drivers) form.value.assigned_drivers = [];
  const idx = form.value.assigned_drivers.findIndex((d) => d.driver_user === username);
  if (idx >= 0) form.value.assigned_drivers.splice(idx, 1);
  else form.value.assigned_drivers.push({ driver_user: username });
}

async function loadData() {
  loading.value = true;
  try {
    const [optsRes, profilesRes] = await Promise.all([getVanProfileOptions(), listVanProfiles()]);
    options.value = optsRes;
    profiles.value = profilesRes;
    if (profiles.value.length > 0 && !selectedProfile.value) selectProfile(profiles.value[0]);
  } catch (err: any) {
    errorMsg.value = err.message || 'Failed to load profiles';
  } finally {
    loading.value = false;
  }
}

function startNew() {
  selectedProfile.value = { ...defaultForm() };
  if (options.value.companies.length === 1) selectedProfile.value.company = options.value.companies[0].name;
  form.value = JSON.parse(JSON.stringify(selectedProfile.value));
  errorMsg.value = '';
}
function selectProfile(p: VanProfile) {
  selectedProfile.value = p;
  form.value = JSON.parse(JSON.stringify(p));
  errorMsg.value = '';
}

async function saveProfile() {
  if (!isValid.value) return;
  isSaving.value = true;
  errorMsg.value = '';
  try {
    const payload = { ...form.value, assigned_drivers: form.value.assigned_drivers?.map((d) => d.driver_user) || [] };
    const saved = await saveVanProfile(payload as any);
    const idx = profiles.value.findIndex((p) => p.name === saved.name);
    if (idx >= 0) profiles.value[idx] = saved;
    else profiles.value.push(saved);
    selectProfile(saved);
  } catch (err: any) {
    errorMsg.value = err.message || 'Failed to save profile';
  } finally {
    isSaving.value = false;
  }
}

onMounted(loadData);
</script>
