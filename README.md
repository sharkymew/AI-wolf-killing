# AI 狼人杀 (AI Werewolf)

一个基于大语言模型（LLM）的命令行版狼人杀游戏模拟器。多个 AI 代理分别扮演狼人、女巫、预言家、猎人和平民，通过真实的推理、协商、伪装与博弈完成一局完整对局。支持 DeepSeek、SiliconFlow、OpenAI 等任意兼容 OpenAI 协议的接口。

## ✨ 核心特性

- **完整角色实现**：狼人、女巫（解药/毒药）、预言家（验人）、猎人（死亡开枪）、平民，含猎人被毒死无法开枪等边界规则
- **并发异步架构**：基于 `asyncio` 的核心引擎，投票等独立决策使用 `asyncio.gather` 并行，狼人协商采用顺序发言确保共识
- **Token 级记忆管理**：使用 `tiktoken` 精确计算每条消息的 token 数，滑动窗口自动修剪旧记忆，始终保留 System Prompt
- **多模型混搭**：每个玩家位可配置不同模型，支持同时使用推理模型（`is_reasoning`）与普通模型
- **裁判模型（Judge）**：引入独立 Judge Model 从复杂推理文本中精准提取行动 ID，兜底正则解析
- **JSON 模式**：可为单个模型开启 `json_mode`，统一输出 `{"thought": "...", "action": ID}` 结构
- **Mock 客户端**：内置 `MockLLMClient`，无需 API Key 即可运行完整对局（用于测试和演示）
- **平票 PK 机制**：投票平局时触发候选人 PK 发言与二轮投票
- **终局检测**：狼人数 ≥ 好人数时提前判定狼人胜利，避免垃圾时间
- **结构化日志**：实时 `rich` 富文本终端输出 + 文本日志 (`logs/text_logs/`) + JSON 回放文件 (`logs/json/`)

## 🚀 快速开始

### 1. 环境准备

Python >= 3.8

```bash
git clone https://github.com/sharkymew/AI-wolf-killing.git
cd AI-wolf-killing

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. 配置

复制并编辑环境变量文件：

```bash
cp .env.example .env
# 填入你的 API Key，例如：
# DEEPSEEK_API_KEY=sk-xxxxxxxx
# SILICONFLOW_API_KEY=sk-xxxxxxxx
```

编辑 `config/game_config.yaml`。每个 `models` 条目对应一个玩家位（轮询分配），数量须 ≥ 角色总数：

```yaml
models:
  - name: "DeepSeek1"
    provider: "deepseek"
    api_key: "env:DEEPSEEK_API_KEY"      # 从环境变量读取
    base_url: "https://api.deepseek.com"
    model: "deepseek-chat"
    is_reasoning: true   # 开启两步推理（先思考后决策）
    json_mode: true      # 输出结构化 JSON 动作
    temperature: 0.7
    max_retries: 3
    timeout: 60.0
  # ... 更多玩家模型

judge_model:             # 可选：用于精准解析行动的裁判模型
  name: "Judge"
  provider: "deepseek"
  api_key: "env:DEEPSEEK_API_KEY"
  base_url: "https://api.deepseek.com"
  model: "deepseek-chat"
  temperature: 0.1       # 低温保证解析稳定

game:
  max_turns: 100
  max_memory_tokens: 8000   # 每个玩家记忆上限（token 数）
  random_seed: null          # 固定随机种子（null = 随机）
  roles:
    # 常用板子：
    # 6人局: 2狼 1女 1预 0猎 2民  (默认)
    # 7人局: 2狼 1女 1预 1猎 2民
    # 9人局: 3狼 1女 1预 1猎 3民
    werewolf: 2
    witch: 1
    seer: 1
    hunter: 1
    villager: 2
```

### 3. 运行

```bash
# 使用默认配置
python main.py

# 指定配置文件和最大回合数
python main.py --config config/game_config.yaml --rounds 100

# 使用 Mock 客户端（无需 API Key）快速体验
python main.py --config config/test_config.yaml --rounds 10
```

## 📂 项目结构

```
.
├── config/
│   ├── game_config.yaml     # 正式对局配置（真实 LLM）
│   └── test_config.yaml     # Mock 测试配置（无需 API Key）
├── logs/
│   ├── json/                # 结构化回放文件 (.json)，按需创建
│   └── text_logs/           # 人类可读的对局日志 (.txt)
├── src/
│   ├── core/
│   │   ├── game.py          # 核心引擎（状态机、日夜流程、胜负判断）
│   │   ├── player.py        # 玩家类（LLM 交互、Prompt 组装、记忆管理）
│   │   └── role.py          # 角色定义（狼人、女巫、预言家、猎人、平民）
│   ├── llm/
│   │   ├── base.py          # LLMClientProtocol（类型协议）
│   │   ├── client.py        # 真实 LLM 客户端（OpenAI 兼容）
│   │   ├── mock_client.py   # Mock 客户端（测试用）
│   │   └── prompts.py       # 角色系统 Prompt 管理
│   └── utils/
│       ├── config.py        # 配置加载与校验（Pydantic）
│       └── logger.py        # 日志模块（Rich + 文件）
├── tests/
│   ├── test_config.py          # 配置加载逻辑测试
│   ├── test_game_engine.py     # 核心引擎逻辑测试（胜负判断、角色分配）
│   ├── test_mock_client.py     # Mock 客户端测试
│   ├── test_player_actions.py  # 玩家行动解析测试
│   ├── test_player_memory.py   # 记忆管理测试
│   └── test_simulation.py      # 完整对局集成测试（Mock）
├── .github/workflows/ci.yml    # GitHub Actions CI
├── main.py                     # 程序入口（Typer CLI）
└── requirements.txt
```

## 🧠 实现细节

### 狼人协商机制

首轮盲选并行发起（所有狼人同时决策），若有分歧进入最多 3 轮顺序协商：
1. 狼人 A 先出票。
2. 狼人 B 看到 A 的选择后出票。
3. 以此类推，直到达成一致，否则强制锁定多数票。

### 行动解析流水线

模型输出 → JSON 解析（如启用 `json_mode`）→ 裁判模型提取（如配置 `judge_model`）→ 正则兜底 → 返回目标 ID。任一环节成功即短路后续步骤。

### 异步并发

- **并行**：投票、PK 投票、狼人首轮盲选均使用 `asyncio.gather`
- **顺序**：白天讨论、狼人协商阶段保留顺序执行，确保上下文连贯

### Token 级记忆修剪

每次生成前调用 `_manage_memory()`，用 `tiktoken` 从最新消息向前累加 token，超出 `max_memory_tokens` 时截断，System Prompt 始终保留。

### 猎人规则

- 被狼刀杀死 → 触发开枪
- 被投票处决 → 触发开枪
- 被女巫毒死 → **不能**开枪

## 🛠️ 依赖

| 库 | 用途 |
|---|---|
| `typer` | CLI 参数解析 |
| `rich` | 终端富文本与流式输出 |
| `openai` | OpenAI 兼容 API 客户端（异步） |
| `pydantic` | 配置数据校验 |
| `pyyaml` | YAML 配置解析 |
| `tiktoken` | Token 精确计数（记忆管理） |
| `python-dotenv` | 环境变量加载 |

## 🧪 测试

```bash
python -m unittest discover -s tests -p "test_*.py"
```

CI 在每次 push/PR 时自动运行（GitHub Actions）。

## 📝 License

MIT License
