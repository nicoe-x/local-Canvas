# Local Canvas

一个接 ComfyUI 的自部署创作画布。

我想把图片、视频和提示词放在同一张画布上，能拖线引用素材，也能按项目分开整理，所以做了这个项目。生成任务发给自己的 ComfyUI，画布和作品存在部署工作台的电脑或服务器上。

目前已经能用来做图片、视频节点的生成和素材引用。还有一些功能没接完，下面会写清楚。

[下载](https://github.com/nicoe-x/local-Canvas/releases/latest) · [更新记录](https://github.com/nicoe-x/local-Canvas/releases) · [提问题](https://github.com/nicoe-x/local-Canvas/issues)

## 先跑起来

需要 Python 3.11 以上，以及一个能正常访问的 ComfyUI。ComfyUI 可以和工作台装在同一台机器，也可以放在局域网的另一台机器上。

从 [Releases](https://github.com/nicoe-x/local-Canvas/releases/latest) 下载部署包，解压后打开所在目录。

Windows 用 PowerShell 运行：

```powershell
.\start.ps1
```

如果脚本被执行策略拦住，用下面这条：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Linux / macOS：

```sh
sh start.sh
```

第一次启动会创建虚拟环境、安装依赖，需要联网。启动后打开 http://127.0.0.1:8848 。

页面会让你创建账号。初始化令牌在启动终端里，也可以从 `studio-data/setup-token` 文件读取。账号建好后，这个文件会删除。密码由你自己设置。

要用视频封面、音轨导出等工具，还需要安装 FFmpeg，并把它加到 `PATH`。

也可以克隆源码，再运行上面的启动脚本：

```sh
git clone https://github.com/nicoe-x/local-Canvas.git
cd local-Canvas
```

## 接上 ComfyUI

第一次启动时会扫描本机的 `8188`、`8189`、`8190`、`8191` 端口。找到一个可直接使用的实例会自动连接，找到多个就需要自己选。扫描过程不会跑生成任务。

没找到的话，进入「ComfyUI 连接」，手动填写地址，例如 `http://127.0.0.1:8188`。目前地址要填服务根地址，不支持在后面加子路径。

有认证的服务可以填 Basic、Bearer 或私有令牌头；自签名 HTTPS 需要在页面里调整 TLS 设置。局域网扫描要自己填写网段和端口，单次最多扫一个 `/24`。如果连不上，先检查 ComfyUI 的监听地址、端口和防火墙。

## 导入工作流

先在 ComfyUI 里把工作流跑通，再导入这里，排错会方便一些。模型和自定义节点也需要提前装在 ComfyUI 上。

导入的是 **API 格式 JSON**，不是普通的 `nodes/links` 画布文件。工作台里选的「模型」实际是一套工作流，具体加载哪个模型由这套工作流决定。

常见的提示词、采样步数、CFG、尺寸和参考图输入会尝试自动识别。特殊节点识别不了，就手动填绑定。比如：

```json
{
  "positive": [{"node": "6", "input": "text"}],
  "seed": [{"node": "3", "input": "seed"}],
  "steps": [{"node": "3", "input": "steps"}],
  "cfg": [{"node": "3", "input": "cfg"}],
  "reference_images": [{"node": "10", "input": "image"}]
}
```

这里的编号和字段名只是示例，要换成自己工作流里的值。参考图按 `reference_images` 的顺序传入，张数也要对应。视频的帧率、帧数对齐需要在工作流配置里写明。

如果服务里有基础节点和 checkpoint，程序会尝试建一个普通文生图模板。H3、Qwen、Z-Image 等工作流仍需要自己导入和确认绑定。

## 画布怎么用

双击空白处添加节点。图片、视频、文本和素材可以放在一起，通过连线传给下一个节点。不同项目可以建不同的画布。

选中节点后，在输入框里写提示词、选工作流和参数。输入框会跟着节点走，缩放画布时大小保持不变；内容多的时候可以展开编辑。

引用图片可以直接连线、点击「画布点选」，或者在提示词中输入 `@`。`@` 菜单默认只显示当前节点已经连接的素材，搜索和「素材引用」分类里才能看到画布上的其他素材。

引用跟着具体的来源节点，改名字不会串图。把来源断开或删掉后，没清理的引用会报错，需要重新选择。

常用操作：

- 左键拖动节点；在空白处拖动可以框选。
- 中键拖动或按住 Space 拖动，平移画布。
- 普通滚轮上下移动，Ctrl + 滚轮缩放。
- 双击节点名称改名，多选后可以分组或批量下载。
- 在输入框中按 Ctrl + Enter，运行当前节点。
- Delete 将选中节点移入回收站。
- 点击空白处关闭引用菜单，点击遮罩空白处关闭放大编辑框。

当前单个视频片段是 4–15 秒。手动生成没有次数限制，同一个节点还在处理时会拦住重复提交。

连接了参考图，也要选支持图片输入的工作流。参考图要在 ComfyUI 工作流里实际接入，画布连线负责把图片传过去。

## Docker

在仓库根目录或部署包解压目录运行：

```sh
docker compose up -d --build
docker compose logs studio
```

默认映射到 `127.0.0.1:8848`，数据存在 `studio-data` 命名卷里。容器内的 `127.0.0.1` 是容器自己，连接宿主机 ComfyUI 时可以用 `host.docker.internal`，前提是 ComfyUI 监听了容器能访问的地址。

Docker 配置已经放进仓库，目前还没做容器构建实测。原生 Python 安装已经验证过。

## 数据和任务

直接运行时，默认数据目录是 `studio-data`：

```text
studio-data/
├── studio.sqlite3       # 账号、会话、任务、工作流
├── canvases.sqlite3     # 项目、画布、连线、回收站
├── settings.json        # ComfyUI 地址和认证配置
├── materials/canvas/    # 上传的素材
├── jobs/<owner>/<id>/   # 下载回来的生成结果
└── assets/three/        # 按需安装的 3D 运行库
```

升级时保留这个目录，备份时也要一起备份。里面有账号信息、连接凭据和作品，不要传到公开仓库。

要改端口、监听地址或保存位置，可以手动启动：

```sh
open-comfy-studio --host 0.0.0.0 --port 8848 --data /path/to/studio-data
```

也可以设置 `OPEN_STUDIO_HOST`、`OPEN_STUDIO_PORT`、`OPEN_STUDIO_DATA`。

任务会记住提交时的工作流和连接。中途换了服务，已经提交的任务还是去原来的服务核对。遇到「结果待核对」，先用页面上的核对按钮查原任务，程序不会自动再提交一遍。

本地队列顺序提交，实际执行还是由 ComfyUI 排队。这里只能取消还没开始的本地任务，不会调用共享 ComfyUI 的全局中断。生成完成会标成 `COMPLETED_UNREVIEWED`，意思是生成完了，还没审片。

回收站里的彻底删除会清理工作台管理的本地文件，有其他画布还在引用时会拦住。ComfyUI 自己保存的 `input/output` 副本需要在那台设备上管理。共享 ComfyUI 的输出是否对其他人可见，也由那边的服务决定。

## 还没做完的地方

图片反推需要另外配置服务：`STUDIO_VISION_URL` 填 OpenAI 兼容的 `/v1` 地址，`STUDIO_VISION_MODEL` 填模型，需要密钥时再填 `STUDIO_VISION_KEY`。只有点反推时才会把图片发过去。

双击空白处选择 **H3 提示词节点**，会添加独立的转换节点。选中节点，在下方输入原文、选择风格和总时长，也可以连入已有文本与参考图片。转换结果和原文保存在节点里，刷新后仍在；多段结果可选择当前输出，拖出右侧连接点传给视频节点。单段可直接创建相连的视频节点，多段也能逐段创建文本快照和视频节点，视频仍要手动启动。

改动原文或参数后，旧输出会清空，必须重新转换。上游文字、参考图顺序或下游时长与结果不匹配时，后端也会拦住提交，避免把旧提示词或整段剧本误送给 H3。

转换需要文本模型：`STUDIO_TEXT_URL` 填 OpenAI 兼容的 `/v1` 地址，`STUDIO_TEXT_MODEL` 填本地 Qwen 等模型名；有认证时填 `STUDIO_TEXT_KEY`。想让剧本留在本地，就填写本地服务地址。程序不自带文本模型，也不会自动切到云端。原文和已连接图片的名称会发给这个服务，图片本身不会发送，外观细节需要自己核对。

总时长支持 4–90 秒，超过 15 秒会拆成多个独立片段，每段都是完整 H3 提示词。没有参考图片用三字段 T2VA，有参考图片用六字段 Ref2VA。默认关闭背景音乐和字幕，检查字段顺序、镜头切点、参考编号和台词容量；中文引号或 `「」` 内的台词还会逐句核对是否遗漏、改写或重复。其他格式的对白只能检查输出是否出自原文，请自行核对是否漏句。格式通过不代表剧情、人物或生成画面已经通过审查。

3D 导演台用的是 Three.js，部署包里带了运行库。如果资源缺了，可以执行：

```sh
open-comfy-studio assets --data ./studio-data
```

视频和音频素材作为生成输入还没接。图层分离、全景、动作捕捉、完整 AI 审片和专用视频超分也还需要各自的适配器，暂时不能当成已完成的功能用。账号目前只有初始化管理员，用户管理界面还没做。

遇到问题可以提 [Issue](https://github.com/nicoe-x/local-Canvas/issues)，带上错误提示、工作流类型和复现步骤。发配置文件前记得去掉密钥和私人素材。

## 开发

安装依赖后跑测试：

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s tests/canvas -v
```

打部署包：

```sh
python scripts/build_release.py --output ./dist/open-comfy-studio.zip
```

构建脚本只打包白名单里的代码和资源，并生成 `MANIFEST.sha256.json`。测试过哪些、哪些还没测，记录在 [VALIDATION.md](VALIDATION.md)。

## 许可证

应用代码是 [Apache-2.0](LICENSE)。Three.js 保留 MIT 协议。ComfyUI、模型和自定义节点用各自的许可证，见 [NOTICE](NOTICE)。仓库不带模型权重、私人配置或生成作品。

H3 节点的“复制完整提示词”复制当前片段全文，预览区也可选中文字。拖动连接线时编辑区会隐藏；需要编辑时点“编辑 / 转换”。

视频节点可直接写 `@参考图1`、`@参考图2`。提交时按实际连线顺序转换成 H3 标签，并将普通描述或旧三字段模板包装成参考模式所需字段；不调用文本 API，不改原文台词。完整六字段模板保持原样。
