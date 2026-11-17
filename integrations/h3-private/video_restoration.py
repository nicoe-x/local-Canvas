"""Shot-local restoration graphs and bounded, frame-exact overlap merging."""

SEED_MODEL = "seedvr2_3b_int8_convrot.safetensors"
SEED_VAE = "seedvr2_ema_vae_fp16.safetensors"
WINDOW = 49
OVERLAP = 8


def windows(start, end, size=WINDOW, overlap=OVERLAP):
    if size <= overlap or overlap < 0:
        raise ValueError("Invalid temporal window")
    offset = start
    while offset < end:
        count = min(size, end - offset)
        yield offset, count
        if offset + count == end:
            return
        offset += count - overlap


def seed_graph(source, job_id, offset, count, width, height, fps, strength=0.25):
    if not 0 <= strength <= 0.5:
        raise ValueError("Restoration strength must be 0–0.5")
    g = {
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
        "2": {
            "class_type": "ImageScale",
            "inputs": {
                "image": ["1", 0],
                "upscale_method": "lanczos",
                "width": width,
                "height": height,
                "crop": "disabled",
            },
        },
        "3": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": SEED_MODEL, "weight_dtype": "default"},
        },
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": SEED_VAE}},
        "6": {"class_type": "SeedVR2Preprocess", "inputs": {"resized_images": ["2", 0]}},
        "7": {
            "class_type": "VAEEncodeTiled",
            "inputs": {
                "pixels": ["6", 0],
                "vae": ["4", 0],
                "tile_size": 512,
                "overlap": 128,
                "temporal_size": 32,
                "temporal_overlap": 8,
            },
        },
        "14": {
            "class_type": "SeedVR2TemporalChunk",
            "inputs": {"latent": ["7", 0], "temporal_overlap": 1, "chunking_mode": "auto"},
        },
        "8": {
            "class_type": "SeedVR2Conditioning",
            "inputs": {"model": ["3", 0], "vae_conditioning": ["14", 0]},
        },
        "9": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["3", 0],
                "positive": ["8", 0],
                "negative": ["8", 1],
                "latent_image": ["14", 0],
                "seed": 42,
                "steps": 1,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "15": {
            "class_type": "SeedVR2TemporalMerge",
            "inputs": {"latents": ["9", 0], "temporal_overlap": ["14", 1]},
        },
        "10": {
            "class_type": "VAEDecodeTiled",
            "inputs": {
                "samples": ["15", 0],
                "vae": ["4", 0],
                "tile_size": 512,
                "overlap": 128,
                "temporal_size": 32,
                "temporal_overlap": 8,
            },
        },
        "11": {
            "class_type": "SeedVR2PostProcessing",
            "inputs": {
                "images": ["10", 0],
                "original_resized_images": ["2", 0],
                "color_correction_method": "lab",
            },
        },
        "12": {
            "class_type": "ImageBlend",
            "inputs": {
                "image1": ["2", 0],
                "image2": ["11", 0],
                "blend_factor": strength,
                "blend_mode": "normal",
            },
        },
        "13": {
            "class_type": "ImageFromBatch",
            "inputs": {"image": ["12", 0], "batch_index": 0, "length": count},
        },
        "5": {
            "class_type": "VHS_VideoCombine",
            "inputs": {
                "images": ["13", 0],
                "frame_rate": fps,
                "loop_count": 0,
                "filename_prefix": f"h3web/{job_id}/restoration/window{offset:07d}",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 14,
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True,
            },
        },
    }
    if strength == 0:
        for key in list(g):
            if key not in {"1", "2", "5"}:
                del g[key]
        g["5"]["inputs"]["images"] = ["2", 0]
    return g


