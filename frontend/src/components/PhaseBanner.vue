<template>
  <div class="banner" :class="phaseClass">
    <div class="left">
      <span class="logo">🐺 AI 狼人杀</span>
      <span class="status" v-if="!winner && phase">
        第 {{ turn }} 天 · {{ phase === 'night' ? '🌙 夜晚' : '☀️ 白天' }}
      </span>
      <span class="status" v-else-if="!winner">等待开始</span>
      <span class="winner" v-else>🏆 {{ winner }} 获胜！</span>
    </div>
    <button class="detail-btn" @click="$emit('toggleDetail')" title="游戏详情">📋</button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ turn: Number, phase: String, winner: String })
defineEmits(['toggleDetail'])
const phaseClass = computed(() => {
  if (props.winner) return 'game-over'
  return props.phase === 'night' ? 'night' : 'day'
})
</script>

<style scoped>
.banner {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 20px;
  transition: background 0.5s;
  flex-shrink: 0;
}
.banner.night { background: linear-gradient(135deg, #0f0c29, #302b63, #24243e); }
.banner.day { background: linear-gradient(135deg, #1a2a6c, #b21f1f, #fdbb2d); }
.banner.game-over { background: linear-gradient(135deg, #11998e, #38ef7d); }
.left { display: flex; align-items: baseline; gap: 16px; }
.logo { font-size: 20px; font-weight: bold; color: #fff; }
.status { font-size: 14px; opacity: 0.85; }
.winner { font-size: 18px; font-weight: bold; color: #fff; }
.detail-btn {
  background: rgba(255,255,255,0.1);
  border: 1px solid rgba(255,255,255,0.2);
  color: #fff;
  font-size: 14px;
  padding: 6px 14px;
  border-radius: 6px;
  cursor: pointer;
}
.detail-btn:hover { background: rgba(255,255,255,0.2); }
</style>
