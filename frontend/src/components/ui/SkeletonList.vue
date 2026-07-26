<template>
  <div class="space-y-3">
    <div v-for="n in rows" :key="n" class="skeleton" :style="{ height: height }" />
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ rows?: number; height?: string }>(), { rows: 4, height: '4.5rem' });
</script>
