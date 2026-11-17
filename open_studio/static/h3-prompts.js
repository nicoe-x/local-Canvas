/* Native H3 conversion nodes. Input and output are deliberately separate. */
(() => {
  const panel=el('section','h3-prompt-dialog h3-prompt-panel');panel.id='h3-prompt-dialog';panel.hidden=true;
  const head=el('div','panel-title'),heading=el('h2','','H3 提示词节点'),close=el('button','','收起');close.type='button';close.onclick=()=>{panel.hidden=true;hiddenNode=selected;editorNode=null;};head.append(heading,close);
  const form=el('form'),source=el('textarea');source.id='h3-source';source.maxLength=30000;source.rows=5;source.required=true;
  source.placeholder='输入描述或剧本，对白用中文引号标明。也可以连入文本节点。';
  const seconds=el('input');seconds.type='number';seconds.min='4';seconds.max='90';seconds.step='1';seconds.value='10';seconds.required=true;
  const style=el('select');for(const [value,title] of [['Live-action','真人写实'],['2D animation','二维动画'],['3D Chinese animation','三维国漫'],['Preserve the style explicitly described in the source','遵循原文风格']]){const option=el('option','',title);option.value=value;style.append(option);}
  function field(title,input){const label=el('label','',title);label.append(input);return label;}
  const options=el('div','h3-prompt-options');options.append(field('总时长（4–90秒）',seconds),field('视觉风格',style));
  const refs=el('p','fineprint'),hint=el('p','fineprint','转换不生成视频；默认无背景音乐、无字幕。参考图片只读取名称。'),run=el('button','primary','转换为 H3 提示词');run.type='submit';
  const status=el('p','h3-prompt-status');status.setAttribute('role','status');const results=el('div','h3-prompt-results');
  form.append(field('描述 / 剧本原文',source),options,refs,hint,run);panel.append(head,form,status,results);$('viewport').append(panel);
  for(const event of ['pointerdown','wheel','dblclick'])panel.addEventListener(event,e=>e.stopPropagation());
  let shown=null,hiddenNode=null,requestNode=null,editorNode=null;
  const errors=new Map();
  function pictures(node){return doc().edges.filter(e=>e.target===node.id).map(e=>nodeBy(e.source)).filter(n=>n&&!['note','reverse','h3prompt','video'].includes(n.kind)&&preview(n));}
  function defaults(node){return node.settings.h3_prompt||{source:'',seconds:10,style:'Live-action'};}
  function current(){const n=board&&selected&&nodeBy(selected);return n?.kind==='h3prompt'?n:null;}
  function invalidate(node){node.text='';delete node.settings.h3_result;errors.set(node.id,'输入已更新，请重新转换');}
  function saveInput(){const n=current();if(!n)return;const old=defaults(n),next={source:source.value,seconds:Number(seconds.value),style:style.value};if(!Number.isInteger(next.seconds)||next.seconds<4||next.seconds>90)return;if(JSON.stringify(old)!==JSON.stringify(next)){n.settings.h3_prompt=next;invalidate(n);touch();paintCards();status.textContent=errors.get(n.id);results.replaceChildren();}}
  source.oninput=saveInput;seconds.oninput=saveInput;style.onchange=saveInput;
  function selectOutput(node,index){const result=node.settings.h3_result;result.selected=index;node.text=result.segments[index].prompt;for(const edge of doc().edges.filter(e=>e.source===node.id)){const target=nodeBy(edge.target);if(target?.kind==='video')target.settings.seconds=result.segments[index].seconds;}touch();shown=null;render();inspector();}
  function fillResults(node){
    results.replaceChildren();const data=node.settings.h3_result;if(!data)return;
    for(const [index,part] of data.segments.entries()){
      const section=el('section','h3-prompt-result'),title=el('h3','',`片段 ${index+1} · ${part.seconds}秒`),output=el('textarea');output.rows=5;output.value=part.prompt;output.setAttribute('aria-label',`片段 ${index+1} H3 提示词，可编辑`);
      output.oninput=()=>{part.prompt=output.value;if(data.selected===index)node.text=output.value;touch();paintCards();};
      const actions=el('div','h3-prompt-actions'),choose=el('button','',data.selected===index?'当前输出':'设为当前输出'),video=el('button','','创建此段视频节点');choose.type=video.type='button';choose.onclick=()=>selectOutput(node,index);
      video.onclick=()=>{
        if(!board||!doc().nodes.includes(node))return;
        if(doc().nodes.length+(data.segments.length===1?1:2)>200){message('节点数量已达上限');return;}
        if(data.references.some(id=>!nodeBy(id))){message('参考图已移除，请重新转换');return;}
        let textNode=node;
        if(data.segments.length>1)textNode=add('note',{text:part.prompt,title:`${node.title} · 片段${index+1}`,x:node.x+380,y:node.y+index*320});
        else selectOutput(node,0);
        const settings={seconds:part.seconds,ratio:node.settings.ratio||'16:9',style:({'Live-action':'写实','2D animation':'二维动画','3D Chinese animation':'3D国漫'})[defaults(node).style]||'写实'};
        const target=add('video',{text:'',x:textNode.x+380,y:textNode.y,settings});doc().edges.push({source:textNode.id,target:target.id},...data.references.map(id=>({source:id,target:target.id})));touch();render();inspector();message('视频节点已连接，尚未启动生成');
      };
      actions.append(choose,video);section.append(title,output,actions);results.append(section);
    }
  }
  function sync(){
    const n=current();if(!n){panel.hidden=true;shown=null;return;}
    if(hiddenNode===n.id||editorNode!==n.id||document.body.classList.contains('canvas-wiring')){panel.hidden=true;return;}panel.hidden=false;
    heading.textContent=n.title;
    if(shown!==n.id){shown=n.id;const input=defaults(n);source.value=input.source;seconds.value=input.seconds;style.value=input.style;fillResults(n);}
    const imageNodes=pictures(n),texts=doc().edges.filter(e=>e.target===n.id&&['note','reverse','h3prompt'].includes(nodeBy(e.source)?.kind));
    refs.textContent=`${imageNodes.length?'Ref2VA':'T2VA'} · ${texts.length} 条上游文本 · `+(imageNodes.map((item,i)=>`<Picture ${i+1}> → ${item.title}`).join('；')||'无参考图片');
    run.disabled=requestNode!==null;source.disabled=seconds.disabled=style.disabled=requestNode===n.id;
    run.textContent=requestNode===n.id?'本地 Qwen 转换中…':'转换为 H3 提示词';
    status.textContent=requestNode===n.id?'转换中，完成后结果保存在此节点。':errors.get(n.id)||(n.settings.h3_result?`共 ${n.settings.h3_result.segments.length} 段 · 输出片段 ${n.settings.h3_result.selected+1} · 可从右侧连到视频节点`:'填写原文或连接上游文本，再开始转换。');
    position();
  }
  function position(){if(panel.hidden)return;const card=$('nodes').querySelector(`[data-id="${shown}"]`);if(!card)return;const r=card.getBoundingClientRect(),v=$('viewport').getBoundingClientRect(),width=Math.min(700,v.width-24);panel.style.width=width+'px';panel.style.left=Math.max(12,Math.min(r.left-v.left+(r.width-width)/2,v.width-width-12))+'px';const below=v.bottom-r.bottom-30,above=r.top-v.top-30,useBelow=below>=260||below>=above,room=Math.max(180,Math.min(v.height*.65,useBelow?below:above));panel.style.maxHeight=room+'px';panel.style.top=Math.max(12,Math.min(useBelow?r.bottom-v.top+18:r.top-v.top-18-Math.min(panel.offsetHeight,room),v.height-Math.min(panel.offsetHeight,room)-12))+'px';}

  const originalView=view;view=function(){originalView();position();};
  function follow(){if(!panel.hidden&&dragging)position();requestAnimationFrame(follow);}requestAnimationFrame(follow);
  function paintCards(){if(!board)return;for(const card of $('nodes').children){const n=nodeBy(card.dataset.id);if(n?.kind!=='h3prompt')continue;card.classList.add('h3-conversion-node');const body=card.querySelector('.card-body');body.replaceChildren();const tag=el('small','h3-node-label','描述 / 剧本 → H3 提示词');const preview=el('p','card-text',n.text?n.text.slice(0,420):(defaults(n).source||'连接文本或输入剧本，转换为 H3 专用提示词。').slice(0,180));preview.dataset.selectableText='true';preview.addEventListener('click',e=>e.stopPropagation());preview.addEventListener('dblclick',e=>e.stopPropagation());body.append(tag,preview);if(n.text){const copy=el('button','','复制完整提示词');copy.type='button';copy.className='h3-copy-output';copy.onclick=async()=>{try{await copyText(n.text);message('已复制当前片段的完整提示词');}catch{message('复制失败，请在编辑区选中完整提示词后按 Ctrl+C');}};body.append(copy);}
    const data=n.settings.h3_result;if(data){const choices=el('select');choices.setAttribute('aria-label','选择节点输出片段');for(const [index,part] of data.segments.entries()){const option=el('option','',`输出片段 ${index+1} · ${part.seconds}秒`);option.value=index;choices.append(option);}choices.value=data.selected;choices.onchange=()=>selectOutput(n,Number(choices.value));body.append(choices);}
    const edit=el('button','',requestNode===n.id?'正在转换…':'编辑 / 转换');edit.type='button';edit.onclick=()=>{hiddenNode=null;editorNode=n.id;select(n.id);shown=null;sync();};body.append(edit);
  }}
  const originalRender=render;render=function(){originalRender();paintCards();renderEdges();position();};
  const originalInspector=inspector;inspector=function(){originalInspector();sync();};
  const originalAdd=add;add=function(kind,extra={}){const n=originalAdd(kind,extra);if(kind==='h3prompt'){hiddenNode=null;editorNode=n.id;shown=null;sync();}return n;};
  const trigger=el('button','composer-tool','H3 提示词节点');trigger.id='h3-prompt-open';trigger.type='button';trigger.onclick=()=>{if(!board||!selected)return;const base=nodeBy(selected),n=add('h3prompt',{x:base.x+380,y:base.y,settings:{h3_prompt:{source:base.text||'',seconds:Math.round(base.settings?.seconds||10),style:'Live-action'}}});if(['note','reverse'].includes(base.kind))doc().edges.push({source:base.id,target:n.id});else for(const pic of pictures(base))doc().edges.push({source:pic.id,target:n.id});touch();render();sync();};$('composer-expand').before(trigger);
  const rail=el('button','','H3');rail.title='添加 H3 提示词节点';rail.setAttribute('aria-label',rail.title);rail.onclick=()=>{if(board)add('h3prompt');};document.querySelector('.rail-bottom').before(rail);
  form.onsubmit=async event=>{
    event.preventDefault();if(requestNode)return;const node=current();if(!node)return;saveInput();const canvas=board.id,input={...defaults(node)},refsNow=pictures(node),ids=refsNow.map(n=>n.id);
    const upstream=doc().edges.filter(e=>e.target===node.id).map(e=>nodeBy(e.source)).filter(n=>['note','reverse','h3prompt'].includes(n?.kind)).map(n=>n.text?.trim()).filter(Boolean);
    // Do not duplicate a source copied from an upstream text node.
    const text=[...new Set([...upstream,input.source.trim()].filter(Boolean))].join('\n\n');if(!text){status.textContent='请输入原文或连接已有文本';return;}
    invalidate(node);requestNode=node.id;busy.add(node.id);errors.delete(node.id);render();sync();
    try{await save();const result=await api('/prompts/h3',json('POST',{...input,source:text,references:refsNow.map(n=>n.title)}));if(board?.id!==canvas||!doc().nodes.includes(node))throw Error('原画布已切换，请回到原节点重新转换');
      if(JSON.stringify(ids)!==JSON.stringify(pictures(node).map(n=>n.id)))throw Error('参考图连线已改变，请重新转换');
      node.settings.h3_result={segments:result.segments,selected:0,model:result.model,references:ids,input_source:text};node.text=result.segments[0].prompt;touch();await save();shown=null;
    }catch(error){errors.set(node.id,error.message);}
    finally{requestNode=null;busy.delete(node.id);render();sync();}
  };
  async function copyText(text){
    try{if(!navigator.clipboard?.writeText)throw Error('clipboard unavailable');await navigator.clipboard.writeText(text);return;}catch{}
    const input=el('textarea');input.value=text;input.readOnly=true;input.style.cssText='position:fixed;left:0;top:0;opacity:0;pointer-events:none';const active=document.activeElement;document.body.append(input);input.select();try{if(!document.execCommand('copy'))throw Error('copy failed');}finally{input.remove();active?.focus({preventScroll:true});}
  }
  document.addEventListener('pointerdown',event=>{if(event.target.closest('.port')){editorNode=null;panel.hidden=true;}},true);
  window.addEventListener('resize',position);
})();
