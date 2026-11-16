/* Compact model/mode/settings toolbar; existing form controls remain the source of truth. */
(() => {
  const composer=$('node-composer'),bottom=composer.querySelector('.composer-bottom');
  const models={z_image_turbo:['Z-Image Turbo','z'],h3_image_w4a8:['Minimax H3 Image · W4A8','h3'],bf16:['Qwen Image · BF16','qwen'],gguf_uc_q8:['Qwen Image · Q8','qwen'],flux_dev:['FLUX.1 dev','flux']};
  function icon(kind){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');svg.classList.add('model-symbol');
    const p=document.createElementNS(svg.namespaceURI,'path');p.setAttribute('fill','none');p.setAttribute('stroke','currentColor');p.setAttribute('stroke-width','1.8');p.setAttribute('stroke-linecap','round');p.setAttribute('stroke-linejoin','round');
    p.setAttribute('d',({h3:'M18 17c5-5 0-14-6-14C5 3 2 10 5 16c3 7 13 6 13-1 0-5-7-8-10-3-2 4 4 8 7 4 2-3-3-6-4-3',z:'M5 6h14L5 18h14M7 3l-3 3 3 3m10 6 3 3-3 3',qwen:'m12 3 3 5 6 1-4 5 1 6-6-3-6 3 1-6-4-5 6-1Z',flux:'M5 4v16M5 5h14M5 12h11',ratio:'M4 6h16v12H4z',text:'M5 5h14M12 5v15M8 20h8',image:'M3 5h18v14H3zM4 17l6-6 4 4 3-3 4 5',chevron:'m8 10 4 4 4-4'})[kind]||'M4 12h16');svg.append(p);return svg;}
  function button(id,label){const b=el('button','toolbar-trigger');b.type='button';b.id=id;b.setAttribute('aria-label',label);b.setAttribute('aria-expanded','false');bottom.prepend(b);return b;}
  const settingsButton=button('toolbar-settings','画面参数'),modeButton=button('toolbar-mode','生成模式'),modelButton=button('toolbar-model','选择生成模型');
  const popup=el('div','toolbar-popup');popup.id='toolbar-popup';popup.setAttribute('popover','auto');document.body.append(popup);
  let active=null,nodeId=null;
  function close(){active?.setAttribute('aria-expanded','false');active=null;if(popup.matches(':popover-open'))popup.hidePopover();}
  popup.addEventListener('toggle',()=>{if(!popup.matches(':popover-open')){active?.setAttribute('aria-expanded','false');active=null;}});
  function position(){if(!active)return;const r=active.getBoundingClientRect();popup.style.width=Math.min(active===settingsButton?350:320,innerWidth-24)+'px';const box=popup.getBoundingClientRect();popup.style.left=Math.max(12,Math.min(innerWidth-box.width-12,r.left))+'px';popup.style.top=Math.max(12,r.top-box.height-10)+'px';}
  function open(trigger,fill){if(active===trigger&&popup.matches(':popover-open')){close();return;}close();popup.replaceChildren();active=trigger;fill();trigger.setAttribute('aria-expanded','true');popup.showPopover();position();popup.querySelector('button,input,select')?.focus({preventScroll:true});}
  function heading(text){popup.append(el('h3','',text));}
  function change(id,value,event='input'){const field=$(id);field.value=value;field.dispatchEvent(new Event(event));sync();}
  function modelRow(value,label,mark){const row=el('button','toolbar-model-row');row.type='button';row.dataset.model=value;row.append(icon(mark),el('span','',label));const current=nodeBy(selected).kind==='video'||$('composer-model').value===value;row.setAttribute('aria-pressed',String(current));if(current)row.append(el('small','','已选择'));row.onclick=()=>{if(nodeBy(selected).kind==='image')change('composer-model',value,'change');close();};popup.append(row);}
  modelButton.onclick=()=>open(modelButton,()=>{heading('生成模型');if(nodeBy(selected).kind==='video')modelRow('default','Minimax H3','h3');else for(const [value,[label,mark]] of Object.entries(models))modelRow(value,label,mark);});
  modeButton.onclick=()=>open(modeButton,()=>{heading('生成模式');const n=nodeBy(selected),refs=doc().edges.filter(e=>e.target===n.id&&!['note','reverse','h3prompt'].includes(nodeBy(e.source).kind)).length;
    if(n.kind==='video'){popup.append(el('p','toolbar-note',refs?'参考图生成视频 · 已连接 '+refs+' 张图片':'文生视频 · 连接图片后自动作为参考图'));return;}
    for(const [value,label] of [['general','自由生图 / 图片参考'],['edit','原图重绘'],['tryon','换装']]){const row=el('button','toolbar-choice',label);row.type='button';row.setAttribute('aria-pressed',String($('image-task').value===value));row.onclick=()=>{change('image-task',value);close();};popup.append(row);}
  });
  function parameters(){heading('画面比例');const ratios=el('div','toolbar-ratios'),n=nodeBy(selected);
    for(const ratio of (n.kind==='video'?['16:9','9:16','1:1']:['16:9','4:3','1:1','3:4','9:16'])){const b=el('button','toolbar-choice');b.type='button';const outline=el('i','ratio-outline');const [w,h]=ratio.split(':').map(Number);outline.style.width=(20*Math.min(1,w/h))+'px';outline.style.height=(20*Math.min(1,h/w))+'px';b.append(outline,el('span','',ratio));b.setAttribute('aria-pressed',String($('ratio').value===ratio));b.onclick=()=>{change('composer-ratio',ratio,'change');popup.replaceChildren();parameters();position();};ratios.append(b);}popup.append(ratios);
    heading('视觉风格');const style=el('select');style.setAttribute('aria-label','视觉风格');style.replaceChildren(...[...$('composer-style').options].map(o=>o.cloneNode(true)));style.value=$('composer-style').value;style.onchange=()=>change('composer-style',style.value,'change');popup.append(style);
    if(n.kind==='video'){heading('视频时长');const line=el('div','toolbar-duration'),range=el('input'),number=el('input');range.type='range';range.min=number.min=4;range.max=number.max=15;range.step=number.step=.01;number.type='number';range.value=number.value=$('composer-seconds').value;range.setAttribute('aria-label','拖动调整视频时长');number.setAttribute('aria-label','视频时长（秒）');const update=e=>{if(!e.target.checkValidity())return;range.value=number.value=e.target.value;change('composer-seconds',e.target.value);};range.oninput=number.oninput=update;line.append(range,number,el('span','','秒'));popup.append(line);}
    popup.append(el('p','toolbar-note','原生分辨率 · 每次生成 1 个结果'+(n.kind==='video'?' · H3 自动生成声音':'')));
  }
  settingsButton.onclick=()=>open(settingsButton,parameters);
  function caption(b,mark,text){b.replaceChildren(icon(mark),el('span','',text),icon('chevron'));}
  function sync(){const n=board&&selected&&nodeBy(selected),enabled=!!n&&['image','video'].includes(n.kind);composer.classList.toggle('compact-generation',enabled);for(const b of [modelButton,modeButton,settingsButton])b.hidden=!enabled;
    if(nodeId!==n?.id){close();nodeId=n?.id;}if(!enabled)return;
    const m=n.kind==='video'?['Minimax H3','h3']:models[$('composer-model').value]||models.z_image_turbo;caption(modelButton,m[1],m[0]);const refs=doc().edges.some(e=>e.target===n.id&&!['note','reverse','h3prompt'].includes(nodeBy(e.source).kind));caption(modeButton,refs?'image':'text',n.kind==='video'?(refs?'参考图视频':'文生视频'):({edit:'原图重绘',tryon:'换装'}[$('image-task').value]||(refs?'图片参考':'文生图')));caption(settingsButton,'ratio',$('ratio').value+' · 原生'+(n.kind==='video'?' · '+$('seconds').value+'s':'')+' · 1个');
    const advanced=$('composer-advanced');if(advanced.parentElement!==bottom)bottom.insertBefore(advanced,$('composer-generate'));advanced.title='高级参数';advanced.setAttribute('aria-label','高级参数');
    $('composer-generate').title=$('composer-generate').dataset.polishLabel||'开始生成';$('composer-generate').setAttribute('aria-label',$('composer-generate').title);
  }
  const original=inspector;inspector=function(){original();sync();};
  for(const id of ['composer-model','composer-ratio','composer-style','composer-seconds','image-task'])$(id).addEventListener(id==='composer-seconds'?'input':'change',sync);
  window.addEventListener('resize',close);$('viewport').addEventListener('wheel',close,{passive:true});
})();
