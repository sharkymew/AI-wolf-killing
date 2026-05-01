<template>
  <div class="overlay" v-if="open" @click="$emit('close')">
    <div class="panel" @click.stop>
      <div class="panel-header">
        <h3>📋 游戏详情</h3>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>
      <div class="panel-body">
        <div class="section">
          <h4>玩家状态</h4>
          <div class="player-list">
            <div v-for="p in players" :key="p.id" class="player-row" :class="{ dead: !p.is_alive }">
              <span class="p-icon">{{ roleIcon(p.role_name) }}</span>
              <span class="p-name">#{{ p.id }} {{ p.role_name }}</span>
              <span class="p-model">{{ p.model }}</span>
              <span class="p-status">{{ p.is_alive ? '🟢' : '💀' }}</span>
              <div v-if="p.current_tokens" class="token-bar-wrap">
                <div class="token-bar" :style="{ width: p.percent + '%' }" :class="tokenBarClass(p.percent)"></div>
                <span class="token-text">{{ formatTokens(p.current_tokens) }}/{{ formatTokens(p.max_tokens) }} ({{ formatTokens(p.total_tokens_used) }}总)</span>
              </div>
            </div>
          </div>
        </div>
        <div class="section">
          <h4>全部事件</h4>
          <div class="event-list">
            <div v-for="(e, i) in events" :key="i" class="event-row">
              <span class="e-time">{{ fmt(e.time) }}</span>
              <span class="e-msg">{{ e.message }}</span>
            </div>
            <div v-if="events.length === 0" class="empty">暂无事件</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  open: Boolean,
  players: Array,
  events: Array,
})
defineEmits(['close'])

const icons = { '狼人': '🐺', '女巫': '🧪', '预言家': '🔮', '猎人': '🔫', '守卫': '🛡️', '白痴': '🤡', '平民': '👤' }
function roleIcon(name) { return icons[name] || '❓' }
function fmt(ts) { return new Date(ts).toLocaleTimeString('zh-CN', { hour12: false }) }
function formatTokens(n) { return n >= 1000 ? (n / 1000).toFixed(1) + 'k' : n }
function tokenBarClass(pct) { return pct > 80 ? 'danger' : pct > 50 ? 'warn' : 'ok' }
</script>

<style scoped>
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  z-index: 200;
  display: flex;
  justify-content: flex-end;
}
.panel {
  width: 380px;
  max-width: 90vw;
  height: 100%;
  background: #12122a;
  border-left: 1px solid #333;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #222;
}
.panel-header h3 { margin: 0; font-size: 16px; }
.close-btn {
  background: none;
  border: none;
  color: #888;
  font-size: 18px;
  cursor: pointer;
  padding: 4px 8px;
}
.close-btn:hover { color: #fff; }
.panel-body { flex: 1; overflow-y: auto; padding: 16px; }
.section { margin-bottom: 20px; }
.section h4 { font-size: 13px; color: #666; margin-bottom: 8px; text-transform: uppercase; }
.player-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 6px;
  background: #1a1a30;
  margin-bottom: 4px;
  font-size: 13px;
}
.player-row.dead { opacity: 0.4; }
.p-icon { font-size: 16px; }
.p-name { font-weight: bold; flex: 1; }
.p-model { font-size: 11px; color: #666; }
.p-status { font-size: 12px; }
.player-row { flex-wrap: wrap; }
.token-bar-wrap {
  width: 100%;
  margin-top: 4px;
  position: relative;
  height: 16px;
  background: #111;
  border-radius: 3px;
  overflow: hidden;
}
.token-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s;
}
.token-bar.ok { background: #2ecc71; }
.token-bar.warn { background: #f39c12; }
.token-bar.danger { background: #e74c3c; }
.token-text {
  position: absolute;
  inset: 0;
  font-size: 10px;
  color: #aaa;
  display: flex;
  align-items: center;
  justify-content: center;
}
.event-row {
  display: flex;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  border-bottom: 1px solid #1a1a2e;
}
.e-time { color: #555; flex-shrink: 0; }
.e-msg { color: #aaa; word-break: break-word; }
.empty { color: #555; font-size: 13px; padding: 10px 0; }
.panel-body::-webkit-scrollbar { width: 4px; }
.panel-body::-webkit-scrollbar-thumb { background: #333; border-radius: 2px; }
</style>
