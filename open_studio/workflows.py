"""Comfy API-format workflow profiles with explicit semantic input bindings."""
import copy
import math
import secrets
import uuid

ROLES={'positive','negative','seed','steps','cfg','width','height','seconds','fps','frames','reference_images'}


def infer(graph):
    result={}
    for key,node in graph.items():
        inputs=node.get('inputs',{});kind=node.get('class_type','')
        for role in ['seed','steps','cfg','width','height','fps','frames','seconds']:
            names={'seed':['seed','noise_seed'],'frames':['length','num_frames','frames']}.get(role,[role])
            for name in names:
                if name in inputs and not isinstance(inputs[name],list):result.setdefault(role,[]).append({'node':key,'input':name})
        if kind in ['KSampler','KSamplerAdvanced']:
            for role in ['positive','negative']:
                link=inputs.get(role)
                if isinstance(link,list) and len(link)==2 and str(link[0]) in graph and graph[str(link[0])].get('class_type')=='CLIPTextEncode':result[role]=[{'node':str(link[0]),'input':'text'}]
        if kind=='LoadImage':result.setdefault('reference_images',[]).append({'node':key,'input':'image'})
    return result


def validate(value,info=None):
    if not isinstance(value,dict) or set(value)-{'id','name','kind','graph','bindings','defaults','frame_multiple','frame_offset'}:raise ValueError('工作流配置格式无效')
    value=copy.deepcopy(value);graph=value.get('graph')
    if not isinstance(graph,dict) or not 1<=len(graph)<=2000 or any(not isinstance(k,str) or not isinstance(n,dict) or not isinstance(n.get('class_type'),str) or not isinstance(n.get('inputs'),dict) for k,n in graph.items()):raise ValueError('请导入 ComfyUI 导出的 API 格式 JSON，不是画布 nodes/links 格式')
    if not isinstance(value.get('name'),str) or not 1<=len(value['name'].strip())<=80 or value.get('kind') not in ['image','video']:raise ValueError('请填写工作流名称和图片/视频类型')
    bindings=value.get('bindings',infer(graph))
    if not isinstance(bindings,dict) or set(bindings)-ROLES or not bindings.get('positive'):raise ValueError('需要明确绑定正向提示词；无法自动识别时请填写 bindings')
    for role,items in bindings.items():
        if not isinstance(items,list) or not 1<=len(items)<=100:raise ValueError('参数绑定必须是非空数组')
        for item in items:
            if not isinstance(item,dict) or set(item)!={'node','input'} or item['node'] not in graph or item['input'] not in graph[item['node']]['inputs']:raise ValueError('绑定指向不存在的节点或输入')
    if len(bindings.get('reference_images',[]))>9:raise ValueError('最多9张参考图')
    defaults=value.get('defaults',{})
    if not isinstance(defaults,dict) or set(defaults)-{'steps','cfg','width','height','fps','seconds','negative'}:raise ValueError('默认参数无效')
    for key,low,high in [('steps',1,200),('cfg',0,30),('width',64,8192),('height',64,8192),('fps',1,120),('seconds',4,15)]:
        v=defaults.get(key,{'steps':20,'cfg':7,'width':768,'height':512,'fps':24,'seconds':5}[key])
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not low<=v<=high:raise ValueError('默认参数超出范围：'+key)
        defaults[key]=v
    if not isinstance(defaults.get('negative',''),str) or len(defaults.get('negative',''))>50000:raise ValueError('负向提示词无效')
    multiple=value.get('frame_multiple',1);offset=value.get('frame_offset',0)
    if type(multiple)!=int or not 1<=multiple<=64 or type(offset)!=int or not 0<=offset<multiple:raise ValueError('帧数对齐参数无效')
    if info is not None:
        missing=sorted({n['class_type'] for n in graph.values()}-set(info))
        if missing:raise ValueError('ComfyUI 缺少节点：'+', '.join(missing[:20]))
    value.update(id=value.get('id') or uuid.uuid4().hex,bindings=bindings,defaults=defaults,frame_multiple=multiple,frame_offset=offset)
    if not isinstance(value['id'],str) or len(value['id'])!=32 or any(c not in '0123456789abcdef' for c in value['id']):raise ValueError('工作流编号无效')
    return value


def render(profile,payload,references):
    graph=copy.deepcopy(profile['graph']);defaults=profile['defaults'];bindings=profile['bindings']
    if len(references)>len(bindings.get('reference_images',[])):raise ValueError('该工作流没有足够的参考图片绑定')
    # A reference-dependent workflow cannot run with its required slots empty.
    if bindings.get('reference_images') and len(references)!=len(bindings['reference_images']):raise ValueError(f"该工作流需要 {len(bindings['reference_images'])} 张参考图")
    ratio=payload.get('ratio','16:9').split(':')
    if len(ratio)!=2 or not all(p.isdigit() and 1<=int(p)<=32 for p in ratio):raise ValueError('画幅无效')
    aspect=int(ratio[0])/int(ratio[1]);area=defaults['width']*defaults['height']
    seconds=payload.get('seconds',defaults['seconds']);fps=defaults['fps'];frames=round(seconds*fps)
    multiple=profile['frame_multiple'];offset=profile['frame_offset'];frames=max(offset,round((frames-offset)/multiple)*multiple+offset)
    values={'positive':payload['text'],'negative':defaults.get('negative',''),'seed':payload.get('seed') if payload.get('seed') is not None else secrets.randbits(50),'steps':payload.get('steps',defaults['steps']),'cfg':payload.get('cfg',defaults['cfg']),'width':max(64,round(math.sqrt(area*aspect)/64)*64),'height':max(64,round(math.sqrt(area/aspect)/64)*64),'seconds':seconds,'fps':fps,'frames':frames}
    for role,items in bindings.items():
        for index,item in enumerate(items):graph[item['node']]['inputs'][item['input']]=references[index] if role=='reference_images' else values[role]
    return graph


def standard(checkpoint):
    graph={
        '1':{'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':checkpoint}},
        '2':{'class_type':'CLIPTextEncode','inputs':{'text':'','clip':['1',1]}},
        '3':{'class_type':'CLIPTextEncode','inputs':{'text':'','clip':['1',1]}},
        '4':{'class_type':'EmptyLatentImage','inputs':{'width':768,'height':512,'batch_size':1}},
        '5':{'class_type':'KSampler','inputs':{'model':['1',0],'positive':['2',0],'negative':['3',0],'latent_image':['4',0],'seed':1,'steps':20,'cfg':7,'sampler_name':'euler','scheduler':'normal','denoise':1}},
        '6':{'class_type':'VAEDecode','inputs':{'samples':['5',0],'vae':['1',2]}},
        '7':{'class_type':'SaveImage','inputs':{'images':['6',0],'filename_prefix':'OpenStudio'}},
    }
    return validate({'name':'标准文生图 · '+checkpoint[:50],'kind':'image','graph':graph})
