"""RGB video -> H3 VAE -> partial-denoise AV sampling, with original audio remux."""
import json
import math
import shutil
import subprocess
from fractions import Fraction


def inspect_source(path):
    if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= 1024**3:
        raise ValueError('源视频不存在或超过1GB')
    result = subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],
                            capture_output=True,check=True,timeout=60)
    info = json.loads(result.stdout)
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    fps = float(Fraction(video['avg_frame_rate']))
    width, height = video['width'], video['height']
    if abs(fps-24) > .001:
        raise ValueError('H3 视频二采需要24fps源视频，请先转换帧率')
    if width % 32 or height % 32 or min(width,height) < 256 or width*height > 1344*768:
        raise ValueError('当前二采支持32像素对齐、最高约1344×768的画面，请先缩小或对齐视频')
    frames = video.get('nb_frames')
    if not frames or frames == 'N/A':
        count = subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-count_frames',
                                '-show_entries','stream=nb_read_frames','-of','json',str(path)],
                               capture_output=True,check=True,timeout=120)
        frames = json.loads(count.stdout)['streams'][0]['nb_read_frames']
    frames = int(frames)
    if not 5 <= frames <= 360:
        raise ValueError('视频二采支持15秒以内的片段，请先拆分长视频')
    return {'width':width, 'height':height, 'frames':frames, 'fps':24,
            'has_audio':any(s['codec_type']=='audio' for s in info['streams'])}


def validate_options(value):
    if not isinstance(value,dict) or set(value) != {'steps','denoise','seed'}:
        raise ValueError('视频二采参数无效')
    if type(value['steps']) is not int or not 1 <= value['steps'] <= 32:
        raise ValueError('视频二采步数须为1–32')
    if type(value['denoise']) not in (int,float) or not math.isfinite(value['denoise']) or not .05 <= value['denoise'] <= 1:
        raise ValueError('视频二采降噪强度须为0.05–1')
    if type(value['seed']) is not int or not 0 <= value['seed'] < 2**53:
        raise ValueError('视频二采随机种子无效')
    return value


def prompt(requirement=''):
    if requirement.strip().startswith('subject_definitions:'):
        return requirement.strip()
    # Exactly one source-frame reference. No inherited, now-unbound Picture N tags.
    return ('subject_definitions: <Picture 1> is the first frame of the source clip, defining its subjects, clothing, environment and composition.\n'
            'summary: Refine the existing video while retaining its action sequence and camera path.\n'
            'retention_analysis: Preserve the identity, body proportions, clothing, objects, lighting and environment shown in <Picture 1> and encoded in the source frames.\n'
            'detailed_description: [Shot 1] Follow the source frames in their existing order. Preserve the original framing, subject movement, facial expression and camera motion. Refine natural surface detail without adding subjects, cuts, captions or gestures. '
            + (requirement.strip()+'\n' if requirement.strip() else '\n')
            + 'overall_soundscape: Preserve the original soundtrack exactly; do not generate new dialogue or sound effects.\n'
            'non_diegetic_music: Preserve the source soundtrack; add no music.')


