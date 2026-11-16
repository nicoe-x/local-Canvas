/* Convert on explicit request; generated text stays editable and video jobs remain manual. */
(() => {
  const dialog=el('dialog','h3-prompt-dialog');dialog.id='h3-prompt-dialog';dialog.setAttribute('aria-labelledby','h3-prompt-heading');
  const header=el('div','panel-title'),heading=el('h2','','H3 提示词转换');heading.id='h3-prompt-heading';
  const close=el('button','','关闭');close.type='button';close.onclick=()=>dialog.close();header.append(heading,close);
  const description=el('p','muted','粘贴描述或剧本，转换后先检查，再连接到视频节点。背景音乐、字幕默认关闭。');
  const form=el('form'),source=el('textarea');source.id='h3-source';source.required=true;source.maxLength=30000;source.rows=8;
  source.placeholder='粘贴描述或剧本。对白请用中文引号标明，例如：林薇说：“我马上到。”';
  function field(text,input){const label=el('label','',text);label.append(input);return label;}
  const options=el('div','h3-prompt-options'),seconds=el('input');seconds.type='number';seconds.min='4';seconds.max='90';seconds.step='1';seconds.required=true;seconds.value='10';
  const style=el('select');for(const [value,label] of [['Live-action','真人写实'],['2D animation','二维动画'],['3D Chinese animation','三维国漫'],['Preserve the style explicitly described in the source','遵循原文风格']]){const option=el('option','',label);option.value=value;style.append(option);}
  options.append(field('总时长（4–90秒）',seconds),field('视觉风格',style));
  const references=el('p','fineprint'),privacy=el('p','fineprint','调用部署者配置的文本服务，会发送当前原文和已连接图片的名称，不发送图片。长内容分成多个不超过15秒的片段；引号内台词逐句核对。');
  const submit=el('button','primary','转换为 H3 提示词');submit.type='submit';
  const status=el('p','h3-prompt-status');status.setAttribute('role','status');const results=el('div','h3-prompt-results');
  form.append(field('描述 / 剧本原文',source),options,references,privacy,submit);dialog.append(header,description,form,status,results);document.body.append(dialog);
  let origin=null,canvas=null,referenceIds=[],pending=false;
  function linkedPictures(node){return doc().edges.filter(e=>e.target===node.id).map(e=>nodeBy(e.source)).filter(n=>n&&!['note','reverse','video'].includes(n.kind)&&preview(n));}
  function open(node){
    if(pending){dialog.showModal();return;}
    origin=node.id;canvas=board.id;const saved=node.settings?.h3_prompt;
    source.value=saved?.source??node.text??'';seconds.value=saved?.seconds??node.settings?.seconds??10;style.value=saved?.style||({写实:'Live-action',二维动画:'2D animation','3D国漫':'3D Chinese animation'}[node.settings?.style]||'Live-action');
    const pictures=linkedPictures(node);referenceIds=pictures.map(n=>n.id);
    references.textContent=pictures.length?'Ref2VA · '+pictures.map((n,i)=>`<Picture ${i+1}> → ${n.title}`).join('；')+'。仅按名称说明用途；请在结果中核对人物外观。':'T2VA · 当前节点未连接图片，不会编造参考图标签。';
    status.textContent='';results.replaceChildren();dialog.showModal();source.focus();
  }
  dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
  const originalAdd=add;add=function(kind,extra={}){if(kind!=='h3prompt')return originalAdd(kind,extra);const n=originalAdd('note',{title:'H3 提示词转换',...extra});open(n);return n;};
  const trigger=el('button','composer-tool','H3 提示词');trigger.id='h3-prompt-open';trigger.type='button';trigger.title='将描述或剧本转换成 H3 专用提示词';trigger.onclick=()=>{const node=board&&selected&&nodeBy(selected);if(node)open(node);};
  $('composer-expand').before(trigger);
  const rail=el('button','','H3');rail.title='添加 H3 提示词转换';rail.setAttribute('aria-label',rail.title);rail.onclick=()=>{if(board)add('h3prompt');};document.querySelector('.rail-bottom').before(rail);
  const originalInspector=inspector;inspector=function(){originalInspector();trigger.hidden=!board||!selected||!['note','image','video','reverse'].includes(nodeBy(selected)?.kind);};
  function current(){if(!board||board.id!==canvas||!nodeBy(origin))throw Error('原画布或节点已改变，请重新打开转换窗口');return nodeBy(origin);}
  form.onsubmit=async event=>{
    event.preventDefault();if(pending)return;let node;
    try{node=current();}catch(error){status.textContent=error.message;return;}
    const input={source:source.value,seconds:Number(seconds.value),style:style.value};
    node.settings={...node.settings,h3_prompt:input};touch();pending=true;submit.disabled=true;source.disabled=true;seconds.disabled=true;style.disabled=true;
    status.textContent='正在转换并复检 H3 格式…';results.replaceChildren();
    try{
      await save();const titles=referenceIds.map(id=>{const n=nodeBy(id);if(!n)throw Error('参考素材已移除，请重新打开转换窗口');return n.title;});
      const result=await api('/prompts/h3',json('POST',{...input,references:titles}));current();
      status.textContent=`已完成 ${result.segments.length} 段 · ${result.model} · 格式校验通过，剧情和画面仍需检查。`;
      let start=0;
      for(const [index,segment] of result.segments.entries()){
        const section=el('section','h3-prompt-result'),title=el('h3','',`片段 ${index+1} · ${start}–${start+segment.seconds}秒`),output=el('textarea');start+=segment.seconds;
        output.value=segment.prompt;output.rows=10;output.setAttribute('aria-label',`片段 ${index+1} H3 提示词，可编辑`);
        const actions=el('div','h3-prompt-actions'),copy=el('button','','复制提示词'),insert=el('button','','加入画布'),video=el('button','primary','加入画布并连接视频节点');
        for(const button of [copy,insert,video])button.type='button';
        copy.onclick=async()=>{try{await navigator.clipboard.writeText(output.value);status.textContent='提示词已复制';}catch{output.focus();output.select();status.textContent='请按 Ctrl+C 复制选中的提示词';}};
        function place(withVideo){
          try{
            const base=current();if(doc().nodes.length+(withVideo?2:1)>200)throw Error('画布节点数量已达上限');
            if(referenceIds.some(id=>!nodeBy(id)))throw Error('参考素材已移除，请重新转换');
            const text=add('note',{title:`H3 提示词 ${index+1}`,text:output.value,x:base.x+380,y:base.y+index*370});
            if(withVideo){const videoSettings={...base.settings};if(base.kind!=='video')delete videoSettings.variant;const target=add('video',{title:`H3 视频 ${index+1}`,text:'',x:base.x+760,y:base.y+index*370,settings:{...videoSettings,seconds:segment.seconds,ratio:base.settings?.ratio||'16:9',style:'自定义风格'}});delete target.settings.h3_prompt;
              doc().edges.push({source:text.id,target:target.id},...referenceIds.map(id=>({source:id,target:target.id})));
            }
            touch();render();inspector();insert.disabled=true;video.disabled=true;status.textContent='已加入画布；尚未生成视频。请为视频节点选择 H3 工作流并检查参考图片顺序。';
          }catch(error){status.textContent=error.message;}
        }
        insert.onclick=()=>place(false);video.onclick=()=>place(true);actions.append(copy,insert,video);section.append(title,output,actions);results.append(section);
      }
    }catch(error){status.textContent=error.message;}
    finally{pending=false;submit.disabled=false;source.disabled=false;seconds.disabled=false;style.disabled=false;}
  };
})();