def face_graph(source, job_id, count, padded, identity_image=None):
    from pipeline.t8_render import build_t8_graph
    from video_prompt import configure_ref2va_graph

    prompt = (
        "subject_definitions: <Subject 1> is the person whose facial identity comes from <Picture 1>.\n"
        "summary: Ref2VA local face restoration of <Subject 1>, retaining the source video motion.\n"
        "retention_analysis: Retain facial structure, eye shape, hairstyle and visible accessories from "
        "<Picture 1>. Retain source head pose, expression, gaze, mouth motion and scene lighting.\n"
        "detailed_description: [Shot 1] Restore only the face of <Subject 1> in the source crop. "
        "Keep the original head size and position, natural expression and mouth movement. "
        "Natural skin texture, no beautification, no added speech. No subtitles or captions.\n"
        "overall_soundscape: No additional sound.\nnon_diegetic_music: N/A"
    )
    g = build_t8_graph(prompt, [], padded / 24, width=512, height=512, video_steps=8, audio_steps=8)

    def kind(name):
        return next((key, node) for key, node in g.items() if node["class_type"] == name)

    cond_id, cond = kind("MiniMaxH3AudioConditioningT8")
    sampler_id, sampler = kind("MiniMaxH3MultiRateSamplerEXPT8")
    _, decode = kind("MiniMaxH3AVDecodeT8")
    vae_id, _ = next(
        (key, node)
        for key, node in g.items()
        if node["class_type"] == "VAELoader" and "video" in node["inputs"]["vae_name"]
    )
    g["2001"] = {
        "class_type": "VHS_LoadVideo",
        "inputs": {
            "video": source,
            "force_rate": 0,
            "custom_width": 0,
            "custom_height": 0,
            "frame_load_cap": padded,
            "skip_first_frames": 0,
            "select_every_nth": 1,
            "format": "None",
        },
    }
    g["2002"] = {
        "class_type": "MiniMaxH3FaceRefinePlanT8Advanced",
        "inputs": {
            "frames": ["2001", 0],
            "fps": 24.0,
            "detector_mode": "local_opencv_yunet",
            "detector_model": "face_detection/face_detection_yunet_2023mar.onnx",
            "detector_device": "cpu",
            "confidence": 0.65,
            "manual_roi_x": 0.3,
            "manual_roi_y": 0.1,
            "manual_roi_width": 0.4,
            "manual_roi_height": 0.55,
            "scene_cut_threshold": 0.22,
            "max_track_jump": 0.12,
            "max_gap_frames": 3,
            "smoothing_radius": 3,
            "crop_context_scale": 3.0,
            "canvas_size": "512",
            "require_h3_grid": True,
            "analysis_chunk_frames": 8,
        },
    }
    g["2003"] = {
        "class_type": "ImageFromBatch",
        "inputs": {"image": ["2002", 1], "batch_index": 0, "length": 1},
    }
    if identity_image:
        g['2003'] = {'class_type': 'LoadImage', 'inputs': {'image': identity_image}}
    cond["inputs"].update(
        task_type="Ref2VA",
        audio_mode="lock_source",
        drive_audio=["2001", 2],
        **{"ref_images.ref_image_0": ["2003", 0]},
    )
    g["2004"] = {
        "class_type": "MiniMaxH3FaceRefineConditioningT8Advanced",
        "inputs": {
            "positive": [cond_id, 0],
            "av_latent": [cond_id, 1],
            "crops": ["2002", 1],
            "video_vae": [vae_id, 0],
            "face_plan": ["2002", 0],
            "audio_policy": "require_locked",
            "allow_multi_shot_exp": False,
        },
    }
    configure_ref2va_graph(g)
    sampler["class_type"] = "MiniMaxH3FaceRefineSamplerT8Advanced"
    sampler["inputs"] = {
        "model": sampler["inputs"]["model"],
        "av_latent": ["2004", 1],
        "steps": 8,
        "denoise": 0.30,
        "shift_video": 12.0,
        "shift_audio": 3.0,
        "sampler_name": "dual_clock_euler",
        "scheduler": "native_flow",
    }
    _, guider = kind("BasicGuider")
    guider["inputs"]["conditioning"] = ["2004", 0]
    _, sample = kind("SamplerCustomAdvanced")
    sample["inputs"]["latent_image"] = ["2004", 1]
    decode_id, _ = kind("MiniMaxH3AVDecodeT8")
    g["2005"] = {
        "class_type": "MiniMaxH3FaceRefineStitchAuditT8Advanced",
        "inputs": {
            "base_frames": ["2001", 0],
            "refined_crops": [decode_id, 0],
            "face_plan": ["2002", 0],
            "paste_region": "ellipse",
            "feather_source_px": 8.0,
            "blend_strength": 0.85,
            "color_match_strength": 0.8,
            "max_face_mean_abs_delta": 0.20,
            "fallback_neighbor_frames": 2,
            "processing_device": "cpu_memory_safe",
        },
    }
    g["2006"] = {
        "class_type": "ImageFromBatch",
        "inputs": {"image": ["2005", 0], "batch_index": 0, "length": count},
    }
    _, save = kind("VHS_VideoCombine")
    save["inputs"].update(
        images=["2006", 0], filename_prefix=f"h3web/{job_id}/face_refine/candidate", crf=14
    )
    save["inputs"].pop("audio", None)
    return g


