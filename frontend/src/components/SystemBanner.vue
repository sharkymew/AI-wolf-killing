<template>
  <div class="banner" :class="type">
    <span class="banner-text">{{ text }}</span>
  </div>
</template>

<script setup>
defineProps({
  type: String,
  text: String,
})
</script>

<style scoped>
.banner {
  text-align: center;
  padding: 8px 16px;
  margin: 4px 0;
}
.banner-text {
  font-size: 13px;
  padding: 4px 16px;
  border-radius: 12px;
}
.banner.phase .banner-text { background: #1a2a10; color: #ffd700; }
.banner.wolf .banner-text { background: #2a1015; color: #e94560; }
.banner.witch .banner-text { background: #1a102a; color: #9b59b6; }
.banner.seer .banner-text { background: #101a2a; color: #3498db; }
.banner.death .banner-text { background: #1a1a1a; color: #888; }
.banner.vote .banner-text { background: #2a1a10; color: #f39c12; }
.banner.execute .banner-text { background: #2a1010; color: #e74c3c; }
.banner.hunter .banner-text { background: #2a1a10; color: #e67e22; }
.banner.game_over .banner-text { background: #1a2a10; color: #ffd700; font-weight: bold; font-size: 15px; }
.banner.log .banner-text { color: #666; }
.banner.error .banner-text { background: #2a1010; color: #e74c3c; }
</style>
