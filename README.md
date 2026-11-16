# Local Canvas

**把 ComfyUI 工作流变成可连接、可复用的创作画布。**

Local Canvas 是一个可独立部署的图片与视频创作工作台。你可以按项目组织画布，通过节点编写提示词、引用素材、选择工作流并生成内容；模型推理交给你连接的 ComfyUI 执行。

[下载部署包](https://github.com/nicoe-x/local-Canvas/releases/latest) · [查看版本](https://github.com/nicoe-x/local-Canvas/releases) · [反馈问题](https://github.com/nicoe-x/local-Canvas/issues) · [Apache-2.0](LICENSE)

## 功能一览

| 功能 | 当前能力 |
| --- | --- |
| 项目画布 | 按项目组织，拖动节点、连线、框选、多选和分组 |
| 创作节点 | 图片、视频、文本、参考素材、图片反推与 3D 导演台 |
| 参考图引用 | 连线、`@` 搜索、分类选择、画布直接点选 |
| 节点编辑器 | 提示词与参数共用一个编辑器，跟随节点移动，支持放大编辑 |
| ComfyUI 连接 | 本机自动发现、指定局域网扫描、手动地址与认证 |
| 工作流导入 | 导入 API 格式 JSON，绑定提示词、采样参数和参考图 |
| 任务与结果 | 生成进度、后台排队、结果下载、提交结果核对 |
| 素材管理 | 本地保存、回收站、恢复、选中素材批量下载 |

图片编辑、视频生成等能力取决于所选工作流、模型和 ComfyUI 节点。仓库不附带模型权重，也不会自动安装模型或自定义节点。

## 开始使用

### 1. 准备环境

- **Python 3.11 或更新版本**：运行工作台。
- **可访问的 ComfyUI**：可以在同一台电脑，也可以在局域网另一台设备。
- **FFmpeg（按需）**：视频封面、音轨导出等本地视频工具需要它，并要求命令位于 `PATH` 中。

工作台本身不要求显卡。显存、模型及推理环境由 ComfyUI 所在设备提供。首次启动脚本会联网安装 Python 依赖。

### 2. 下载并启动

从 [Releases](https://github.com/nicoe-x/local-Canvas/releases/latest) 下载 `open-comfy-studio-*.zip`，解压后进入包含 `start.ps1`、`start.sh` 的目录。

**Windows / PowerShell**

```powershell
.\start.ps1
```

如果执行策略阻止运行脚本，可在当前操作中运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

**Linux / macOS**

```sh
sh start.sh
```

打开 **http://127.0.0.1:8848**。

### 3. 初始化并连接

1. 从启动终端或 `studio-data/setup-token` 读取一次性初始化令牌。
2. 在页面中创建工作空间管理员账号和密码。初始化完成后令牌文件会删除。
3. 进入 **ComfyUI 连接**，选择发现的实例，或手动填写地址。
4. 进入 **工作流**，导入已经在 ComfyUI 中跑通的 API 格式 JSON。
5. 打开 **创作画布**，添加节点、填写提示词，选择工作流后生成。

没有预设的通用管理员密码。

## 使用画布

### 节点与参考素材

双击画布空白处添加节点，或上传素材、从生成历史中选择已有作品。节点之间通过连线传递提示词和参考图片。

在提示词中输入 `@`，或点击 **画布参考**：

- 默认仅显示当前节点**已经连接的素材**。
- 输入搜索词可搜索当前画布素材。
- 进入“素材引用”分类后，在子菜单选择其他素材。
- 点击 **画布点选** 后，可直接点击画布上的图片作为参考。

图片引用绑定来源节点，改名不会改变引用对象。来源被删除或断开时，仍存在的引用会阻止提交。未完成或不支持的素材不能当作有效图片输入。

### 常用操作

| 操作 | 方式 |
| --- | --- |
| 添加节点 | 双击画布空白处 |
| 移动节点 | 左键拖动节点可拖动区域 |
| 平移画布 | 鼠标中键拖动，或按住 Space 拖动 |
| 上下移动画布 | 普通滚轮 |
| 缩放画布 | Ctrl + 滚轮 |
| 多选 | 在空白处左键框选 |
| 重命名节点 | 双击节点名称 |
| 运行当前节点 | 编辑器中 Ctrl + Enter |
| 移除选中节点 | Delete，移入回收站 |
| 关闭浮层 | Esc，或点击浮层外空白处 |

普通编辑框跟随选中节点移动，优先位于节点下方；靠近窗口边缘时自动避让。画布缩放不会改变编辑框自身大小。放大编辑框可点击遮罩空白处关闭。

## ComfyUI 连接方式

### 自动发现

首次启动且尚未配置连接时，探测本机 `8188`、`8189`、`8190`、`8191` 端口，并通过 `/system_stats` 与 `/object_info` 验证服务。

- 只发现一个无需认证的可用实例：自动连接。
- 发现多个实例：由你选择。
- 需要认证的实例：填写认证信息后连接。

扫描不会提交生成任务。

### 手动连接与局域网扫描

在连接页面填写 `http://主机:端口` 或 `https://主机:端口`。当前连接地址需要使用服务根路径。

支持 HTTP Basic、Bearer Token 和指定的私有令牌头。自签名 HTTPS 需要显式选择相应 TLS 设置。认证信息保存在服务端，设置查询接口不返回密钥。

局域网扫描由用户指定私有 CIDR 与端口，单次网段范围最多 `/24`。服务需要可达，且防火墙允许访问。

## 导入工作流

### 导入什么文件

使用 **ComfyUI 导出的 API 格式 JSON**。普通画布的 `nodes/links` JSON 不会自动转换为可执行工作流。

工作台中的模型选择项实际对应一个已导入的工作流；使用哪个模型、加载哪些节点，由工作流决定。

当基础节点和 checkpoint 可用时，应用会尝试建立一个普通文生图模板。MiniMax H3、Qwen、Z-Image 等特殊工作流，需要先在 ComfyUI 中验证，再导入工作台。

### 参数绑定

程序可以识别部分常见输入，例如 `KSampler`、`CLIPTextEncode`、latent 尺寸及 `LoadImage`。无法识别的自定义节点需要手动填写绑定。

下面是绑定格式示例，节点编号和输入名称必须替换成你自己的工作流内容：

```json
{
  "positive": [{"node": "6", "input": "text"}],
  "negative": [{"node": "7", "input": "text"}],
  "seed": [{"node": "3", "input": "seed"}],
  "steps": [{"node": "3", "input": "steps"}],
  "cfg": [{"node": "3", "input": "cfg"}],
  "reference_images": [{"node": "10", "input": "image"}]
}
```

只有绑定的参数会写入工作流。参考图片按绑定数组顺序传入，数量必须匹配。视频帧率、帧数对齐倍数和偏移需要明确配置。

当前画布单分镜时长范围为 **4–15 秒**。手动生成次数不限；同一节点有未结束的任务时会阻止重复提交。

## 其他部署方式

### 从源码启动

```sh
git clone https://github.com/nicoe-x/local-Canvas.git
cd local-Canvas
```

然后运行当前系统对应的启动脚本，或手动安装：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -c requirements-tested.txt .
.venv/bin/open-comfy-studio --data ./studio-data
```

Windows 手动安装时使用 `.venv\Scripts\python.exe` 和 `.venv\Scripts\open-comfy-studio.exe`。

### Docker Compose

在仓库根目录或部署包解压目录执行：

```sh
docker compose up -d --build
docker compose logs studio
```

默认发布地址为 `127.0.0.1:8848`，数据保存在命名卷 `studio-data`。

容器中的 `127.0.0.1` 指容器本身。连接宿主机 ComfyUI 时，可使用 `host.docker.internal`；宿主 ComfyUI 必须监听容器能够访问的地址。也可以手动连接局域网中的其他设备。

已提供 Dockerfile 和 Compose 配置；当前发布版本的 Docker 容器构建尚未在本机实测，原生 Python 安装已验证。

### 自定义监听与数据目录

```sh
open-comfy-studio --host 0.0.0.0 --port 8848 --data /path/to/studio-data
```

命令参数也可通过 `OPEN_STUDIO_HOST`、`OPEN_STUDIO_PORT`、`OPEN_STUDIO_DATA` 设置。跨设备访问前，请按部署环境配置网络访问范围和入口。

## 数据保存与任务行为

```text
studio-data/
├── studio.sqlite3       # 账号、会话、任务和工作流
├── canvases.sqlite3     # 项目、画布、连线和回收站
├── settings.json        # ComfyUI 地址与认证配置
├── materials/canvas/    # 上传素材和派生图片
├── jobs/<owner>/<id>/   # 下载的生成结果和参考图片
└── assets/three/        # 按需安装的 3D 运行库
```

更新应用时保留整个数据目录。备份中包含账号信息、连接配置和作品，应按私人数据保存。

任务会保存提交时的工作流与连接快照。切换连接不会把已提交的任务改投到另一个服务。提交结果不确定时，使用 **核对后台结果** 查找原任务；程序不会自动重复提交。

工作空间按本地队列顺序提交任务，最终执行由 ComfyUI 队列负责。仅支持取消尚未开始的本地排队任务，运行中的任务不会调用共享 ComfyUI 的全局中断接口。

生成结果标记为 `COMPLETED_UNREVIEWED`，表示生成完成、尚未经内容审查。

### 删除范围

移除节点后进入回收站。彻底删除会清理本工作空间管理的文件；存在其他画布引用时会阻止误删。

ComfyUI 自己的 `input/output` 文件由 ComfyUI 所在设备管理。工作台本地删除不会自动删除远端副本；连接共享 ComfyUI 时，其输出可见性也由该服务控制。

## 可选能力与当前边界

- **3D 导演台**：发布包包含固定版本 Three.js；缺少资源时可执行 `open-comfy-studio assets --data ./studio-data` 下载并验证运行库。
- **图片反推**：配置 `STUDIO_VISION_URL`、`STUDIO_VISION_MODEL`，需要认证时再配置 `STUDIO_VISION_KEY`。地址为 OpenAI 兼容的 `/v1` 服务入口，只有主动执行反推才发送图片。
- **视频与音频参考**：当前未接入视频、音频素材作为生成输入，相关入口会显示禁用原因或空状态。
- **高级处理**：图层分离、720°全景、深度动作捕捉、完整 AI 审片和专用视频超分需要额外适配器，目前未作为完整能力交付。
- **账号管理**：首次运行创建工作空间管理员，暂未提供完整的用户管理界面。

## 常见问题

**扫描不到 ComfyUI？** 先确认服务已启动、端口正确，并检查监听地址和防火墙。Docker 用户还需区分容器地址与宿主机地址，也可直接手动连接。

**能连接但无法生成？** 检查导入的是否为 API 格式、节点和模型是否已安装、参数绑定是否正确，以及参考图数量是否匹配。具体节点执行错误需到 ComfyUI 查看。

**连接了图片却没有参考效果？** 所选工作流必须实际支持图片输入。把图片连到纯文生图工作流，不会自动获得参考图编辑能力。

**模型列表有了，为什么还要导入工作流？** 模型列表来自服务元数据；一次生成还需要完整的节点连接、采样配置和输入绑定。

## 开发与发布

安装依赖后执行：

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s tests/canvas -v
```

构建带完整性清单的部署包：

```sh
python scripts/build_release.py --output ./dist/open-comfy-studio.zip
```

构建器按白名单收集代码、静态资源和已校验运行库，生成 `MANIFEST.sha256.json`。验证范围、已测项目和未实测项见 [VALIDATION.md](VALIDATION.md)。

## 开源协议

应用代码使用 [Apache License 2.0](LICENSE)。Three.js 保留 MIT 许可证；ComfyUI、模型权重和自定义节点继续适用各自许可证，详见 [NOTICE](NOTICE)。

仓库和部署包不包含私人账号、连接配置、数据库、模型权重或生成作品。
