# 0.1.0 验证记录

验证日期：2026-11-16。以下结论仅适用于这次提交与构建出的独立包。

- 独立服务测试：14 项通过，覆盖认证/CSRF、服务识别、指定网段限制、工作流参数绑定、连接与工作流快照、提交结果不确定性、本地回收站和发布包白名单。
- 原画布回归：105 项通过。共享代码只增加静态目录与本地删除适配注入点，默认行为不变。
- 独立发布包从 ZIP 解压后，在单独虚拟环境构建并安装 wheel；资源实际从 site-packages 读取，不依赖原仓库路径。
- Edge 浏览器端到端：登录、自动连接、模型/节点扫描、工作台生成、导入画布、参数保留、画布生成、WebSocket 采样进度和刷新后数据保留通过；无 JavaScript 页面错误。
- 发布包内 Three.js 运行库通过固定哈希校验，浏览器软件 WebGL 下三维摆位界面与构图导出通过。
- 生成链路使用隔离的 CPU 图片返回服务，不占用生产 GPU；这不证明任意实际模型或自定义工作流的生成效果。
- 对现有认证 ComfyUI 实例进行只读连接检查，识别 2359 个节点和 64 个模型选项；没有提交生成任务。
- ZIP 包逐文件核对 SHA-256，并检查不含连接凭据、私人地址、数据库、模型和生成媒体。

## 未实测与限制

- 当前验证机器没有 Docker，未实测容器构建；已提供 Dockerfile、Compose 和健康检查。原生独立安装已实测。
- 特殊 H3 / Qwen / Z-Image 工作流需用户导入 API 格式 JSON 并确认语义参数绑定；不自动安装模型、节点或转换任意画布 JSON。
- 尚未运行真实 GPU 视频生产、专用超分、完整 AI 审片或外部收费处理服务。
- 既有公共与私人服务没有因本次开发重启、替换或迁移。测试服务运行于隔离的本机端口，测试后关闭。


## 0.1.1 参考图引用修复

增加 `@` 候选、键盘选择、缩略图选择与画布直接点选，支持放大编辑器。引用通过节点 ID 持久化，提交时才换算实际传图序号；删除/断线后失效引用阻止提交。

新增路由测试覆盖上传顺序与别名顺序不同、同名来源、断开来源与未知引用；共享画布回归共119项通过。Edge 隔离测试通过键盘 @ 选择、点击缩略图、直接点选不移动节点/不改变目标、不重复连线、放大编辑器、改名保留引用、失效422与实际提交顺序。生成仅使用CPU返回图片服务，无GPU任务。


## 0.1.2 引用菜单交互

默认仅列当前节点已连接素材，搜索与分类列表才显示画布其他素材。使用紧凑浅色双层菜单、搜索框和已连接素材编号缩略图。支持文本源连线合并，不支持的视频参考明确禁用，未有音频输入时显示空状态。

隔离 Edge 测试通过默认范围、搜索跨节点、右侧分类、文本引用、无重复ID、浅色紧凑浮层、放大编辑器、键盘导航和480px窄屏边界检查。测试不提交生成任务。共享画布119项与独立服务14项回归测试通过。


## 0.1.3 输入框跟随与空白关闭

普通编辑框按节点屏幕位置定位，优先下方、边界避让；跟随拖动和平移，缩放不改变自身尺寸。引用菜单点击空白关闭，放大编辑框可点击遮罩空白关闭，拖选文字到外面不会误关。取消了因编辑框尺寸导致的自动缩放/平移画布。

隔离 Edge 测试通过拖动/平移跟随、缩放尺寸稳定、切换节点重新定位、两类空白关闭、拖选保护和窄屏边界；引用菜单上一版的范围、分类、搜索和键盘回归同样通过。共享画布119项测试通过。测试不提交生成任务。


## 独立 GitHub 仓库初始化

