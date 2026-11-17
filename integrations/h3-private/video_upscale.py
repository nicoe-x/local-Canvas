"""Bounded frame-batch super-resolution with original video/audio preservation."""

import json
import os
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

from video_progress import probe, render_clip

RESOLUTIONS = {"1080P": 1080, "2K": 1440, "4K": 2160}


def dimensions(width, height, resolution):
    edge = RESOLUTIONS[resolution]
    scale = edge / min(width, height)
    return tuple(max(2, round(value * scale / 2) * 2) for value in (width, height))


def graph(source, job_id, offset, count, width, height, fps, pixel=False):
    if not pixel:
        from video_restoration import seed_graph

        return seed_graph(source, job_id, offset, count, width, height, fps)
    nodes = {
        "1": {
            "class_type": "VHS_LoadVideo",
            "inputs": {
                "video": source,
                "force_rate": 0,
                "custom_width": 0,
                "custom_height": 0,
                "frame_load_cap": count,
                "skip_first_frames": offset,
                "select_every_nth": 1,
                "format": "None",
            },
        },
        "4": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["1", 0],
                "upscale_method": "nearest-exact",
                "width": width,
                "height": height,
                "crop": "disabled",
            },
        },
        "5": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["4", 0],
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": f"h3web/{job_id}/upscale/batch{offset:07d}",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 16,
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True,
            },
        },
    }
    return nodes


