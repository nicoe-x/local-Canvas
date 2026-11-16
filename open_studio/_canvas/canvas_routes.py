"""Additive private Studio routes. Existing create() owns all generation validation."""
import asyncio
import io
import json
import uuid
from pathlib import Path

from fastapi import HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from canvas_store import Store, Conflict, checked_id, fingerprint, document, resolve_reference_mentions


def register(ns):
    app = ns["app"]
    store = Store(ns["DATA"] / "canvases.sqlite3")
    from canvas_media_tools import register as register_media_tools
    register_media_tools(ns,store)
    from canvas_selection_download import register as register_selection_download
    register_selection_download(ns,store)
    locks = [asyncio.Lock() for _ in range(32)]

    def identity(request, write=False):
        return ns["authenticate"](request, sensitive=True, write=write)["id"]

    def get(owner, key):
        try:
            return store.get(owner, key)
        except (ValueError, KeyError):
            raise HTTPException(404, "画布不存在") from None

    def media_folder(owner, key):
        # User identity is server-resolved; no caller path or owner accepted.
        return ns["MATERIAL"] / "canvas" / ns["user_folder"](owner) / checked_id(key)

    def snapshot(owner, result):
        folder = media_folder(owner, result["id"])
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = folder / (uuid.uuid4().hex + ".partial")
        temp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf8")
        temp.replace(folder / "board.json")

    from canvas_trash import register as register_trash
    register_trash(ns, store, snapshot)

    @app.get("/api/canvas-projects")
    def projects(request: Request):
        return store.projects(identity(request))

    @app.post("/api/canvas-projects")
    @app.put("/api/canvas-projects/{key}")
    async def project_write(request: Request, key: str = None):
        owner=identity(request, True)
        try:
            data=await request.json()
            if not isinstance(data,dict) or set(data)!={"name"}:raise ValueError("仅接受项目名称")
            return store.rename_project(owner,key,data["name"]) if key else store.create_project(owner,data["name"])
        except KeyError:raise HTTPException(404,"项目不存在") from None
        except ValueError as exc:raise HTTPException(422,str(exc)) from None

    @app.put("/api/canvases/{key}/project")
    async def move_project(key: str, request: Request):
        owner=identity(request,True)
        get(owner,key)
        try:
            data=await request.json()
            if not isinstance(data,dict) or set(data)!={"project_id","revision"}:raise ValueError("分类参数无效")
            result=store.move(owner,key,data["project_id"],data["revision"])
            snapshot(owner,result)
            return result
        except KeyError:raise HTTPException(404,"项目不存在") from None
        except Conflict as exc:raise HTTPException(409,str(exc)) from None
        except ValueError as exc:raise HTTPException(422,str(exc)) from None

    def validate_sources(owner, value):
        for node in value.get("nodes", []):
            if node.get("job_id"):
                with ns["database"]() as db:
                    row = db.execute("SELECT owner,purged_at,purge_started_at FROM jobs WHERE id=?", (checked_id(node["job_id"]),)).fetchone()
                # A removed source may remain on its owner's board as a missing card.
                if not row or row["owner"] != owner or ("purged_at" in row.keys() and row["purged_at"]) or ("purge_started_at" in row.keys() and row["purge_started_at"]):
                    raise HTTPException(404, "素材不存在")

    def check_saved_sources(owner,key,value):
        validate_sources(owner,value)
        for node in value.get('nodes',[]):
            if node.get('media_id'):
                path=media_folder(owner,key)/(checked_id(node['media_id'])+'.jpg')
                if not path.is_file() or path.is_symlink(): raise HTTPException(409,'参考图片已删除，无法保存此节点')
    store.source_validator=check_saved_sources

    @app.get("/canvas")
    def page(request: Request):
        # Shell holds no private data; every API and media endpoint authenticates.
        return FileResponse(ns.get("CANVAS_STATIC", Path(__file__).parent / "static") / "canvas.html")

    @app.get("/api/canvases")
    def listing(request: Request):
        try:
            return store.list(identity(request), request.query_params.get("project_id", "all"))
        except (ValueError, KeyError):
            raise HTTPException(404, "项目不存在") from None

    @app.get("/api/canvas-config")
    def config(request: Request):
        identity(request)
        return {"image_styles": list(ns["STYLE_PROMPTS"]), "video_styles": list(ns["VIDEO_STYLES"])}

    @app.post("/api/canvases")
    async def create_canvas(request: Request):
        owner = identity(request, True)
        try:
            raw = await request.json()
            if not isinstance(raw, dict):raise ValueError("画布格式无效")
            project_id = raw.pop("project_id", None)
            value = document(raw)
            validate_sources(owner, value)
            result = store.create(owner, value, project_id)
            snapshot(owner, result)
            return result
        except KeyError:
            raise HTTPException(404, "项目不存在") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/api/canvases/{key}")
    def read_canvas(key: str, request: Request):
        return get(identity(request), key)

    @app.put("/api/canvases/{key}")
    async def save_canvas(key: str, request: Request):
        owner = identity(request, True)
        get(owner, key)
        try:
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError("画布格式无效")
            value = document(data["document"])
            validate_sources(owner, value)
            result = store.save(owner, key, data["revision"], value)
            snapshot(owner, result)
            return result
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/canvases/{key}/media")
    async def upload(key: str, request: Request):
        owner = identity(request, True)
        get(owner, key)
        if int(request.headers.get("content-length", "0")) > 10 * 1024 * 1024:
            raise HTTPException(413, "图片不能超过10MB")
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 10 * 1024 * 1024:
                raise HTTPException(413, "图片不能超过10MB")
        try:
            data = await asyncio.to_thread(ns["clean_image"], bytes(raw))
        except (ValueError, ns["UnidentifiedImageError"]):
            raise HTTPException(422, "仅支持有效的PNG、JPEG、WebP图片") from None
        folder = media_folder(owner, key)
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        media = uuid.uuid4().hex
        (folder / (media + ".jpg")).write_bytes(data)
        return {"media_id": media}

    @app.get("/api/canvases/{key}/media/{media}")
    def read_media(key: str, media: str, request: Request):
        owner = identity(request)
        get(owner, key)
        try:
            path = media_folder(owner, key) / (checked_id(media) + ".jpg")
        except ValueError:
            raise HTTPException(404, "素材不存在") from None
        if not path.is_file() or path.is_symlink():
            raise HTTPException(404, "素材不存在")
        return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})

    @app.get("/api/canvases/{key}/runs")
    def runs(key: str, request: Request):
        owner = identity(request)
        get(owner, key)
        result = store.runs(owner, key)
        for run in result:
            if run["job_id"]:
                try:
                    row = ns["owned_job"](run["job_id"], owner)
                    run.update(job_state=row["state"], stage=row["stage"], progress=row["progress"])
                except HTTPException:
                    run.update(job_state="REMOVED", stage="作品已删除", progress=0)
        return result

    @app.post("/api/canvases/{key}/nodes/{node_id}/generate")
    async def generate(key: str, node_id: str, request: Request):
        owner = identity(request, True)
        get(owner, key)
        async with locks[int(key[:4], 16) % len(locks)]:
            board = get(owner, key)
            body = await request.json()
            if not isinstance(body, dict):
                raise HTTPException(422, "提交格式无效")
            if body.get("revision") != board["revision"]:
                raise HTTPException(409, "请先保存最新画布再生成")
            graph = board["document"]
            nodes = {node["id"]: node for node in graph["nodes"]}
            node = nodes.get(node_id)
            if not node or node["kind"] not in {"image", "video"}:
                raise HTTPException(422, "请选择图片或视频生成卡片")
            sources = [nodes[edge["source"]] for edge in graph["edges"] if edge["target"] == node_id]
            reference_count = sum(source["kind"] not in {"note", "reverse"} for source in sources)
            if reference_count > (4 if node["kind"] == "image" else 9):
                raise HTTPException(422, "参考图数量超限：图片最多4张，视频最多9张")
            if node["kind"] == "image" and reference_count and node.get("settings", {}).get("variant", "z_image_turbo") in {"z_image_turbo", "flux_dev"}:
                raise HTTPException(422, "当前模型仅支持文生图，请切换Qwen或H3-Image以使用参考图")
            # Latest submitted run is the source output, unless the user imported a job.
            latest = {run["node_id"]: run for run in store.runs(owner, key)}
            prompts, uploads, source_ids, reference_nodes = [], [], [], []
            for edge in graph["edges"]:
                if edge["target"] != node_id:
                    continue
                source = nodes[edge["source"]]
                if source["kind"] in {"note", "reverse"}:
                    if source["kind"] == "reverse" and not source.get("text", "").strip():
                        raise HTTPException(422, "图片反推尚未完成，请先运行上游反推节点")
                    prompts.append(source.get("text", ""))
                    continue
                run = latest.get(source["id"], {})
                job_id = source.get("job_id") or run.get("job_id")
                if job_id:
                    row = ns["owned_job"](job_id, owner)
                    if row["state"] != "COMPLETED_UNREVIEWED" or json.loads(row["payload"]).get("kind") != "image":
                        raise HTTPException(422, "图片参考须为已完成的图片；视频卡片暂不作为参考视频输入")
                    path = ns["output_folder"](row) / "final.png"
                    source_ids.append(job_id)
                elif source.get("media_id"):
                    path = media_folder(owner, key) / (checked_id(source["media_id"]) + ".jpg")
                    source_ids.append(source["media_id"])
                else:
                    raise HTTPException(422, "上游参考图尚未生成或上传，请先完成上游卡片")
                if not path.is_file() or path.is_symlink() or path.stat().st_size > 10 * 1024 * 1024:
                    raise HTTPException(422, "参考图不存在或超过10MB，请重新选择")
                reference_nodes.append(source["id"])
                uploads.append(UploadFile(file=io.BytesIO(path.read_bytes()), filename=f"参考图{len(uploads)+1}.png"))
            try:
                prompts.append(resolve_reference_mentions(node.get("text", ""), node.get("settings", {}), reference_nodes, node["kind"]))
            except ValueError as exc:
                raise HTTPException(422,str(exc)) from None
            text = "\n\n".join(item.strip() for item in prompts if item.strip())
            if not text:
                raise HTTPException(422, "请填写提示词，或连接一张提示词卡片")
            settings = dict(node.get("settings", {}))
            if node["kind"] == "video":
                seconds = settings.get("seconds", 5)
                if isinstance(seconds, bool) or not isinstance(seconds, (int,float)) or not 4 <= seconds <= 15:
                    raise HTTPException(422, "画布单分镜时长为4–15秒")
            payload = {**settings, "title": node.get("title") or "画布生成", "text": text,
                       "kind": node["kind"], "mode": "creative", "style": settings.get("style", "自定义风格"),
                       "ratio": settings.get("ratio", "16:9"), "labels": [f"参考图{i+1}" for i in range(len(uploads))],
                       "expedite": False}
            if node["kind"] == "image":
                variant = settings.get("variant", "z_image_turbo")
                payload.update(variant=variant, steps=settings.get("steps", {"z_image_turbo": 8, "h3_image_w4a8": 6}.get(variant, 40)))
            try:
                ns["Generation"].model_validate(payload)
                stamp = fingerprint({"text": text, "sources": source_ids})
                # Preserve infrastructure-failure classification for run history.
                try:
                    from job_errors import INFRASTRUCTURE_CODES
                except ImportError:
                    INFRASTRUCTURE_CODES = set()
                for old in store.runs(owner, key):
                    if old["node_id"] != node_id or old["state"] != "SUBMITTED" or not old.get("job_id"):
                        continue
                    try:
                        row = ns["owned_job"](old["job_id"], owner)
                        error = json.loads(row["detail"]).get("error", {}) if "detail" in row.keys() else {}
                        if row["state"] == "FAILED" and isinstance(error, dict) and error.get("code") in INFRASTRUCTURE_CODES:
                            store.exclude_infrastructure(old["token"])
                    except HTTPException:
                        pass
                previous = latest.get(node_id)
                # Replaying the original submission token must return its recorded job,
                # even when that job is already running.
                if previous and previous.get("job_id") and previous["token"] != body.get("token"):
                    try:
                        previous_row = ns["owned_job"](previous["job_id"], owner)
                        if previous_row["state"] not in ns["TERMINAL"]:
                            raise Conflict("当前卡片仍有任务在处理，请等待完成")
                    except HTTPException as exc:
                        if exc.status_code != 404:
                            raise
                run, claimed = store.claim(owner, key, node_id, body.get("token"), stamp)
            except Conflict as exc:
                raise HTTPException(409, str(exc)) from None
            except (ValueError, TypeError) as exc:
                raise HTTPException(422, str(exc)) from None
            if not claimed:
                return run
            try:
                result = await ns["create"](request=request, metadata=json.dumps(payload, ensure_ascii=False), images=uploads,
                    audio_reference=None, video_reference=None, script_document=None, script_text=None, script_encoding="auto", script_ocr=True)
            except HTTPException:
                store.finish(body["token"])
                raise
            # Unexpected errors intentionally leave PENDING. Never blindly create another job.
            store.finish(body["token"], result["id"])
            return {"state": "SUBMITTED", "job_id": result["id"], "token": body["token"]}
