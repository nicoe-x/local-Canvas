# H3 生成后的小脸修复

这是现有私人 H3 gateway 的适配代码，不是通用 ComfyUI 插件。独立部署包默认不显示这个开关；单独复制这两个文件到普通 ComfyUI 不会生效。

画布视频节点的「画面参数 → 生成后处理」可开启「小脸局部修复」。生成、拼接完成后，gateway 在原有 GPU 调度锁内运行人脸检测、跟踪裁剪、H3 局部重绘、合成，再按需超分。关闭超分也能修复；两者同时开启时只修复一次。生成结果仍为 `COMPLETED_UNREVIEWED`。

可以从当前节点已经连接的图片中选择人物参考。后端按实际上传顺序生成 `face_reference_index`，不接受文件路径。参考图断开后会拦住提交。修复时提取参考图中最大的脸：适合单个人物的四视图，不适合混有多个人的大合照。没有选参考时沿用视频自身的脸；已经严重变形时，这种方式通常不够。

目前只处理 24fps、写实、单人、可稳定检测的小脸镜头；动画、近景、多脸或检测不足会跳过，不显示成修复成功。检测阈值和范围沿用 `analyse` 的保守规则。每次最多处理 49 帧，重叠 8 帧；512×512 脸部画布，8 步、降噪 0.30，原有 Turbo 模型。已有修复候选会按持久提交记录恢复，提交结果不明时停止核对，不重新提交。

`original.mp4` 始终保留。成功时另存 `face-repaired.mp4`，交付文件为 `final.mp4`；原声音以流复制保留。输出必须与原片宽高、帧率、帧数、时长一致。`face-repair.json` 和任务详情的 `face_repair` 记录成功、跳过或失败；跳过/失败有醒目阶段提示，不能据此认为画面通过审查。

## 部署前提

- 使用 gateway 的 `video_progress`、`pipeline.t8_render`、`video_restoration`、GPU 锁与私有连接隔离机制。
- 已安装 `MiniMaxH3FaceRefinePlanT8Advanced`、`MiniMaxH3FaceRefineConditioningT8Advanced`、`MiniMaxH3FaceRefineSamplerT8Advanced`、`MiniMaxH3FaceRefineStitchAuditT8Advanced`，及 H3/VHS 模型和依赖。
- 在 gateway 进程环境中配置 `H3_FACE_DETECTOR`，指向部署机上的 YuNet ONNX 检测模型，不要假设它位于私人 input 同级的 models 下。
- 私人 Studio 的 `Generation` 增加 `face_repair: bool = False` 与 `face_reference_index: int | None = Field(default=None, ge=0, le=8)`；前者开启时只允许 `kind=video, mode=creative`。校验人物参考索引不得超过 labels 数量。
- 在部署和实际短片验证完成后设置 `app.state.h3_face_repair = True`，画布才公布能力并显示开关。
- Studio 同步远端任务详情时也需复制 `face_repair: remote.get('face_repair')`，否则前端只能看到阶段消息，读不到完整修复记录。
- 只在确认没有活动任务后备份、部署 gateway 两个模块及画布 API/UI，重启私人 Studio。不要覆盖公共服务或通过重启中断生成。

方法参考社区 [ComfyUI-H3-FaceRefine](https://github.com/Carasibana/ComfyUI-H3-FaceRefine) 的跟踪、裁剪、局部重绘与合成流程；本适配复用已安装的 T8 节点，并未安装社区原版节点包。提示词、整片二采和超分均不能代替这个步骤。单例测试不保证所有身份、侧脸和表情都能修好，保留原片供对比。
