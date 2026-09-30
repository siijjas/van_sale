<template>
  <WorkspacePage back eyebrow="Shift reports" title="X & Y reports" description="X is a live snapshot of your open shift. Y is the final report of a closed shift." width="default">
    <SkeletonList v-if="loading" :rows="4" height="5rem" />

    <div v-else class="space-y-5">
      <AppCard v-if="activeShift" interactive padding="lg" @click="router.push({ name: 'shift-report-x' })">
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <span class="flex h-11 w-11 items-center justify-center rounded-2xl bg-success/12 text-success">
              <AppIcon name="activity" :size="22" />
            </span>
            <div>
              <p class="font-bold text-foreground">X report</p>
              <p class="text-xs text-muted">Current shift{{ activeShift.period_start ? `, open since ${formatTime(activeShift.period_start)}` : '' }}</p>
            </div>
          </div>
          <AppIcon name="chevron-right" :size="18" class="text-muted" />
        </div>
      </AppCard>

      <section>
        <p class="mb-3 text-xs font-bold uppercase tracking-wider text-muted">Closed shifts · Y reports</p>
        <AppAlert v-if="error" tone="danger" :message="error" />
        <EmptyState v-else-if="!closings.length" icon="receipt" title="No closed shifts yet" description="Y reports appear here once you close a shift." />
        <div v-else class="space-y-2.5">
          <AppCard v-for="c in closings" :key="c.name" padding="sm" interactive @click="router.push({ name: 'shift-report-y', params: { name: c.name } })">
            <div class="flex items-center justify-between gap-3">
              <div class="min-w-0">
                <p class="font-semibold text-foreground">{{ formatDate(c.shift_date) }}</p>
                <p class="mt-0.5 truncate text-xs text-muted">
                  {{ store.isManager ? `${c.driver_name || c.driver} · ` : '' }}{{ formatTime(c.period_start) }} – {{ formatTime(c.period_end) }}
                </p>
              </div>
              <div class="text-right">
                <p class="tnum text-sm font-bold text-foreground">{{ currency }} {{ fmt(c.total_sales) }}</p>
                <p v-if="c.net_difference" class="tnum text-xs font-semibold" :class="c.net_difference > 0 ? 'text-success' : 'text-danger'">
                  {{ c.net_difference > 0 ? '+' : '−' }}{{ fmt(Math.abs(c.net_difference)) }} variance
                </p>
                <p v-else class="text-xs text-muted">Balanced</p>
              </div>
            </div>
          </AppCard>
        </div>
      </section>
    </div>
  </WorkspacePage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import * as api from '../api/frappe';
import { useSessionStore } from '../stores/session';
import type { ActiveShift, ShiftClosingListRow } from '../types';
import WorkspacePage from '../components/WorkspacePage.vue';
import { AppCard, AppAlert, AppIcon, EmptyState, SkeletonList } from '../components/ui';

const router = useRouter();
const store = useSessionStore();
const currency = computed(() => store.currencyDisplay);

const loading = ref(true);
const error = ref('');
const activeShift = ref<ActiveShift | null>(null);
const closings = ref<ShiftClosingListRow[]>([]);

const fmt = (n?: number) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const formatTime = (ts: string | null) => {
  const d = ts ? new Date(ts.replace(' ', 'T')) : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : '—';
};
const formatDate = (s: string) => {
  const d = new Date(`${s}T00:00:00`);
  return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
};

onMounted(async () => {
  try {
    const [shift, rows] = await Promise.all([api.getActiveShift().catch(() => null), api.getShiftClosings()]);
    activeShift.value = shift;
    closings.value = rows;
  } catch (e: any) {
    error.value = e?.message || 'Could not load shift reports.';
  } finally {
    loading.value = false;
  }
});
</script>
