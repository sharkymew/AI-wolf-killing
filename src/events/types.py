"""WebSocket 事件类型常量。

事件字面量是前后端协议契约的一部分，前端 `frontend/src/App.vue`
中的 switch case 与此处常量值必须保持一致——重命名常量名是安全的，
但**不要修改字符串值**。
"""
from typing import Final

# 游戏初始化与阶段切换
GAME_INIT: Final[str] = "game_init"
PHASE: Final[str] = "phase"
GAME_OVER: Final[str] = "game_over"

# 玩家思考与 token 用量
PLAYER_THINKING: Final[str] = "player_thinking"
TOKEN_USAGE: Final[str] = "token_usage"

# 夜晚阶段
NIGHT_WOLF_KILL: Final[str] = "night_wolf_kill"
NIGHT_WOLF_VOTE: Final[str] = "night_wolf_vote"
NIGHT_WITCH: Final[str] = "night_witch"
NIGHT_WITCH_ACTION: Final[str] = "night_witch_action"
NIGHT_GUARD: Final[str] = "night_guard"
NIGHT_GUARD_ACTION: Final[str] = "night_guard_action"
NIGHT_SEER: Final[str] = "night_seer"
NIGHT_SEER_ACTION: Final[str] = "night_seer_action"
NIGHT_RESULT: Final[str] = "night_result"

# 白天阶段
DAY_SPEECH: Final[str] = "day_speech"
DAY_VOTE: Final[str] = "day_vote"
DAY_EXECUTE: Final[str] = "day_execute"
VOTE_RESULT_PK_TIE: Final[str] = "vote_result_pk_tie"

# 玩家状态变化
PLAYER_DEAD: Final[str] = "player_dead"
PLAYER_INTERACTION: Final[str] = "player_interaction"

# 技能触发
HUNTER_SHOOT: Final[str] = "hunter_shoot"
IDIOT_REVEAL: Final[str] = "idiot_reveal"

# 错误
ERROR: Final[str] = "error"
