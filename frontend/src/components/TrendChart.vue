<template>
  <div class="trend">
    <div class="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
      <span v-for="s in series" :key="s.key" class="inline-flex items-center gap-1.5">
        <span class="h-2.5 w-2.5 rounded-full" :style="{ background: s.color }"></span>{{ s.label }}
      </span>
    </div>

    <div ref="box" class="relative" :style="{ height: `${HEIGHT}px` }">
      <svg v-if="width" :width="width" :height="HEIGHT" class="block overflow-visible" role="img" :aria-label="ariaLabel">
        <!-- gridlines + y labels -->
        <g v-for="t in yTicks" :key="t">
          <line :x1="PAD.left" :x2="width - PAD.right" :y1="y(t)" :y2="y(t)" class="grid" />
          <text :x="PAD.left - 8" :y="y(t)" text-anchor="end" dominant-baseline="middle" class="axis">{{ short(t) }}</text>
        </g>
        <!-- x labels -->
        <text v-for="i in xTicks" :key="`x${i}`" :x="x(i)" :y="HEIGHT - 6" text-anchor="middle" class="axis">{{ dayLabel(rows[i].date) }}</text>

        <!-- lines -->
        <path v-for="s in series" :key="s.key" :d="path(s.key)" fill="none" :stroke="s.color" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />

        <!-- end dots + direct labels -->
        <g v-for="s in endLabels" :key="`end${s.key}`">
          <circle :cx="x(rows.length - 1)" :cy="s.dotY" r="4" :fill="s.color" class="ring" />
          <text :x="x(rows.length - 1) + 8" :y="s.labelY" dominant-baseline="middle" class="label">{{ s.label }}</text>
        </g>

        <!-- hover layer -->
        <g v-if="hover !== null">
          <line :x1="x(hover)" :x2="x(hover)" :y1="PAD.top" :y2="HEIGHT - PAD.bottom" class="crosshair" />
          <circle v-for="s in series" :key="`h${s.key}`" :cx="x(hover)" :cy="y(rows[hover][s.key])" r="4" :fill="s.color" class="ring" />
        </g>
        <rect
          :x="PAD.left" :y="0" :width="Math.max(plotWidth, 0)" :height="HEIGHT"
          fill="transparent"
          @pointermove="onMove" @pointerdown="onMove" @pointerleave="hover = null"
        />
      </svg>

      <div
        v-if="hover !== null"
        class="pointer-events-none absolute top-0 z-10 min-w-[11rem] rounded-xl border border-line bg-card px-3 py-2 text-xs shadow-raised"
        :style="tooltipStyle"
      >
        <p class="mb-1 font-semibold text-foreground">{{ fullDate(rows[hover].date) }}</p>
        <p v-for="s in series" :key="`t${s.key}`" class="flex items-center justify-between gap-3 text-muted">
          <span class="inline-flex items-center gap-1.5"><span class="h-2 w-2 rounded-full" :style="{ background: s.color }"></span>{{ s.label }}</span>
          <span class="tnum whitespace-nowrap font-semibold text-foreground">{{ currency }} {{ money(rows[hover][s.key]) }}</span>
        </p>
      </div>
    </div>

    <button type="button" class="mt-2 text-xs font-semibold text-primary" @click="showTable = !showTable">
      {{ showTable ? 'Hide table' : 'Show as table' }}
    </button>
    <div v-if="showTable" class="mt-2 max-h-72 overflow-auto rounded-xl border border-line">
      <table class="w-full text-xs">
        <thead class="sticky top-0 bg-card-muted text-muted">
          <tr><th class="px-3 py-2 text-left font-semibold">Date</th><th v-for="s in series" :key="`th${s.key}`" class="px-3 py-2 text-right font-semibold">{{ s.label }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.date" class="border-t border-line">
            <td class="px-3 py-1.5 text-foreground">{{ fullDate(r.date) }}</td>
            <td v-for="s in series" :key="`td${s.key}`" class="tnum px-3 py-1.5 text-right text-foreground">{{ money(r[s.key]) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import type { PeriodDailyRow } from '../types';
import { useTheme } from '../composables/useTheme';

type Key = 'sales' | 'collections';

const props = defineProps<{ rows: PeriodDailyRow[]; currency: string }>();

// Categorical slots 1 and 2 of the dataviz reference palette, validated against this
// app's card surfaces (#ffffff light, #1e2122 dark): CVD ΔE ≥ 24, all ≥ 3:1 contrast.
const series = computed(() => {
  const dark = isDark.value;
  return [
    { key: 'sales' as Key, label: 'Sales', color: dark ? '#3987e5' : '#2a78d6' },
    { key: 'collections' as Key, label: 'Collections', color: dark ? '#d95926' : '#eb6834' },
  ];
});

const HEIGHT = 220;
const PAD = { top: 12, right: 88, bottom: 26, left: 44 };

const box = ref<HTMLElement | null>(null);
const width = ref(0);
const hover = ref<number | null>(null);
const showTable = ref(false);
const { isDark } = useTheme();

let resize: ResizeObserver | null = null;
onMounted(() => {
  resize = new ResizeObserver(([entry]) => (width.value = entry.contentRect.width));
  if (box.value) resize.observe(box.value);
});
onBeforeUnmount(() => {
  resize?.disconnect();
});

const plotWidth = computed(() => width.value - PAD.left - PAD.right);
const plotHeight = HEIGHT - PAD.top - PAD.bottom;

const maxValue = computed(() => {
  const m = Math.max(0, ...props.rows.flatMap((r) => [r.sales, r.collections]));
  return m > 0 ? m : 1;
});
// "Nice" y-axis: 4 intervals on a 1/2/2.5/5 × 10^n step.
const yStep = computed(() => {
  const raw = maxValue.value / 4;
  const mag = 10 ** Math.floor(Math.log10(raw));
  return ([1, 2, 2.5, 5, 10].find((f) => f * mag >= raw) || 10) * mag;
});
const yMax = computed(() => yStep.value * 4);
const yTicks = computed(() => [0, 1, 2, 3, 4].map((i) => i * yStep.value));

const x = (i: number) => PAD.left + (props.rows.length > 1 ? (i / (props.rows.length - 1)) * plotWidth.value : plotWidth.value / 2);
const y = (v: number) => PAD.top + plotHeight - (v / yMax.value) * plotHeight;

const xTicks = computed(() => {
  const n = props.rows.length;
  const count = Math.max(2, Math.min(6, Math.floor(plotWidth.value / 70)));
  if (n <= count) return props.rows.map((_, i) => i);
  const step = (n - 1) / (count - 1);
  return Array.from({ length: count }, (_, i) => Math.round(i * step));
});

const path = (key: Key) => props.rows.map((r, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(r[key]).toFixed(1)}`).join('');

// Direct labels at the line ends, pushed apart so they never overlap.
const endLabels = computed(() => {
  const last = props.rows[props.rows.length - 1];
  if (!last) return [];
  const labels = series.value
    .map((s) => ({ ...s, dotY: y(last[s.key]), labelY: y(last[s.key]) }))
    .sort((a, b) => a.labelY - b.labelY);
  for (let i = 1; i < labels.length; i++) {
    if (labels[i].labelY - labels[i - 1].labelY < 14) labels[i].labelY = labels[i - 1].labelY + 14;
  }
  return labels;
});

const onMove = (e: PointerEvent) => {
  const rect = (e.currentTarget as SVGRectElement).ownerSVGElement!.getBoundingClientRect();
  const px = e.clientX - rect.left - PAD.left;
  const n = props.rows.length;
  hover.value = n > 1 ? Math.min(n - 1, Math.max(0, Math.round((px / plotWidth.value) * (n - 1)))) : 0;
};

const tooltipStyle = computed(() => {
  if (hover.value === null) return {};
  const left = x(hover.value);
  return left > width.value / 2 ? { right: `${width.value - left + 12}px` } : { left: `${left + 12}px` };
});

const money = (n: number) => (n || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const short = (n: number) =>
  n >= 1e6 ? `${+(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${+(n / 1e3).toFixed(1)}k` : `${+n.toFixed(0)}`;
const parse = (s: string) => new Date(`${s}T00:00:00`);
const dayLabel = (s: string) => parse(s).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
const fullDate = (s: string) => parse(s).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });

const ariaLabel = computed(
  () => `Daily sales and collections from ${props.rows[0]?.date} to ${props.rows[props.rows.length - 1]?.date}. Use "Show as table" for the values.`,
);
</script>

<style scoped>
.grid { stroke: rgb(var(--c-line)); stroke-width: 1; shape-rendering: crispEdges; }
.axis { fill: rgb(var(--c-muted)); font-size: 10px; font-variant-numeric: tabular-nums; }
.label { fill: rgb(var(--c-foreground)); font-size: 11px; font-weight: 600; }
.crosshair { stroke: rgb(var(--c-subtle)); stroke-width: 1; }
.ring { stroke: rgb(var(--c-card)); stroke-width: 2; }
</style>
