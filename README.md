# fluent-cfd — ANSYS Fluent / PyFluent 智能体预设

通过本机 `ansys-fluent-mcp`（官方 `ansys/pyfluent-mcp`）驱动 ANSYS Fluent 的 DSH 智能体预设。包含：

- **`agent.cordis.yml`** — 智能体编排（persona + 工具 + Fluent MCP 执行层）。
- **`preset.yml`** — 预设元数据。
- **`skills/fluent-cfd/`** — Fluent CFD 判断层（工作流、湍流/边界、数值/收敛、PyFluent 执行、预处理计算、校验/恢复）+ 脚本（`solver_loop.py` 长跑驱动、`long_run.journal`、`preprocessing.py`）。

> 只有 **预设（判断层 + 执行层配置）** 会被安装。真正求解仍需要你本机装有 ANSYS Fluent + license。

---

## 1. 前置依赖（必须）

| 项 | 说明 |
|---|---|
| DSH（`.dsh`） | 已安装并可用（`~/.dsh/`，含 `agent-presets` 目录） |
| ANSYS Fluent | 建议 **2025 R2 / v25.2**（`agent.cordis.yml` 里 AWP root 指向它）+ 有效 **license** |
| Python 3.x | 装 `ansys-fluent-core`（PyFluent）+ `ansys-fluent-mcp`（用到 `ansys-fluent-mcp` 命令/`ansys-fluent-mcp.exe`） |

> 版本不匹配是常见坑：`pyfluent` 与 Fluent 发行版要对应（PyFluent 0.41 ↔ Fluent 25.2）。

---

## 2. 一键安装

### Windows（PowerShell）
```powershell
# 克隆后
git clone <你的仓库地址> fluent-cfd-deploy
cd fluent-cfd-deploy
.\install.ps1
```
脚本会自动：探测本机 python、`ansys-fluent-mcp`、Ansys 安装目录，把两个机器路径写进 `agent.cordis.yml`，并复制预设到 `%USERPROFILE%\.dsh\.agent-presets\fluent-cfd`。

### Linux / macOS（bash）
```bash
git clone <你的仓库地址> fluent-cfd-deploy
cd fluent-cfd-deploy
./install.sh
```

### 手动（不跑脚本）
1. 把 `fluent-cfd/` 整个拷到 `~/.dsh/.agent-presets/fluent-cfd/`。
2. 编辑 `agent.cordis.yml` 两处：
   ```yaml
   command: '<python的Scripts目录>\ansys-fluent-mcp.exe'   # 你本机的 mcp 可执行文件
   env:
     AWP_ROOT252: '<你的Ansys安装目录，如 D:\Program Files\ANSYS Inc\v252>'
     AWP_ROOT25:  '<同上>'
   ```

### 覆盖自动检测
设置环境变量（或安装脚本参数）即可跳过探测：
- `PYTHON` / `-p`：python 解释器路径
- `PYTHON_ANSYS_FLUENT_MCP`：`ansys-fluent-mcp` 完整路径
- `ANSYS_AWP_ROOT` / `-a`：Ansys 安装目录（如 `/opt/ansys_inc/v252`）

---

## 3. 使用

1. 在 DSH 里以 **`fluent-cfd`** 预设启动智能体（工具以 `mcp__fluent__*` 暴露）。
2. 智能体自带 `fluent-cfd` skill：先 `session_status`，再 `connect`（会占 license，会先告诉你），加载 case，短烟测，再决定长跑。

### 长跑（重要）
- **不要用 `run_code` 跑长迭代** —— 单次调用超时会杀掉会话（skill 里 `pyfluent-execution.md` 已写明）。
- 用后台脚本：
  ```bash
  python skills/fluent-cfd/scripts/solver_loop.py --case-dir <案例目录> --blocks 60 --iters-per-block 500
  ```
  - 默认弹出 Fluent GUI；`--no-gui` 无头；`--keep-open` 跑完后保留界面（自己关）。
  - 或用 `long_run.journal`：`fluent.exe 2ddp -t16 -i long_run.journal`。

---

## 4. 故障排查

- **`File has wrong dimensions (2)`**：case 是 2D，但会话是 3D。启动时用 `dimension=2`（`solver_loop.py` 已内置；MCP `connect` 用 `connect_kwargs={"dimension":2,...}`）。
- **PyFluent 找不到 Fluent**：`AWP_ROOT252`/`AWP_ROOT25` 没指向你的 v252。
- **`ansys-fluent-mcp` 命令不存在**：装 `ansys-fluent-mcp` 包，或把 `command` 指向实际路径。
- **license**：确认 license 服务已启动、可用。
- **长跑被断**：走了 `run_code` 长迭代 → 改用 `solver_loop.py` / `long_run.journal`（后台进程，无超时）。

---

## 5. 目录说明

```
fluent-cfd-deploy/
├── README.md
├── install.ps1 / install.sh        # 一键安装
├── fluent-cfd/                     # 预设模板（agent.cordis.yml 含 __占位符__）
│   ├── preset.yml
│   ├── agent.cordis.yml
│   └── skills/fluent-cfd/
│       ├── SKILL.md
│       ├── references/             # 6 个：workflow / boundaries-and-turbulence /
│       │                           #   numerics-and-convergence / pyfluent-execution /
│       │                           #   preprocessing-calculations / validation-and-recovery
│       └── scripts/                # solver_loop.py / long_run.journal / preprocessing.py
└── LICENSE
```
