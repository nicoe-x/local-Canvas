/* Video refinement is an explicit derivative node; opening/saving never submits GPU work. */
(() => {
  const dialog=el('dialog','result-tool-dialog');dialog.id='video-resample-dialog';
  const form=el('form'),head=el('div','panel-title'),title=el('h2','','视频二次采样'),close=el('button','','关闭');
  close.type='button';close.onclick=()=>dialog.close();head.append(title,close);
  const help=el('p','muted','重新采样整段视频，保留原尺寸、帧数和音轨。降噪越高，画面改动通常越大；人物和动作仍需检查。'),fields=el('div','resample-fields');
  function field(label,type,value){const box=el('label','',label),input=el(type==='textarea'?'textarea':'input');if(type!=='textarea')input.type=type;input.value=value;box.append(input);fields.append(box);return input;}
  const steps=field('采样步数','number',8),denoise=field('降噪强度','number',.25),seed=field('随机种子（留空随机）','number',''),text=field('修改要求（选填）','textarea','');
  steps.min=1;steps.max=32;steps.step=1;steps.required=true;denoise.min=.05;denoise.max=1;denoise.step=.05;denoise.required=true;
  seed.min=0;seed.max=Number.MAX_SAFE_INTEGER;seed.step=1;text.maxLength=30000;text.rows=4;
  const notice=el('p','result-tool-notice');notice.setAttribute('role','status');
  const submit=el('button','primary','创建二采节点');submit.type='submit';
  form.append(head,help,fields,notice,submit);dialog.append(form);document.body.append(dialog);
  let target=null,boardId=null,editing=false;
  window.openVideoResample=(node,edit=false)=>{
    if(!capabilities.video_resample){message('当前生成服务尚未安装视频二采适配器。');return;}
    target=node.id;boardId=board.id;editing=edit;const options=node.settings?.video_resample;
    steps.value=edit?options.steps:8;denoise.value=edit?options.denoise:.25;
    seed.value=edit?(node.settings.seed??''):'';text.value=edit?(node.text||''):'';
    submit.textContent=edit?'保存二采参数':'创建二采节点';notice.textContent='支持24fps、15秒以内的视频。创建后点击节点的生成按钮开始处理。';dialog.showModal();steps.focus();
  };
  form.onsubmit=async event=>{
    event.preventDefault();if(submit.disabled||!form.reportValidity())return;
    const n=Number(steps.value),d=Number(denoise.value),s=seed.value===''?null:Number(seed.value);
    if(!Number.isInteger(n)||n<1||n>32||!Number.isFinite(d)||d<.05||d>1||s!==null&&(!Number.isSafeInteger(s)||s<0)){notice.textContent='请检查步数、降噪强度和种子。';return;}
    submit.disabled=true;
    try{
      if(board?.id!==boardId||!nodeBy(target))throw Error('画布已切换或源节点已移除，请重新选择。');
      if(editing){const node=nodeBy(target);if(busy.has(target)||['QUEUED','STARTING','RUNNING','PENDING','SUBMITTED','PAUSED','RESUMING'].includes(stateOf(node)))throw Error('任务正在处理，完成后才能修改二采参数。');node.settings.video_resample={...node.settings.video_resample,steps:n,denoise:d};node.settings.seed=s;node.text=text.value;touch();render();inspector();}
      else{
        const source=nodeBy(target);if(stateOf(source)!=='COMPLETED_UNREVIEWED')throw Error('请先完成源视频生成。');
        await save();const result=add('video',{title:(source.title.slice(0,60)+' · 二次采样'),x:source.x+390,y:source.y+40,text:text.value,
          settings:{variant:'default',ratio:source.settings?.ratio||'16:9',style:source.settings?.style||'写实',seconds:source.settings?.seconds||5,steps:8,cfg:1,seed:s,video_resample:{source:target,steps:n,denoise:d}}});
        doc().edges.push({source:target,target:result.id});touch();render();inspector();
      }
      await save();dialog.close();message(editing?'二采参数已保存。':'二采节点已创建，点击生成开始处理。');
    }catch(error){notice.textContent=error.message;}finally{submit.disabled=false;}
  };
  const params=el('button','toolbar-trigger','二采参数');params.id='video-resample-parameters';params.type='button';params.hidden=true;
  $('node-composer').querySelector('.composer-bottom').prepend(params);
  params.onclick=()=>{const n=board&&selected&&nodeBy(selected);if(n?.settings?.video_resample)window.openVideoResample(n,true);};
  const prompt=$('composer-prompt'),defaultPlaceholder=prompt.placeholder;
  const old=inspector;inspector=function(){old();const node=board&&selected&&nodeBy(selected),value=node?.settings?.video_resample;params.hidden=!value;document.body.classList.toggle('video-resample-selected',!!value);prompt.placeholder=value?'选填：描述需要改善的画面细节。留空会保留原动作与构图，进行保守二采。':defaultPlaceholder;if(value){params.textContent=`二采 · ${value.steps}步 · 降噪${value.denoise}`;$('model-note').textContent='H3 视频二次采样，尺寸、时长和音轨沿用上游视频；点击“二采参数”修改步数和降噪。';}};
})();
