/* Whole-card movement, type-based default names, and direct title editing. */
(() => {
  const nodes=$('nodes'),viewport=$('viewport'),sequences=new Map();
  const labels={h3prompt:'H3提示词节点',image:'图片节点',video:'视频节点',note:'文本节点',asset:'资源节点',reverse:'图片反推节点',stage3d:'3D导演台节点'};
  const originalAdd=add;
  add=function(kind,extra={}){
    if(!board)return originalAdd(kind,extra);
    const label=labels[kind]||'节点',key=board.id+':'+kind;
    const same=doc().nodes.filter(n=>n.kind===kind);
    const highest=same.reduce((max,n)=>{const suffix=n.title?.startsWith(label)?Number(n.title.slice(label.length)):0;return Number.isSafeInteger(suffix)?Math.max(max,suffix):max;},0);
    const next=Math.max(sequences.get(key)||0,highest,same.length)+1;
    sequences.set(key,next);
    return originalAdd(kind,{...extra,title:label+next});
  };
  let gesture=null,suppressClick=false;
  nodes.addEventListener('pointerdown',event=>{
    const card=event.target.closest('.card');
    if(!board||!card||event.button!==0||event.target.closest('button,input,textarea,select,a,[contenteditable=true]')||viewport.classList.contains('hand-mode'))return;
    // Keep the native video control strip interactive while allowing its picture to move the node.
    const video=event.target.closest('video');if(video&&event.clientY>video.getBoundingClientRect().bottom-44)return;
    event.preventDefault();event.stopPropagation();
    const node=nodeBy(card.dataset.id);if(!node)return;
    if(event.target.closest('.card-head'))select(node.id);
    const picked=window.H3Selection?.ids()||[],ids=picked.includes(node.id)?picked:[node.id];
    gesture={pointer:event.pointerId,id:node.id,board:board.id,startX:event.clientX,startY:event.clientY,x:node.x,y:node.y,moved:false,positions:ids.map(id=>({id,x:nodeBy(id).x,y:nodeBy(id).y}))};
  },true);
  document.addEventListener('pointermove',event=>{
    if(!gesture||event.pointerId!==gesture.pointer)return;
    if(board?.id!==gesture.board||!nodeBy(gesture.id)){finish();return;}
    if(!gesture.moved&&Math.hypot(event.clientX-gesture.startX,event.clientY-gesture.startY)<4)return;
    if(!gesture.moved){if(gesture.positions.length===1)select(gesture.id);viewport.setPointerCapture(event.pointerId);}
    gesture.moved=true;dragging={type:'node',...gesture};
    if(gesture.positions.length===1)move(event);
    else{const dx=(event.clientX-gesture.startX)/doc().viewport.zoom,dy=(event.clientY-gesture.startY)/doc().viewport.zoom;for(const original of gesture.positions){const node=nodeBy(original.id);if(!node)continue;node.x=Math.max(-100000,Math.min(100000,original.x+dx));node.y=Math.max(-100000,Math.min(100000,original.y+dy));const card=nodes.querySelector(`[data-id="${node.id}"]`);if(card){card.style.left=node.x+'px';card.style.top=node.y+'px';}}renderEdges();}
    window.H3Selection?.refresh?.();event.preventDefault();event.stopImmediatePropagation();
  },true);
  function finish(){
    if(!gesture)return;
    const value=gesture;gesture=null;
    if(value.moved){endDrag();suppressClick=true;setTimeout(()=>suppressClick=false,0);}
    if(viewport.hasPointerCapture(value.pointer))viewport.releasePointerCapture(value.pointer);
  }
  document.addEventListener('pointerup',finish,true);
  viewport.addEventListener('pointercancel',finish);viewport.addEventListener('lostpointercapture',finish);window.addEventListener('blur',finish);
  document.addEventListener('click',event=>{if(suppressClick){event.preventDefault();event.stopImmediatePropagation();suppressClick=false;}},true);
  async function rename(id){
    const node=board&&nodeBy(id);if(!node)return;
    const d=$('canvas-name-dialog'),input=$('canvas-name');if(d.open)return;
    d.querySelector('h2').textContent='重命名节点';input.value=node.title;d.returnValue='';d.showModal();input.focus();input.select();
    const key=board.id;
    d.addEventListener('close',()=>{
      if(d.returnValue!=='save'||board?.id!==key||!nodeBy(id))return;
      const title=input.value.trim();if(!title)return;
      nodeBy(id).title=title;touch();render();inspector();save().catch(e=>message(e.message));
    },{once:true});
  }
  nodes.addEventListener('dblclick',event=>{const title=event.target.closest('.card-head strong');if(!title)return;event.preventDefault();event.stopPropagation();rename(title.closest('.card').dataset.id);});
  const originalRender=render;
  render=function(){originalRender();for(const title of nodes.querySelectorAll('.card-head strong')){title.title='双击重命名';title.tabIndex=0;title.setAttribute('role','button');title.setAttribute('aria-label','重命名 '+title.textContent);title.onkeydown=event=>{if(event.key==='Enter'||event.key==='F2'){event.preventDefault();rename(title.closest('.card').dataset.id);}};}for(const image of nodes.querySelectorAll('img'))image.draggable=false;};
})();
