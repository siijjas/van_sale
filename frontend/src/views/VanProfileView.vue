<template>
  <WorkspacePage eyebrow="Manager · fleet" title="Van profiles" description="Reusable configuration templates for your fleet." width="wide">
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
            <p class="mt-1 text-xs text-subtle">{{ p.assigned_drivers?.length || 0 }} driver(s)</p>
          </AppCard>
          <AppButton variant="secondary" block icon="plus" @click="startNew">Create profile</AppButton>
          <EmptyState v-if="!filteredProfiles.length" icon="user" title="No profiles" description="Create your first van profile." />
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
          <div class="grid gap-4 md:grid-cols-2">
            <FormField label="Profile name" required>
              <BaseInput v-model="form.profile_name" placeholder="e.g. Riyadh Van Fleet" />
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
        <FormSection title="Warehouses & routing" icon="boxes">
          <div class="grid gap-4 md:grid-cols-2">
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
            <FormField label="Delivery route (territory)">
              <BaseSelect v-model="form.delivery_route" placeholder="Optional route restriction">
                <option v-for="r in options.routes" :key="r.name" :value="r.name">{{ r.name }}</option>
              </BaseSelect>
            </FormField>
          </div>
        </FormSection>

        <!-- Drivers -->
        <FormSection title="Assigned drivers" icon="users" :badge="`${form.assigned_drivers?.length || 0}`">
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
            <FormField label="Low stock threshold" hint="Alert when van stock drops below this.">
              <BaseInput v-model="form.low_stock_threshold" type="number" inputmode="numeric" />
            </FormField>
          </div>
          <div class="grid gap-2 md:grid-cols-2">
            <ToggleRow v-model="form.allow_rate_change" label="Allow modifying item rates" />
            <ToggleRow v-model="form.allow_discount_change" label="Allow modifying discounts" />
            <ToggleRow v-model="form.validate_stock_on_save" label="Strictly validate stock on save" />
            <ToggleRow v-model="form.allow_offline_stock_dashboard" label="Enable offline stock dashboard" />
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
          </div>
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
import { AppCard, AppButton, AppAlert, AppIcon, FormField, BaseInput, BaseSelect, SearchBar, StatusBadge, SkeletonList, EmptyState, StickyBar } from '../components/ui';

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
  companies: [],
  price_lists: [],
  tax_templates: [],
  currencies: [],
  print_formats: [],
  users: [],
});

const defaultForm = (): Partial<VanProfile> => ({
  profile_name: '',
  company: '',
  is_active: true,
  source_warehouse: '',
  van_warehouse: '',
  delivery_route: '',
  selling_price_list: '',
  currency: '',
  taxes_and_charges: '',
  apply_discount_on: 'Grand Total',
  daily_credit_limit: 0,
  low_stock_threshold: 5,
  allow_rate_change: false,
  allow_discount_change: false,
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
  allowed_payment_modes: [],
  assigned_drivers: [],
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

const isValid = computed(
  () =>
    !!form.value.profile_name &&
    !!form.value.company &&
    !!form.value.source_warehouse &&
    !!form.value.van_warehouse &&
    form.value.source_warehouse !== form.value.van_warehouse,
);

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
