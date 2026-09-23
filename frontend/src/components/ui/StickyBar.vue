<template>
  <!-- Thumb-reachable action bar pinned above the bottom nav (mobile) / inline (desktop). -->
  <div class="pointer-events-none fixed inset-x-0 bottom-[76px] z-40 px-3.5 pb-2.5 lg:bottom-0 lg:left-[88px] lg:px-6 lg:pb-5">
    <div
      class="pointer-events-auto mx-auto max-w-3xl rounded-3xl bg-elevated/93 p-2.5 shadow-pop ring-1 ring-inset ring-line backdrop-blur-md"
    >
      <slot />
    </div>
  </div>
</template>
