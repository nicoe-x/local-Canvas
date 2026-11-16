/* Inspect a node in canvas space; preview original media in a separate lightbox. */
(() => {
  const viewport=$('viewport'),dialog=$('media-dialog'),content=$('media-content');
  let focused=null,previousView=null,focusRequest=0,previewNumber=0,selectTimer=0;
  const bar=el('div','node-focus-actions');bar.hidden=true;
  const caption=el('span'),back=el('button','','返回画布'),edit=el('button','','编辑节点'),large=el('button','','放大预览');
  back.type=edit.type=large.type='button';bar.append(caption,back,edit,large);viewport.append(bar);
  function exit(restore=true){
    cancelAnimationFrame(focusRequest);focused=null;document.body.classList.remove('node-focus-mode');bar.hidden=true;
    if(restore&&previousView&&board){doc().viewport={...previousView};view();touch();}
    previousView=null;
  }
  function focus(id){
    const node=nodeBy(id);if(!node)return;
    if(!focused)previousView={...doc().viewport};
    focused=id;document.body.classList.add('node-focus-mode');select(id);bar.hidden=false;caption.textContent=node.title;
    large.hidden=!preview(node)||stateOf(node)!=='COMPLETED_UNREVIEWED';
    cancelAnimationFrame(focusRequest);focusRequest=requestAnimationFrame(()=>{
      const body=$('nodes').querySelector(`[data-id="${id}"] .card-body`);if(!body||focused!==id)return;
      const r=viewport.getBoundingClientRect(),card=body.closest('.card'),n=nodeBy(id),v=doc().viewport;
      const w=body.offsetWidth,h=body.offsetHeight;
      v.zoom=Math.max(.15,Math.min(8,(r.width-100)/Math.max(w,1),(r.height-160)/Math.max(h,1)));
      v.x=r.width/2-(n.x+body.offsetLeft+w/2)*v.zoom;
      v.y=(r.height-10)/2-(n.y+body.offsetTop+h/2)*v.zoom;
      const video=body.querySelector('video');if(video&&video.readyState<1){video.preload='metadata';video.load();}
      view();touch();
    });
  }
  bar.addEventListener('pointerdown',e=>e.stopPropagation());bar.addEventListener('dblclick',e=>e.stopPropagation());
  back.onclick=()=>exit();edit.onclick=()=>{const id=focused;exit();if(id&&nodeBy(id))select(id);};
  large.onclick=()=>{const node=focused&&nodeBy(focused);if(node)showMedia(node);};
  // Defer plain body selection briefly so the fixed editor cannot cover the
  // second click. Modified clicks retain the existing multi-select semantics.
  function plainBody(event){return !viewport.classList.contains('hand-mode')&&event.target.closest('.card-body')&&!event.target.closest('button,input,textarea,select,a,video')&&!event.altKey&&!event.ctrlKey&&!event.metaKey&&!event.shiftKey;}
  document.addEventListener('pointerdown',()=>clearTimeout(selectTimer),true);
  document.addEventListener('click',event=>{
    if(!plainBody(event))return;
    event.preventDefault();event.stopImmediatePropagation();clearTimeout(selectTimer);
    if(event.detail===1){const key=board.id,id=event.target.closest('.card').dataset.id;selectTimer=setTimeout(()=>{if(board?.id===key&&nodeBy(id))select(id);},320);}
  },true);
  viewport.addEventListener('dblclick',event=>{
    const body=event.target.closest('.card-body');if(!body||event.target.closest('button,input,textarea,select,a'))return;
    clearTimeout(selectTimer);event.preventDefault();event.stopImmediatePropagation();focus(body.closest('.card').dataset.id);
  },true);
  // Preview/edit controls intentionally leave canvas inspection mode.
  viewport.addEventListener('click',event=>{if(focused&&event.target.closest('.card-foot button'))exit(false);},true);
  window.addEventListener('keydown',event=>{if(event.key==='Escape'&&focused&&!dialog.open&&!event.target.closest('dialog,input,textarea,select')){exit();}},true);
  const oldView=view;view=function(){oldView();if(focused)document.body.style.setProperty('--focus-zoom',doc().viewport.zoom);};
  const oldInspector=inspector,oldOpen=openBoard;
  inspector=function(){if(focused&&selected!==focused)exit(false);oldInspector();};
  openBoard=async function(key){exit(false);return oldOpen(key);};

  dialog.classList.add('canvas-lightbox');dialog.setAttribute('aria-label','原始媒体放大预览');
  const info=el('span','lightbox-info'),fit=el('button','','适应窗口'),native=el('button','','原图 1:1');
  fit.type=native.type='button';const controls=el('div','lightbox-controls');controls.append(info,fit,native,$('media-download'));
  dialog.append(controls);$('media-close').setAttribute('aria-label','关闭放大预览');
  fit.onclick=()=>{dialog.classList.remove('lightbox-native');fit.setAttribute('aria-pressed','true');native.setAttribute('aria-pressed','false');};
  native.onclick=()=>{dialog.classList.add('lightbox-native');fit.setAttribute('aria-pressed','false');native.setAttribute('aria-pressed','true');};
  showMedia=function(node){
    const video=node.kind==='video',url=video?'/api/jobs/'+jobOf(node)+'/video':preview(node);if(!url)return;
    const serial=++previewNumber;content.replaceChildren();$('media-title').textContent=node.title;info.textContent='正在加载…';native.hidden=video;fit.click();
    const media=el(video?'video':'img');media.src=url;
    if(video){media.controls=true;media.preload='metadata';media.onloadedmetadata=()=>{if(serial===previewNumber)info.textContent=`${media.videoWidth} × ${media.videoHeight} · ${media.duration.toFixed(2)} 秒`;};}
    else{media.alt=node.title;media.onload=()=>{if(serial===previewNumber)info.textContent=`${media.naturalWidth} × ${media.naturalHeight}`;};}
    media.onerror=()=>{if(serial===previewNumber)info.textContent='媒体加载失败，请返回节点核对生成结果';};
    content.append(media);$('media-download').href=url+(jobOf(node)?'?download=true':'');$('media-download').textContent=video?'下载视频':'下载原图';
    if(!dialog.open)dialog.showModal();$('media-close').focus();
  };
  dialog.addEventListener('click',event=>{if(event.target===dialog||event.target===content)dialog.close();});
  dialog.addEventListener('close',()=>{previewNumber++;content.querySelector('video')?.pause();content.replaceChildren();});
  const help=$('help-dialog').querySelector('form');
  for(const p of help.querySelectorAll('p'))p.textContent=p.textContent.replaceAll('滚轮缩放','Ctrl+滚轮缩放').replaceAll('滚轮或触控板双指缩放','普通滚轮上下平移，Ctrl+滚轮缩放').replaceAll('滚轮或触控板双指：缩放','普通滚轮上下平移；Ctrl+滚轮：缩放');
  help.insertBefore(el('p','','双击节点画面：自动居中并放大。放大预览：以遮罩查看原图或播放视频。画布缩放范围15%–800%。'),help.lastElementChild);
  viewport.setAttribute('aria-label','无限创作画布。滚轮上下移动，Ctrl加滚轮缩放；双击节点画面居中放大，中键平移。');
})();