def enhance(folder, payload, job_id, status, *, face_only=False, source=None):
    from pipeline.t8_render import INPUT, get_outputs, submit

    original = source or folder / "original.mp4"
    info = probe(original)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    width, height = ((video['width'], video['height']) if face_only else
                     dimensions(video["width"], video["height"], payload["video_resolution"]))
    if not face_only and width <= video["width"] and height <= video["height"]:
        return {"state": "SKIPPED", "method": "source_already_large_enough"}
    fps = float(Fraction(video["avg_frame_rate"]))
    frames = video.get("nb_frames")
    if not frames or frames == "N/A":
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-count_frames",
                "-show_entries",
                "stream=nb_read_frames",
                "-of",
                "json",
                str(original),
            ],
            check=True,
            capture_output=True,
            timeout=600,
        )
        frames = json.loads(result.stdout)["streams"][0]["nb_read_frames"]
    frames = int(frames)
    if frames <= 0 or not 0 < fps <= 60:
        raise ValueError("Invalid source video timing")
    source_name = f"h3web/{job_id}/{'face' if face_only else 'upscale'}_source.mp4"
    dest = INPUT / source_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copyfile(original, dest)
    import cv2
    from job_cancel import check_cancelled
    from video_restoration import analyse, face_graph, merge_windows, seed_graph, windows

    strength = float(payload.get("upscale_strength", 0.25))
    face_enabled = (
        bool(payload.get("video_face_refine", True))
        and payload["style"] in {"写实", "电影写实", "胶片摄影", "黑白摄影"}
        and strength > 0
        and abs(fps - 24) < 0.01
    )
    detector = Path(os.environ.get('H3_FACE_DETECTOR', str(INPUT.parent / "models/face_detection/face_detection_yunet_2023mar.onnx")))
    if face_only and not face_enabled:
        return {'state': 'SKIPPED', 'reason': 'requires_photorealistic_24fps', 'face_windows': 0}
    if face_enabled and not detector.is_file():
        raise RuntimeError("小脸检测模型未就绪")
    status("RUNNING", "检查镜头与小脸，保留近景原貌", 94)
    shots = analyse(original, detector, face_enabled, lambda: check_cancelled(folder))
    if not shots or shots[-1]["end"] != frames:
        raise ValueError("Source decoded frame count mismatch")
    if face_only and not any(shot['face_refine'] for shot in shots):
        return {'state': 'SKIPPED', 'reason': 'no_safe_single_small_face_track', 'face_windows': 0}
    identity_image = None
    if face_only and payload.get('face_reference_index') is not None:
        index = payload['face_reference_index']
        if type(index) is not int or not 0 <= index < len(payload.get('labels', [])):
            raise ValueError('Invalid selected face reference')
        # These paths are server-owned, never accepted from the client.
        image = cv2.imread(str(folder / f'image{index}.jpg'))
        if image is None:raise ValueError('Selected face reference is missing')
        detector_ref = cv2.FaceDetectorYN.create(str(detector), '', (image.shape[1], image.shape[0]), .65, .3, 5000)
        _, found = detector_ref.detect(image)
        if found is None:raise ValueError('No clear face in the selected identity reference')
        # A multi-view identity sheet's portrait is normally its largest face.
        x,y,w,h = max(found, key=lambda box: box[2]*box[3])[:4]
        side = int(max(w,h)*1.8);cx,cy=x+w/2,y+h/2
        left,top=max(0,int(cx-side/2)),max(0,int(cy-side/2))
        crop=image[top:min(image.shape[0],top+side),left:min(image.shape[1],left+side)]
        identity_image=f'h3web/{job_id}/face_identity.jpg'
        if not cv2.imwrite(str(INPUT / identity_image),crop):raise ValueError('Could not save face reference')
    batches = folder / ('face-pass-v1' if face_only else "restoration-v2")
    batches.mkdir(exist_ok=True)
    records, face_windows = [], 0
    for shot in shots:
        for offset, count in windows(shot["start"], shot["end"]):
            check_cancelled(folder)
            index = len(records) + 1
            window_source, window_offset = source_name, offset

            def report(prompt_id, _offset=offset):
                status(
                    "RUNNING",
                    (f"小脸局部重绘 {_offset}/{frames} 帧" if face_only else
                     f"保守视频超分 {_offset}/{frames} 帧 · {payload['video_resolution']}"),
                    95 + int(3 * _offset / frames),
                    prompt_id=prompt_id,
                )

            if shot["face_refine"] and abs(fps - 24) < 0.01:
                status("RUNNING", f"小脸局部修复 {offset}/{frames} 帧（背景与音轨保留）", 95)
                padded = count + (5 - count % 17) % 17
                native = dest.parent / f"face-source{offset:07d}.mp4"
                subprocess.run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        str(original),
                        "-vf",
                        f"trim=start_frame={offset}:end_frame={offset + count},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop={padded - count}",
                        "-af",
                        f"atrim=start={offset / fps}:end={(offset + count) / fps},asetpts=PTS-STARTPTS,apad",
                        "-frames:v",
                        str(padded),
                        "-r",
                        str(Fraction(video["avg_frame_rate"])),
                        "-t",
                        str(padded / fps),
                        "-c:v",
                        "libx264",
                        "-crf",
                        "14",
                        "-c:a",
                        "aac",
                        str(native),
                    ],
                    check=True,
                    timeout=600,
                )
                graph_face = face_graph(str(native.relative_to(INPUT)), job_id, count, padded, identity_image)
                # Source-specific directories make resumed stages durable and avoid duplicate GPU submission.
                face_folder = batches / f"face{offset:07d}"
                face_folder.mkdir(exist_ok=True)
                candidate = render_clip(
                    face_folder, 1, graph_face, submit, get_outputs, report, require_audio=False
                )
                face_dest = dest.parent / f"face-candidate{offset:07d}.mp4"
                shutil.copyfile(candidate, face_dest)
                window_source, window_offset = str(face_dest.relative_to(INPUT)), 0
                face_windows += 1
            if face_only:
                # Unselected shots retain the original frames; no full-frame
                # diffusion or resize is used by this pass.
                records.append({'offset': offset, 'count': count,
                                'path': (face_dest if shot['face_refine'] else original,
                                         0 if shot['face_refine'] else offset, count)})
                continue
            work = (
                graph(window_source, job_id, window_offset, count, width, height, fps, True)
                if payload["style"] == "像素艺术"
                else seed_graph(
                    window_source, job_id, window_offset, count, width, height, fps, strength
                )
            )
            clip = render_clip(
                batches, index, work, submit, get_outputs, report, require_audio=False
            )
            records.append({"offset": offset, "count": count, "path": clip})
    target = folder / ('face-repaired.partial.mp4' if face_only else "upscaled.partial.mp4")
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(Fraction(video["avg_frame_rate"])),
        "-i",
        "pipe:0",
        "-i",
        str(original),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(target),
    ]

    def read_frames(path):
        start, limit = 0, None
        if isinstance(path, tuple):
            path, start, limit = path
        cap = cv2.VideoCapture(str(path))
        try:
            if start:cap.set(cv2.CAP_PROP_POS_FRAMES, start)
            seen = 0
            while limit is None or seen < limit:
                ok, frame = cap.read()
                if not ok:
                    break
                if frame.shape[:2] != (height, width):
                    raise ValueError("Restored frame dimensions mismatch")
                yield frame
                seen += 1
        finally:
            cap.release()

    with (batches / "encode.log").open("wb") as log:
        encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=log)
        try:
            emitted = merge_windows(
                records,
                read_frames,
                lambda frame: encoder.stdin.write(frame.tobytes()),
                lambda: check_cancelled(folder),
            )
            encoder.stdin.close()
            if encoder.wait(timeout=600) or emitted != frames:
                raise ValueError("Frame-exact restoration mux failed")
        finally:
            if encoder.poll() is None:
                encoder.kill()
                encoder.wait()
    actual = probe(target)
    output = next(s for s in actual["streams"] if s["codec_type"] == "video")
    if (output["width"], output["height"]) != (width, height) or int(
        output.get("nb_frames", 0)
    ) != frames:
        raise ValueError("Super-resolution output size/frame count mismatch")
    if (
        abs(float(actual["format"]["duration"]) - float(info["format"]["duration"]))
        > 1 / fps + 0.02
    ):
        raise ValueError("Super-resolution output duration mismatch")
    if Fraction(output["avg_frame_rate"]) != Fraction(video["avg_frame_rate"]):
        raise ValueError("Restoration changed source frame rate")
    target.replace(folder / "final.mp4")
    return {
        "state": "COMPLETED",
        "method": "H3_tracked_face_crop_v1" if face_only else "nearest_pixel_grid"
        if payload["style"] == "像素艺术"
        else "Lanczos_resize_only"
        if strength == 0
        else "SeedVR2_3B_conservative_v2",
        "strength": strength,
        "face_windows": face_windows,
        "identity_reference": payload.get('face_reference_index') if face_only else None,
        "face_sampling": {'steps': 8, 'denoise': .30, 'canvas': 512, 'blend': .85} if face_only else None,
        "temporal_overlap": 8,
        "frames": frames,
        "output_size": [width, height],
    }


