<template>
  <WorkspacePage back eyebrow="Route finances" title="Expenses" description="Log out-of-pocket and van maintenance spending." width="default">
    <div class="grid gap-5 md:grid-cols-2">
      <!-- Form -->
      <AppCard padding="lg" class="h-fit">
        <h3 class="text-base font-bold text-foreground">Log new expense</h3>
        <p class="mt-0.5 text-sm text-muted">Record costs incurred on today's route.</p>

        <div class="mt-5 space-y-4">
          <AppAlert v-if="error" tone="danger" :message="error" />
          <FormField label="Expense type" required>
            <BaseSelect v-model="expenseForm.type" placeholder="Select a category">
              <option v-for="t in expenseTypes" :key="t" :value="t">{{ t }}</option>
            </BaseSelect>
          </FormField>
          <FormField label="Amount" required>
            <BaseInput v-model="expenseForm.amount" type="number" inputmode="decimal" :prefix="currency" placeholder="0.00" />
          </FormField>
          <FormField label="Notes" hint="Optional — e.g. Shell Station 42">
            <BaseTextarea v-model="expenseForm.notes" :rows="2" placeholder="Add a note…" />
          </FormField>
          <AppButton size="lg" block icon="plus" :disabled="!isValid" :loading="submitting" @click="submit">
            {{ submitting ? 'Logging…' : 'Submit expense' }}
          </AppButton>
        </div>
      </AppCard>

      <!-- Today's log -->
      <div class="space-y-3">
        <p class="text-xs font-bold uppercase tracking-wider text-muted">Today's log</p>
        <SkeletonList v-if="loading" :rows="3" height="5rem" />
        <EmptyState v-else-if="!expenses.length" icon="file-text" title="No expenses today" description="Logged expenses will appear here." />
        <div v-else class="space-y-2.5">
          <AppCard v-for="exp in expenses" :key="exp.name" padding="sm">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="font-semibold text-foreground">{{ exp.expense_type }}</p>
                <p class="mt-0.5 text-xs text-muted">{{ exp.name }}</p>
              </div>
              <p class="tnum font-bold text-foreground">{{ currency }} {{ exp.amount.toFixed(2) }}</p>
            </div>
            <p v-if="exp.notes" class="mt-3 rounded-xl border border-line bg-card-muted p-2.5 text-sm text-muted">{{ exp.notes }}</p>
          </AppCard>
        </div>
      </div>
    </div>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import * as api from '../api/frappe';
import { useSessionStore } from '../stores/session';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, AppAlert, FormField, BaseInput, BaseSelect, BaseTextarea, SkeletonList, EmptyState } from '../components/ui';

const store = useSessionStore();
const currency = computed(() => store.currencyDisplay);

const expenseTypes = ['Fuel', 'Tolls', 'Meals', 'Vehicle Maintenance', 'Miscellaneous'];
const expenses = ref<any[]>([]);
const loading = ref(true);
const submitting = ref(false);
const error = ref('');

const expenseForm = ref({ type: '', amount: null as number | null, notes: '' });
const isValid = computed(() => !!expenseForm.value.type && !!expenseForm.value.amount && expenseForm.value.amount > 0);

const loadExpenses = async () => {
  loading.value = true;
  try {
    expenses.value = await api.getRouteExpenses();
  } finally {
    loading.value = false;
  }
};

const submit = async () => {
  if (!isValid.value) return;
  submitting.value = true;
  error.value = '';
  try {
    await api.submitRouteExpense(expenseForm.value.type, expenseForm.value.amount!, expenseForm.value.notes);
    expenseForm.value = { type: '', amount: null, notes: '' };
    await loadExpenses();
  } catch (e: any) {
    error.value = e?.message || 'Failed to submit expense log.';
  } finally {
    submitting.value = false;
  }
};

onMounted(loadExpenses);
</script>