def graph(source, job_id, info, options, text=''):
    from pipeline.t8_render import build_t8_graph
    from video_prompt import configure_ref2va_graph
    validate_options(options)
    padded = info['frames'] + (5-info['frames']%17)%17
    g = build_t8_graph(prompt(text), [], padded/24, width=info['width'],height=info['height'])
    def node(kind):
        return next((k,n) for k,n in g.items() if n['class_type']==kind)
    cond_id, cond = node('MiniMaxH3AudioConditioningT8')
    sampler_id, sampler = node('MiniMaxH3MultiRateSamplerEXPT8')
    vae = next(k for k,n in g.items() if n['class_type']=='VAELoader' and 'video' in n['inputs']['vae_name'])
    g['resample_source'] = {'class_type':'VHS_LoadVideo','inputs':{
        'video':source,'force_rate':0,'custom_width':0,'custom_height':0,'frame_load_cap':padded,
        'skip_first_frames':0,'select_every_nth':1,'format':'None'}}
    g['resample_reference'] = {'class_type':'ImageFromBatch','inputs':{'image':['resample_source',0],'batch_index':0,'length':1}}
    cond['inputs'].update(audio_mode='lock_source',drive_audio=['resample_source',2],
                          **{'ref_images.ref_image_0':['resample_reference',0]})
    configure_ref2va_graph(g, native=True)
    g['resample_encode'] = {'class_type':'VAEEncodeTiled','inputs':{
        'pixels':['resample_source',0],'vae':[vae,0],'tile_size':512,'overlap':64,'temporal_size':32,'temporal_overlap':8}}
    g['resample_latent'] = {'class_type':'MiniMaxH3SourceAVPrepareT8','inputs':{
        'video_latent':['resample_encode',0], 'audio_latent':[cond_id,1],
        'video_mode':'regenerate','video_denoise_strength':1.0,'audio_mode':'lock',
        'audio_denoise_strength':0.0,'audio_fit_policy':'strict','dtype_device_policy':'match_video'}}
    model = sampler['inputs']['model']
    # This installed sampler is a generic low-denoise dual-clock schedule; no face plan/crop is used.
    sampler['class_type']='MiniMaxH3FaceRefineSamplerT8Advanced'
    sampler['inputs']={'model':model,'av_latent':['resample_latent',0],'steps':options['steps'],
                       'denoise':options['denoise'],'shift_video':12.0,'shift_audio':3.0,
                       'sampler_name':'dual_clock_euler','scheduler':'native_flow'}
    _, sample = node('SamplerCustomAdvanced');sample['inputs']['latent_image']=['resample_latent',0]
    _, noise = node('RandomNoise');noise['inputs']['noise_seed']=options['seed']
    decode_id,_ = node('MiniMaxH3AVDecodeT8')
    g['resample_trim']={'class_type':'ImageFromBatch','inputs':{'image':[decode_id,0],'batch_index':0,'length':info['frames']}}
    _,save = node('VHS_VideoCombine')
    save['inputs'].update(images=['resample_trim',0],filename_prefix=f'h3web/{job_id}/resample/candidate',crf=14)
    save['inputs'].pop('audio',None)
    return g


def run(folder, payload, job_id, status):
    from bridge import job_path
    from job_cancel import check_cancelled
    from job_pause import checkpoint
    from pipeline.t8_render import INPUT, submit, get_outputs
    from video_progress import render_clip, probe, save
    from media_checks import collect
    options = validate_options(payload['video_resample'])
    original = folder/'original.mp4'
    if not original.exists():
        source = job_path(payload['resample_of'])/'final.mp4'
        inspect_source(source)
        shutil.copyfile(source,original)
    info = inspect_source(original)
    checkpoint(folder);check_cancelled(folder)
    padded = info['frames']+(5-info['frames']%17)%17
    name = f'h3web/{job_id}/resample_source.mp4'
    target = INPUT/name;target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        temp=target.with_name('resample_source.partial.mp4')
        args=['ffmpeg','-v','error','-nostdin','-y','-i',str(original)]
        if not info['has_audio']:args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
        args+=['-map','0:v:0','-map','0:a:0' if info['has_audio'] else '1:a:0',
               '-vf',f'tpad=stop_mode=clone:stop={padded-info["frames"]}',
               '-frames:v',str(padded),'-af','apad','-t',str(padded/24),
               '-c:v','libx264','-crf','14','-pix_fmt','yuv420p','-c:a','aac',str(temp)]
        subprocess.run(args,check=True,capture_output=True,timeout=300);temp.replace(target)
    work=folder/'video-resample';work.mkdir(exist_ok=True)
    workflow=graph(name,job_id,info,options,payload.get('text',''))
    clip=render_clip(work,1,workflow,submit,get_outputs,
                     lambda pid:status('RUNNING','H3 视频二次采样 · 保留原音轨',50),require_audio=False)
    checkpoint(folder);check_cancelled(folder)
    temp=folder/'resampled.partial.mp4'
    args=['ffmpeg','-v','error','-nostdin','-y','-i',str(clip),'-i',str(original),'-map','0:v:0']
    if info['has_audio']:args+=['-map','1:a:0','-c:a','copy']
    args+=['-c:v','copy','-movflags','+faststart',str(temp)]
    subprocess.run(args,check=True,capture_output=True,timeout=300)
    result_info=inspect_source(temp)
    if any(result_info[k]!=info[k] for k in ['width','height','frames','fps','has_audio']):
        raise ValueError('二采结果尺寸、帧数或音轨与源视频不一致，未交付结果')
    temp.replace(folder/'final.mp4')
    save(folder/'video-resample.json',{'state':'COMPLETED_UNREVIEWED','method':'H3_RGB_partial_denoise_v1',
                                      'source':payload['resample_of'],**options,**info})
    observations=collect(folder)
    status('COMPLETED_UNREVIEWED','视频二采完成 · 未审片',100,
           size=(folder/'final.mp4').stat().st_size,output_size=[info['width'],info['height']],
           original_ready=True,original_size=original.stat().st_size,media_checks=observations)
