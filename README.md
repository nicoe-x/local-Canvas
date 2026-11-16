# Local Canvas · Open Comfy Studio

独立部署的 ComfyUI 创作画布与工作空间。复用现有无限画布体验，将账号、存储、队列、模型路径和服务器地址从私人部署中分离。

[下载部署包](https://github.com/nicoe-x/local-Canvas/releases/latest) · [全部版本](https://github.com/nicoe-x/local-Canvas/releases)

## 快速启动

需要 Python 3.11+。图片生成不要求工作空间设备有显卡；显卡与模型由连接的 ComfyUI 提供。视频截图、音轨导出等本地视频工具需要 FFmpeg。

下载独立发布 ZIP 后解压，运行：

```powershell
# Windows，首次启动会建立虚拟环境并安装依赖
.\start.ps1
```

```sh
# Linux / macOS
sh start.sh
```

打开 `http://127.0.0.1:8848`。从启动终端或 `studio-data/setup-token` 获取一次性初始化令牌，创建自己的账号密码。初始化后令牌删除，没有固定管理员密码。

从源码仓库运行（不需要原项目仓库）：

```sh
git clone https://github.com/nicoe-x/local-Canvas.git
cd local-Canvas
python -m venv .venv
# Windows 使用 .venv/Scripts/python；以下为 Linux/macOS
.venv/bin/python -m pip install -c requirements-tested.txt .
.venv/bin/open-comfy-studio --data ./studio-data
```

## Docker

发布 ZIP 目录内可直接运行：

```sh
docker compose up -d --build
docker compose logs studio
```

从完整源码仓库运行：

```sh
docker compose up -d --build
```

账号、设置、作品和画布保存在命名卷 `studio-data`，更新镜像不会清空它。默认端口只发布到宿主机回环地址；需要局域网访问时，调整 compose 的端口映射并配置你的 HTTPS 反向代理。没有要求下载 NVIDIA CUDA 镜像或占用第二份模型显存。

Docker 内的 `127.0.0.1` 指容器本身；应用也会尝试 `host.docker.internal`。宿主 ComfyUI 必须监听 Docker 容器可访问的地址，或手动连接另一台局域网设备上的 ComfyUI。应用不能跨过防火墙、猜测认证密码或自动安装缺失节点。

## 自动发现与连接

1. 启动时探测本机常用端口 8188、8189、8190、8191，通过 `/system_stats` 与 `/object_info` 双重验证服务。
2. 仅找到一个无需认证的可用实例时自动连接；多个实例保留列表，由用户选择。
3. 在“ComfyUI 连接”中可指定私有局域网 CIDR（最大 /24）与端口，或手动填写地址。
4. 支持 HTTP Basic、Bearer Token、私有令牌头及明确选择的自签名 HTTPS。认证头只存服务器设置文件，读取 API 不返回密钥。
5. 连接后读取节点定义、checkpoint、UNet、CLIP、VAE、LoRA 选项。不会自动下载任何模型。

接口依据 [ComfyUI 官方服务器路由文档](https://github.com/Comfy-Org/docs/blob/main/development/comfyui-server/comms_routes.mdx)。扫描不会触发 `/prompt`，不会执行生成、安装节点或改动 ComfyUI 文件。

## 工作流与模型

模型选择实际选择的是已配置的 **API 工作流**，工作流再决定使用哪些模型。标准 checkpoint 与基础节点存在时，应用可自动建立普通文生图模板。H3、Z-Image、Qwen、自定义采样等请导入你已经在 ComfyUI 验证过的 API 格式工作流。

在 ComfyUI 导出 API 格式 JSON，在工作空间填写名称、图片/视频类型并导入。常见 `KSampler`、`CLIPTextEncode`、latent 尺寸、`LoadImage` 会自动识别；自定义节点需显式声明语义绑定，不能保证任意图都可无配置识别。

```json
{
  "positive": [{"node": "6", "input": "text"}],
  "negative": [{"node": "7", "input": "text"}],
  "seed": [{"node": "3", "input": "seed"}],
  "steps": [{"node": "3", "input": "steps"}],
  "reference_images": [{"node": "10", "input": "image"}]
}
```

画布中输入 `@` 或点击“画布参考”，默认只显示当前节点已连接的素材。使用搜索框可查找当前画布素材，或从“素材引用”分类进入右侧列表；“画布点选”可以直接选图。已连接的参考图可反复插入提示词；引用绑定具体来源，断开后会阻止误用。

只有绑定的参数会被写入图。参考图片严格按绑定数组顺序传递，数量不匹配不提交。视频帧率、帧数对齐倍数/偏移在配置中明确填写；应用不猜测 H3 或其他模型的帧数规范。画布单分镜保持4–15秒，手动生成次数不限。

## 数据与任务

```text
studio-data/
  studio.sqlite3       # 账号密码哈希、会话、任务、工作流
  canvases.sqlite3     # 项目、画布、连线、回收站
  settings.json        # 连接地址与认证，文件权限600（支持的平台）
  materials/canvas/    # 上传素材与派生图片
  jobs/<owner>/<id>/   # 本工作空间下载的生成结果、参考图
  assets/three/        # 可选的固定版本3D运行库
```

所有者、任务优先级、输出路径由服务器确定，前端不能指定目录。ComfyUI 的任务 ID 与本地任务绑定，输出下载后保存在本工作空间。任务保存提交时的工作流与连接快照，后续切换服务不会把旧任务指向新服务。未知提交结果进入 `NEEDS_ATTENTION`，通过“核对后台结果”查找原任务，不会自动重复POST。

单工作空间进程顺序调度；ComfyUI 自己继续处理其他客户端的队列。取消仅支持尚未开始的本地排队任务，运行中的共享 ComfyUI 不调用全局 interrupt。生成结果始终为 `COMPLETED_UNREVIEWED`，不冒充已经审片。

回收站彻底删除会删除本工作空间的文件，存在其他画布引用时阻止误删。**ComfyUI 服务器自己的 output/input 目录不由普通客户端删除**，需通过 ComfyUI 或部署者自己的保留策略管理。不会让客户端拿任意远程路径进行删除。

## 可选功能

- 3D 导演台：包含3D资源的发布包可直接使用；纯源码安装可执行 `open-comfy-studio assets --data ./studio-data`，下载并验证固定版本 Three.js（MIT），不是模型下载。
- 图片反推：配置 `STUDIO_VISION_URL`（OpenAI兼容 `/v1` 地址）、`STUDIO_VISION_MODEL`，需要认证时配置 `STUDIO_VISION_KEY`。只有用户点击反推才会发送图片。
- 图层分离、720°全景、深度动作捕捉、完整AI审片和专用视频超分需额外适配器，当前不假装已安装；没有配置时显示说明或返回明确错误。
- 现有生产服务器的私有 SSH 网关、自动归档、OA身份和GPU文件锁不移植为开源版的隐式依赖。ComfyUI 本身负责显存与执行队列。

## 构建独立发布包

```sh
python scripts/build_release.py --output ./dist/open-comfy-studio-0.1.3.zip
```

构建器仅收集白名单源码、静态文件、文档和已校验3D库，生成 `MANIFEST.sha256.json`。不复制 `.env`、数据库、私人账号、连接设置、模型、SSH密钥、日志、缓存和已生成媒体，也不要求发布整个历史仓库。

## 开发与验证

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s tests/canvas -v
```

服务发现、端口认证、API工作流绑定、队列输出、提交不确定性、配置快照、密钥脱敏和本地回收站均有隔离测试。真实ComfyUI服务可进行只读连接检查；不把模拟生成测试描述为真实模型生成效果。

具体测试范围与未实测项见 [验证记录](VALIDATION.md)。

本包应用代码使用 [Apache-2.0](LICENSE)。模型、ComfyUI、自定义节点和可选运行库仍使用各自许可证，详见 [NOTICE](NOTICE)。本仓库仅包含独立版应用源码及声明过的运行库，不含原项目历史、私人部署配置或模型权重。
