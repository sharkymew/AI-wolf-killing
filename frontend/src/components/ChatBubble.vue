<template>
  <div class="bubble-wrapper" :class="factionClass">
    <div class="avatar" @click="showInfo = !showInfo" :title="player.model">
      <span class="avatar-emoji">{{ roleIcon }}</span>
    </div>
    <div class="bubble-body">
      <div class="bubble-header">
        <span class="player-name">#{{ player.id }} {{ player.role_name }}</span>
        <span class="model-tag">{{ player.model }}</span>
      </div>
      <div class="speech-text">{{ speech }}</div>
      <div v-if="thinking" class="thinking-section">
        <div class="thinking-toggle" @click="thinkingOpen = !thinkingOpen">
          {{ thinkingOpen ? '▼' : '▶' }} 思考过程
        </div>
        <div v-if="thinkingOpen" class="thinking-text">{{ thinking }}</div>
      </div>
    </div>
    <div v-if="showInfo" class="info-popup" @click="showInfo = false">
      <div class="info-card" @click.stop>
        <div class="info-emoji">{{ roleIcon }}</div>
        <div class="info-name">玩家 {{ player.id }}</div>
        <div class="info-role">{{ player.role_name }} · {{ factionLabel }}</div>
        <div class="info-model">模型: {{ player.model }}</div>
        <div class="info-status" :class="{ alive: player.is_alive, dead: !player.is_alive }">
          {{ player.is_alive ? '🟢 存活' : '💀 死亡' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  player: Object,
  speech: String,
  thinking: String,
})

const thinkingOpen = ref(false)
const showInfo = ref(false)

const factionClass = computed(() => props.player.faction)
const factionLabel = computed(() => props.player.faction === 'werewolf' ? '狼人阵营' : '好人阵营')

const roleIcons = { '狼人': '🐺', '女巫': '🧪', '预言家': '🔮', '猎人': '🔫', '平民': '👤' }
const roleIcon = computed(() => roleIcons[props.player.role_name] || '❓')
</script>

<style scoped>
.bubble-wrapper {
  display: flex;
  gap: 10px;
  padding: 8px 16px;
  align-items: flex-start;
}
.avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #1e2a4a;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  flex-shrink: 0;
  font-size: 20px;
  transition: transform 0.15s;
}
.avatar:hover { transform: scale(1.1); }
.bubble-body {
  flex: 1;
  min-width: 0;
}
.bubble-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.player-name {
  font-weight: bold;
  font-size: 14px;
}
.bubble-wrapper.werewolf .player-name { color: #e94560; }
.bubble-wrapper.good .player-name { color: #4a9eff; }
.model-tag {
  font-size: 11px;
  color: #666;
  background: #1a1a2e;
  padding: 2px 6px;
  border-radius: 4px;
}
.speech-text {
  color: #ddd;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.thinking-section { margin-top: 8px; }
.thinking-toggle {
  font-size: 12px;
  color: #888;
  cursor: pointer;
  user-select: none;
}
.thinking-toggle:hover { color: #aaa; }
.thinking-text {
  margin-top: 6px;
  padding: 10px;
  background: #111827;
  border-left: 3px solid #666;
  border-radius: 0 6px 6px 0;
  font-size: 12px;
  color: #999;
  white-space: pre-wrap;
  line-height: 1.5;
}
.info-popup {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.3);
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
}
.info-card {
  background: #1a1a2e;
  border: 1px solid #333;
  border-radius: 12px;
  padding: 24px;
  text-align: center;
  min-width: 220px;
}
.info-emoji { font-size: 48px; margin-bottom: 8px; }
.info-name { font-size: 20px; font-weight: bold; margin-bottom: 4px; }
.info-role { color: #aaa; margin-bottom: 8px; }
.info-model { font-size: 13px; color: #888; margin-bottom: 8px; }
.info-status { font-size: 13px; }
.info-status.alive { color: #4caf50; }
.info-status.dead { color: #666; }
</style>
