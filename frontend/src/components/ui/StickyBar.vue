<template>
  <!-- Thumb-reachable action bar pinned above the bottom nav (mobile) / inline (desktop). -->
  <div class="pointer-events-none fixed inset-x-0 bottom-[68px] z-40 px-4 pb-3 lg:bottom-0 lg:left-[88px] lg:px-6 lg:pb-5">
    <div class="pointer-events-auto mx-auto max-w-3xl rounded-3xl border border-line bg-elevated/95 p-3 shadow-pop backdrop-blur">
      <slot />
    </div>
  </div>
</template>
