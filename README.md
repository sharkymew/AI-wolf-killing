# AI 狼人杀 (AI Werewolf)

一个基于大语言模型（LLM）的狼人杀游戏模拟器。多个 AI 代理分别扮演狼人、女巫、预言家、猎人和平民，通过真实的推理、协商、伪装与博弈完成一局完整对局。支持 DeepSeek、SiliconFlow、OpenAI 等任意兼容 OpenAI 协议的接口。

提供**终端模式**和 **Web UI 模式**两种运行方式。

## ✨ 核心特性

- **完整角色实现**：狼人、女巫（解药/毒药）、预言家（验人）、猎人（死亡开枪）、平民，含猎人被毒死无法开枪等边界规则
- **Web UI 实时观战**：Vue 3 聊天风格界面，发言气泡 + 可折叠思考过程 + 事件横幅，上帝视角查看所有 AI 的推理与决策
- **并发异步架构**：基于 `asyncio` 的核心引擎，投票等独立决策使用 `asyncio.gather` 并行，狼人协商采用顺序发言确保共识
- **Token 级记忆管理**：使用 `tiktoken` 精确计算每条消息的 token 数，滑动窗口自动修剪旧记忆，始终保留 System Prompt
- **多模型混搭**：每个玩家位可配置不同模型，支持同时使用推理模型（`is_reasoning`）与普通模型，不同玩家可连不同 API 服务商
- **裁判模型（Judge）**：引入独立 Judge Model 从复杂推理文本中精准提取行动 ID，兜底正则解析
- **JSON 模式**：可为单个模型开启 `json_mode`，统一输出 `{"thought": "...", "action": ID}` 结构
- **Mock 客户端**：内置 `MockLLMClient`，无需 API Key 即可运行完整对局（用于测试和演示）
- **平票 PK 机制**：投票平局时触发候选人 PK 发言与二轮投票
- **终局检测**：狼人数 ≥ 好人数时提前判定狼人胜利，避免垃圾时间
- **结构化日志**：实时 `rich` 富文本终端输出 + 文本日志 + JSON 回放文件

## 🚀 快速开始

### 1. 环境准备

Python >= 3.10，Node.js >= 18

```bash
git clone https://github.com/sharkymew/AI-wolf-killing.git
cd AI-wolf-killing

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cd frontend && npm install && cd ..
```

### 2. 配置

```bash
cp .env.example .env
# 填入你的 API Key
```

编辑 `config/game_config.yaml`。每个 `models` 条目对应一个玩家位：

```yaml
models:
  - name: "DeepSeek1"
    provider: "deepseek"
    api_key: "env:DEEPSEEK_API_KEY"
    base_url: "https://api.deepseek.com"
    model: "deepseek-v4-pro"
    is_reasoning: true
    json_mode: true

game:
  roles:
    werewolf: 2
    witch: 1
    seer: 1
    hunter: 1
    villager: 2
```

### 3. 运行

**Web UI 模式（推荐）**：

```bash
./start.sh
# 自动启动后端 + 前端，打开浏览器 http://localhost:5173
```

**终端模式**：

```bash
python main.py start                           # 默认配置
python main.py start -c config/test_config.yaml  # Mock 客户端
```

**仅后端（前端单独启动）**：

```bash
python main.py server                          # 后端 :8000
cd frontend && npm run dev                     # 前端 :5173
```

## 🖥️ Web UI

微信风格聊天界面，实时展示每个 AI 模型的发言和思考过程：

- **发言气泡**：每个模型输出以气泡展示，头像可点击查看模型信息
- **思考过程**：推理模型的 CoT 思考自动折叠在气泡内，点击展开
- **事件横幅**：阶段切换、死亡、投票、处决等系统事件居中穿插
- **狼人协商**：夜晚狼人选目标的过程实时可见
- **详情面板**：右上角 📋 按钮滑出玩家状态总览和完整事件日志
- **再来一局**：游戏结束后点击即可重开

## 📂 项目结构

```
.
├── config/
│   ├── game_config.yaml     # 正式对局配置
│   └── test_config.yaml     # Mock 测试配置
├── frontend/                # Vue 3 Web UI
│   ├── src/
│   │   ├── App.vue          # 根组件：WebSocket 连接与事件路由
│   │   └── components/
│   │       ├── ChatBubble.vue       # 发言气泡（含可折叠思考过程）
│   │       ├── ConversationView.vue # 聊天流容器
│   │       ├── SystemBanner.vue     # 系统事件横幅
│   │       ├── DetailPanel.vue      # 详情滑出面板
│   │       └── PhaseBanner.vue      # 顶部状态条
│   ├── package.json
│   └── vite.config.js
├── src/
│   ├── core/
│   │   ├── game.py          # 核心引擎（事件回调、日夜流程、胜负判断）
│   │   ├── player.py        # 玩家类（LLM 交互、思考回调、记忆管理）
│   │   └── role.py          # 角色定义（狼人、女巫、预言家、猎人、平民）
│   ├── llm/
│   │   ├── base.py          # LLMClientProtocol
│   │   ├── client.py        # 真实 LLM 客户端
│   │   ├── mock_client.py   # Mock 客户端
│   │   └── prompts.py       # 角色 Prompt
│   ├── server/
│   │   └── game_server.py   # FastAPI + WebSocket 服务器
│   └── utils/
│       ├── config.py        # 配置加载与校验
│       └── logger.py        # 日志模块
├── tests/
│   ├── test_config.py
│   ├── test_game_engine.py
│   ├── test_mock_client.py
│   ├── test_player_actions.py
│   ├── test_player_memory.py
│   └── test_simulation.py
├── .github/workflows/ci.yml
├── main.py                  # CLI 入口（start / server 命令）
├── start.sh                 # 一键启动脚本
└── requirements.txt
```

## 🧠 实现细节

### WebSocket 事件系统

GameEngine 通过 `on_event` 回调推送结构化事件，FastAPI WebSocket 广播到前端。事件类型包括 `game_init`、`phase`、`night_wolf_vote`、`night_witch`、`night_seer`、`day_speech`、`day_vote`、`player_thinking`、`game_over` 等。

### 狼人协商机制

首轮盲选并行发起，分歧时进入最多 3 轮顺序协商，每轮每位狼人的投票实时推送到前端。无法达成一致则强制锁定多数票。

### 行动解析流水线

模型输出 → JSON 解析（`json_mode`）→ 裁判模型提取 → 正则兜底 → 返回目标 ID。JSON 模式仅在动作阶段启用，避免发言时的 400 错误。

### 异步并发

- **并行**：投票、PK 投票、狼人首轮盲选使用 `asyncio.gather`
- **顺序**：白天讨论、狼人协商保留顺序，每完成一个模型立刻推送结果

### 猎人规则

- 被狼刀 / 投票处决 → 触发开枪（`can_shoot` 确保只开一次）
- 被女巫毒死 → 不能开枪

## 🛠️ 依赖

| 库 | 用途 |
|---|---|
| `typer` | CLI 参数解析 |
| `rich` | 终端富文本 |
| `openai` | OpenAI 兼容 API 客户端 |
| `pydantic` | 配置校验 |
| `pyyaml` | YAML 配置解析 |
| `tiktoken` | Token 精确计数 |
| `python-dotenv` | 环境变量加载 |
| `fastapi` | Web API 框架 |
| `uvicorn[standard]` | ASGI 服务器（含 WebSocket） |
| `websockets` | WebSocket 协议支持 |

## 🧪 测试

```bash
python -m pytest tests/ -v
```

CI 在每次 push/PR 时自动运行。

## 📝 License

MIT License
