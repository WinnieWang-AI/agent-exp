# Agent Exp - 多 Agent 协作平台

## 快速启动

### 启动 Web 前端（Video Agent Studio）

```bash
bash web/run.sh
```

该脚本会自动：
1. 加载 `env.sh` 中的环境变量（Nacos/Statsig/LLM 配置）
2. 检查并安装 `fastapi`、`uvicorn` 依赖
3. 启动 uvicorn 服务，默认监听 `0.0.0.0:8080`，支持热重载

访问地址：`http://<机器IP>:8080/`

可通过环境变量自定义端口和地址：
```bash
PORT=9090 HOST=0.0.0.0 bash web/run.sh
```

### 命令行运行（Auto-Eval 模式）

```bash
bash run.sh [视频路径] [项目名]
```

默认复现 `video_sample/killbill.mp4`，输出到 `output/<项目名>/`。

## 前端功能

页面提供三个 Tab：

| Tab | WebSocket 端点 | 说明 |
|-----|---------------|------|
| Video Director | `/ws/chat/video-director` | 与导演 agent 单独对话 |
| Auto Evaluator | `/ws/chat/video-auto-eval` | 与评估 agent 单独对话 |
| Auto Interaction | `/ws/auto` | auto-eval 自动驱动 director 协作 |

另有多 agent 聊天室端点 `/ws/room`，支持 `@mention`：
- `@Director` — video-director agent
- `@Evaluator` — video-auto-eval agent
- `@Optimizer` — agent-optimizer agent
- 不加 `@` 或 `@All` — 广播给所有 agent

## Session 管理

每次对话会生成一个 `session_id`（UUID），前端右上角会显示（点击可复制）。

数据存储：
- `output/.sessions/{session_id}/meta.json` — session 元数据
- `output/.sessions/{session_id}/chat.jsonl` — 聊天记录

REST API：
- `GET /api/sessions` — 列出所有 session
- `GET /api/sessions/{session_id}` — 获取 session 详情和聊天历史

## 配置

环境变量通过 `env.sh` 加载，包含：
- Nacos 配置中心连接信息（自动拉取 LLM/Sora/Gemini 等配置）
- Statsig 配置（自动拉取 Vidu 配置）

启动前务必确保 `env.sh` 存在且内容正确，否则会报 `LLM not set` 错误。