def finish(folder, payload, job_id, status):
    original = folder / "original.mp4"
    # A usable original remains even when enhancement fails.
    shutil.copyfile(original, folder / "final.mp4")
    result = {"state": "DISABLED"}
    face_result = {'state': 'DISABLED'}
    warning = None
    enhanced_source = None
    if payload.get('face_repair', False):
        try:
            status('RUNNING', '检测并局部重绘小脸 · 原音轨保留', 94)
            face_result = enhance(folder, {**payload, 'video_face_refine': True,
                                          'upscale_strength': .25}, job_id, status, face_only=True)
            if face_result['state'] == 'COMPLETED':
                enhanced_source = folder / 'face-repaired.mp4'
                shutil.copyfile(folder / 'final.mp4', enhanced_source)
            else:
                warning = '小脸修复已跳过：未找到可安全处理的单人小脸轨迹，或画风/帧率不支持；请检查原片'
        except Exception as exc:
            if getattr(exc, 'needs_attention', False):raise
            from job_cancel import check_cancelled
            from job_pause import checkpoint
            check_cancelled(folder);checkpoint(folder)
            face_result = {'state': 'FAILED', 'error_type': type(exc).__name__}
            warning = '小脸修复失败，已保留原片；请检查后重试修复'
        (folder / 'face-repair.json').write_text(json.dumps(face_result), encoding='utf8')
    if payload.get("video_resolution", "native") != "native":
        try:
            # A selected independent pass must not run face diffusion twice.
            result = enhance(folder, {**payload, 'video_face_refine': False} if payload.get('face_repair') else payload,
                             job_id, status, source=enhanced_source)
        except Exception as exc:
            if getattr(exc, "needs_attention", False):
                raise
            print("Video enhancement failed:", type(exc).__name__)
            result = {"state": "FAILED"}
            warning = (warning + '；' if warning else '') + "超分失败，已保留超分前视频，可下载原片"
    info = probe(folder / "final.mp4")
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    (folder / "upscale.json").write_text(json.dumps(result), encoding="utf8")
    from media_checks import collect
    status('RUNNING', '检查黑帧、静音及声音交接', 99)
    observations = collect(folder)
    status(
        "COMPLETED_UNREVIEWED",
        warning or "视频生成完成 · 未审片",
        100,
        size=(folder / "final.mp4").stat().st_size,
        output_size=[video["width"], video["height"]],
        original_ready=True,
        original_size=original.stat().st_size,
        upscale=result,
        upscale_warning=warning,
        face_repair=face_result,
        media_checks=observations,
    )