def analyse(source, detector, enabled=True, check=lambda: None):
    """CPU analysis only; exclude closeups, crowds and uncertain/short tracks."""
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(source))
    face = (
        cv2.FaceDetectorYN.create(str(detector), "", (320, 320), 0.65, 0.3, 5000)
        if enabled
        else None
    )
    shots, previous, start, sizes, crowd, frames = [], None, 0, [], False, 0

    def shot(end):
        heights = [v for v in sizes if v is not None]
        return {
            "start": start,
            "end": end,
            "face_refine": bool(
                face
                and not crowd
                and len(heights) >= max(5, (end - start) * 0.6)
                and 20 <= float(np.median(heights)) <= 96
                and max(heights) <= 120
            ),
        }

    try:
        while True:
            check()
            ok, frame = cap.read()
            if not ok:
                break
            proxy = cv2.resize(frame, (32, 32)).astype(np.float32) / 255
            if previous is not None and float(np.abs(proxy - previous).mean()) >= 0.22:
                shots.append(shot(frames))
                start, sizes, crowd = frames, [], False
            previous = proxy
            found = None
            if face is not None:
                h, w = frame.shape[:2]
                scale = min(1.0, 640 / w)
                small = cv2.resize(frame, (round(w * scale), round(h * scale)))
                face.setInputSize((small.shape[1], small.shape[0]))
                _, detections = face.detect(small)
                if detections is not None:
                    crowd |= len(detections) > 1
                    found = float(max(d[3] for d in detections)) / scale
            sizes.append(found)
            frames += 1
        if frames > start:
            shots.append(shot(frames))
    finally:
        cap.release()
    return shots


def merge_windows(records, read_frames, emit, check):
    """Crossfade overlapping copies of the same source frames, never across shots."""
    import numpy as np

    pending, written = [], 0
    for index, record in enumerate(records):
        offset, count = record["offset"], record["count"]
        overlap = written + len(pending) - offset
        if overlap < 0 or overlap > len(pending):
            raise ValueError("Noncontiguous restoration windows")
        prefix = len(pending) - overlap
        for frame in pending[:prefix]:
            check()
            emit(frame)
            written += 1
        pending = pending[prefix:]
        keep = (
            0
            if index + 1 == len(records)
            else max(0, offset + count - records[index + 1]["offset"])
        )
        seen = 0
        for i, frame in enumerate(read_frames(record["path"])):
            check()
            if i >= count:
                raise ValueError("Restoration returned extra frames")
            if i < overlap:
                alpha = (i + 1) / (overlap + 1)
                frame = (
                    np.rint(
                        pending[i].astype(np.float32) * (1 - alpha)
                        + frame.astype(np.float32) * alpha
                    )
                    .clip(0, 255)
                    .astype(np.uint8)
                )
            if i < count - keep:
                emit(frame)
                written += 1
            else:
                # Keep at most OVERLAP raw frames, independent of video length.
                if i == count - keep:
                    tail = []
                tail.append(frame)
            seen += 1
        if seen != count:
            raise ValueError("Restoration returned too few frames")
        pending = tail if keep else []
    if pending:
        raise ValueError("Unmerged temporal tail")
    return written
