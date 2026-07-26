<template>
  <WorkspacePage back eyebrow="Payment detail" title="Payment Entry" description="Amount, mode, and invoice allocation." width="default">
    <template #actions>
      <AppButton v-if="payment && payment.docstatus === 1" variant="secondary" size="sm" icon="printer" @click="printPdf">Print</AppButton>
    </template>

    <SkeletonList v-if="loading" :rows="2" height="6rem" />

    <div v-else-if="payment" class="space-y-4">
      <!-- Amount hero -->
      <AppCard class="bg-gradient-to-br from-success to-success/80 text-success-fg" padding="lg">
        <div class="flex items-start justify-between">
          <div>
            <p class="text-xs font-semibold uppercase tracking-wide opacity-80">Customer</p>
            <p class="text-lg font-bold">{{ payment.party_name }}</p>
          </div>
          <StatusBadge tone="neutral" :dot="false" class="bg-white/20 text-success-fg">{{ payment.status }}</StatusBadge>
        </div>
        <p class="mt-5 text-xs font-semibold uppercase tracking-wide opacity-80">Amount paid</p>
        <p class="tnum text-4xl font-bold">{{ currency }} {{ fmt(payment.paid_amount) }}</p>
        <div class="mt-4 flex gap-6 text-sm font-medium opacity-90">
          <span>{{ formatDate(payment.posting_date) }}</span>
          <span>{{ payment.mode_of_payment }}</span>
        </div>
      </AppCard>

      <AppCard v-if="payment.references && payment.references.length">
        <h3 class="mb-3 text-xs font-bold uppercase tracking-wider text-muted">Allocated to</h3>
        <div class="divide-y divide-line">
          <div v-for="ref in payment.references" :key="ref.name" class="flex items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
            <div class="min-w-0">
              <p class="truncate text-sm font-semibold text-foreground">{{ ref.reference_name }}</p>
              <p class="text-xs text-muted">{{ ref.reference_doctype }}</p>
            </div>
            <p class="tnum text-sm font-bold text-foreground">{{ currency }} {{ fmt(ref.allocated_amount) }}</p>
          </div>
        </div>
      </AppCard>
    </div>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { useRoute } from 'vue-router';
import { useSessionStore } from '../stores/session';
import { getPaymentEntry, downloadPdf } from '../api/frappe';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppButton, StatusBadge, SkeletonList } from '../components/ui';

const route = useRoute();
const store = useSessionStore();
const currency = computed(() => store.currencyDisplay);
const payment = ref<any>(null);
const loading = ref(true);

const fmt = (n?: number) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

onMounted(async () => {
  const name = route.params.name as string;
  if (name) {
    try {
      payment.value = await getPaymentEntry(name);
    } finally {
      loading.value = false;
    }
  }
});

const formatDate = (date: string) => (date ? new Date(date).toLocaleDateString() : '');
const printPdf = () => payment.value && downloadPdf('Payment Entry', payment.value.name);
</script>