2026-11-16：从独立部署包整理为可直接克隆的源码仓库，更新根目录安装说明、独立构建脚本和测试路径。独立服务14项测试与画布118项测试通过；排除了仅用于原项目页面打补丁的1项迁移测试。无生产账号、私人地址、密钥、数据库、模型或生成媒体进入仓库。GitHub Actions提供Python 3.11/3.13自动测试。
# H3 prompt conversion

- Added authenticated, CSRF-protected `/api/prompts/h3`; configuration stays server-side. No ComfyUI submission or video job is created by conversion.
- Tested contiguous duration budgeting for every integer from 4 to 90, template sections/order, reference bounds, cut timing, quoted dialogue preservation, and rejection of invented speech/music.
- Browser fixture: 30-second source produces two editable 15-second outputs; adding an output creates connected text/video nodes, persists original source after reload, and leaves the video job count at zero. No browser JavaScript errors.
- Local tests use an OpenAI-compatible CPU fixture. They verify integration and rejection behavior, not a language model's creative quality or the quality of generated video. Text/image generation remains separate.
- Final local suite: 25 application/format tests and 118 canvas tests passed. Structured H3 video prompts retain their first official field when a visual style is selected.
- Private installation: a five-second T2VA request ran on the existing local Qwen3.6-27B and returned valid fields in 45.6 seconds. A reference/dialogue request returned six fields with verbatim Chinese speech after wrapper normalization. Follow-up speaker-ID enforcement has unit coverage; its next real-model check was deferred because the shared GPU was busy (409, no preemption). No generated video quality claim is made.

## Native H3 node follow-up

- `h3prompt` is now a distinct canvas kind. Original source/settings and all converted segments persist separately from the selected output text. Input changes invalidate the output. The editor is anchored under/above its node rather than a modal.
- Backend tests verify native-node roundtrip and selected-prompt submission, and rejection of incomplete conversions, stale upstream text and duration mismatches. No GPU job was executed by these tests.
- Local browser fixture covers persistent multiple outputs, selection after reload, editor placement without covering the node, invalidation, and direct native-node-to-video links.
- The private installation passed a browser acceptance test using a mocked text completion: native node save/reload and direct video connection, no JavaScript errors, no video submitted. Temporary test canvases were isolated from user work. The local Qwen adapter was not changed or run again for this UI follow-up.

## H3 copy and wiring interaction fix

Browser CPU fixture verified: opening the editor then dragging the output port hides both composers; releasing the wire does not reopen the H3 editor; clicking Edit explicitly reopens it. Clipboard tests compared the full output (longer than the 420-character preview) with the system clipboard, including a rejected Clipboard API followed by the legacy copy fallback. Drag-selecting preview text produced a nonempty selection and did not change node coordinates. No model or video jobs were submitted; no JavaScript errors.

## Direct @ reference submission

The existing alias resolver still binds aliases by node ID and actual upload order. Video submission now frames ordinary text or a complete legacy T2VA document as Ref2VA when images are connected, preserving authored dialogue/actions/sound/music and inserting Shot 1 when missing. Complete six-field documents remain unchanged. Partial templates and out-of-range picture tags are rejected. Existing 26 application tests and 118 canvas tests passed; three additional compiler tests passed. The previously rejected private video node passed the real creative_segments preflight with its current text and two references; no video was submitted or evaluated.

## Automatic text processing before H3 submission

27 application tests and 121 canvas tests passed. The application integration test uses a mock OpenAI-compatible completion and verifies plain video text is converted before the recorded job is created, the stored text is the compiled H3 document, replaying the submission token does not call the text service again, and invalid model output creates no additional job. Existing native H3 documents bypass conversion. No real video was generated by these tests.

Private local-model smoke: a seven-second courtyard description with two picture references returned a valid six-field Ref2VA document from Qwen3.6-27B in 80.4 seconds, with no browser errors. This smoke exercised the same registered preparation callback via its text endpoint; integration coverage of the automatic video submission uses a mocked completion. No real video was submitted.
