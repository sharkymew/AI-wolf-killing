# AI 狼人杀 (AI Werewolf)

一个基于大语言模型（LLM）的命令行版狼人杀游戏模拟器。在这个系统中，你可以配置多个 AI 代理（支持 DeepSeek、OpenAI 等兼容接口）分别扮演狼人、女巫、预言家和平民，观察它们之间的推理、伪装、辩论与博弈。

## ✨ 核心特性

- **高性能并发架构**：基于 `asyncio` 重构的核心引擎，实现多模型并行推理（如所有玩家同时投票），大幅提升游戏运行速度。
- **智能记忆管理**：内置滑动窗口记忆机制，自动修剪过早的历史记录并保留关键 System Prompt，有效防止上下文溢出（Context Limit Exceeded）。
- **多模型支持**：支持通过 `config/game_config.yaml` 配置不同的 LLM 模型，包括专门的“裁判模型”用于精准解析动作。
- **完整游戏流程**：
  - **日夜交替**：包含夜晚行动（狼刀、女巫毒/救、预言家验人）和白天讨论（遗言、自由讨论、投票）。
  - **狼人协商**：狼人阵营在首轮盲选支持并行决策，协商阶段采用顺序发言机制确保达成杀人共识。
  - **平票 PK**：投票平局时触发 PK 发言与二轮投票机制。
  - **终局检测**：支持“狼人控场”（狼人数 >= 好人数）提前结束游戏，避免垃圾时间。
- **高级推理能力**：
  - **思维链 (CoT)**：支持配置 `is_reasoning: true`，让模型先输出思考过程（[dim]灰色显示[/dim]），再输出最终决策。
  - **裁判模型**：引入独立的 Judge Model，从模型复杂的推理文本中精准提取行动指令（如投票对象），解决正则解析不准的问题。
- **完善的日志系统**：
  - **实时流式输出**：使用 `rich` 库实现打字机效果的实时终端输出。
  - **双重记录**：同时生成可读性强的文本日志 (`logs/text_logs/`) 和结构化的 JSON 回放文件 (`logs/json/`)。

## 🚀 快速开始

### 1. 环境准备

确保你的 Python 版本 >= 3.8。

```bash
# 克隆项目
git clone https://github.com/sharkymew/AI-wolf-killing.git
cd AI-wolf-killing

# 创建并激活虚拟环境 (推荐)
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```
*(注：如果没有 `requirements.txt`，请安装以下核心库)*
```bash
pip install typer rich openai pydantic pyyaml python-dotenv
```

### 2. 配置模型

1. 复制环境变量示例文件：
   ```bash
   cp .env.example .env
   ```
2. 编辑 `.env` 文件，填入你的 API Key：
   ```env
   DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
   ```

3. 检查或修改 `config/game_config.yaml`。你可以为 6 个玩家位配置不同的模型，也可以配置一个专门的 `judge_model`：
   ```yaml
   models:
     - name: "DeepSeek1"
       provider: "deepseek"
       api_key: "env:DEEPSEEK_API_KEY"
       base_url: "https://api.deepseek.com"
       model: "deepseek-chat"
       is_reasoning: true  # 开启思考过程显示
     ...

   judge_model:
     name: "Judge"
     provider: "deepseek"
     api_key: "env:DEEPSEEK_API_KEY"
     model: "deepseek-chat"
     temperature: 0.1 # 低温确保解析准确
   ```

### 3. 运行游戏

```bash
python main.py
```

或者指定配置文件和最大回合数：

```bash
python main.py --config config/my_custom_config.yaml --rounds 100
```

## 📂 项目结构

```
.
├── config/
│   └── game_config.yaml    # 游戏与模型配置文件
├── logs/
│   ├── json/               # 存放结构化回放数据 (.json)
│   └── text_logs/          # 存放人类可读的对局日志 (.txt)
├── src/
│   ├── core/
│   │   ├── game.py         # 游戏核心引擎 (状态机、流程控制)
│   │   ├── player.py       # 玩家类 (LLM 交互、Prompt 组装)
│   │   └── role.py         # 角色定义 (狼人、女巫等)
│   ├── llm/
│   │   ├── client.py       # LLM 客户端封装
│   │   └── prompts.py      # 角色 Prompt 管理
│   └── utils/
│       ├── config.py       # 配置加载逻辑
│       └── logger.py       # 日志模块 (Rich + File)
├── main.py                 # 程序入口
├── .env                    # 环境变量 (API Keys)
└── README.md               # 项目文档
```

## 🧠 实现细节

### 狼人协商机制
为了避免多个狼人模型同时输出导致的目标冲突，系统实现了**顺序协商机制**：
1. 狼人 A 先发言并选择目标。
2. 狼人 B 接收到狼人 A 的选择作为上下文，再进行决策。
3. 如果意见不统一，进入多轮协商，直到达成一致或强制锁定多数票。

### 裁判模型 (Judge Model)
LLM（尤其是推理模型）往往废话较多，容易导致正则提取失败（例如：“我决定投给3号，因为...”）。
本项目引入了 `Judge Model`，当正则提取失败时，将玩家的完整发言投喂给裁判模型，由裁判模型精准提取出最终的数字 ID，大大提高了游戏的稳定性。

### 异步并发与记忆管理
- **Asyncio**: 所有的 LLM 网络请求均已异步化。在投票阶段，系统会使用 `asyncio.gather` 并行请求所有玩家的决策，极大缩短了等待时间。
- **Sliding Window**: 每个玩家维护一个固定长度的记忆窗口（默认保留 System Prompt + 最近 15 轮交互）。旧的对话记录会被自动修剪，确保游戏能无限进行而不受 Token 上限限制。

### 终局检测
为了优化游戏节奏，系统会在每个阶段结束时检查：
- **狼人控场**：存活狼人数 >= 存活好人数 -> 狼人直接胜利。
- **屠边/屠城**：所有狼人出局 或 所有好人出局。

## 🛠️ 依赖库

- **Typer**: 命令行界面构建
- **Rich**: 终端富文本显示与流式输出
- **OpenAI**: 调用兼容 OpenAI 协议的 LLM 接口
- **Pydantic**: 数据校验与配置管理
- **PyYAML**: YAML 配置文件解析

## 📝 License

MIT License
