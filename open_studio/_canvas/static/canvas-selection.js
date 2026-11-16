/* Default left button selects. Middle/hand pans; Alt+left explicitly moves nodes. */
(() => {
  const viewport=$('viewport'),nodes=$('nodes'),world=$('world'),picks=new Set();let gesture=null,frame=0,boardKey=null,undo=null,groupMode=null;
  document.body.classList.add('marquee-selection-mode');
  const groups=el('div','canvas-groups');groups.id='canvas-groups';world.prepend(groups);
  const marquee=el('div','canvas-marquee');marquee.id='canvas-marquee';marquee.hidden=true;viewport.append(marquee);
  const outline=el('div','selection-outline');outline.hidden=true;viewport.append(outline);
  const toolbar=el('div','selection-toolbar');toolbar.id='selection-toolbar';toolbar.hidden=true;toolbar.setAttribute('role','toolbar');toolbar.setAttribute('aria-label','多选操作');viewport.append(toolbar);
  const count=el('span','selection-count');toolbar.append(count);
  function btn(id,text,fn){const b=el('button','',text);b.id=id;b.type='button';const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',({'selection-copy':'M8 8h12v12H8zM4 16H3V3h13v1','selection-group':'M3 8V3h5m8 0h5v5M3 16v5h5m8 0h5v-5','selection-ungroup':'M8 3v5H3m18 0h-5V3M3 16h5v5m8 0v-5h5','selection-download':'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5','selection-delete':'M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7'})[id]);svg.append(path);b.prepend(svg);b.onclick=async()=>{try{await fn();}catch(e){message(e.message);}};toolbar.append(b);return b;}
  const copy=btn('selection-copy','创建副本',copySelection),group=btn('selection-group','打组',makeGroup),ungroup=btn('selection-ungroup','取消分组',ungroupSelection),download=btn('selection-download','批量下载',downloadSelection),remove=btn('selection-delete','删除',deleteSelection);
  toolbar.addEventListener('pointerdown',e=>e.stopPropagation());toolbar.addEventListener('dblclick',e=>e.stopPropagation());
  function currentIds(){return [...picks].filter(id=>board&&nodeBy(id));}
  function cleanGroups(){if(doc().groups)doc().groups=doc().groups.map(g=>({...g,node_ids:g.node_ids.filter(id=>nodeBy(id))})).filter(g=>g.node_ids.length);}
  function bounds(ids){const boxes=ids.map(id=>nodes.querySelector(`[data-id="${id}"]`)?.getBoundingClientRect()).filter(Boolean);if(!boxes.length)return null;return {left:Math.min(...boxes.map(r=>r.left)),top:Math.min(...boxes.map(r=>r.top))-28,right:Math.max(...boxes.map(r=>r.right)),bottom:Math.max(...boxes.map(r=>r.bottom))+18};}
  function paint(){
    if(!board){picks.clear();toolbar.hidden=outline.hidden=true;groups.replaceChildren();return;}
    if(boardKey!==board.id){picks.clear();groupMode=null;boardKey=board.id;undo=null;}
    for(const id of picks)if(!nodeBy(id))picks.delete(id);
    for(const card of nodes.children)card.classList.toggle('multi-selected',picks.has(card.dataset.id));
    const ids=currentIds(),r=bounds(ids),v=viewport.getBoundingClientRect(),multi=ids.length>1||!!groupMode;
    toolbar.hidden=outline.hidden=!multi||!r;
    if(multi&&r){const left=Math.max(8,r.left-v.left-12),top=Math.max(8,r.top-v.top-12);outline.style.left=left+'px';outline.style.top=top+'px';outline.style.width=Math.max(0,r.right-v.left-left+12)+'px';outline.style.height=Math.max(0,r.bottom-v.top-top+12)+'px';count.textContent=`已选 ${ids.length} 项`;toolbar.style.maxWidth=(v.width-20)+'px';toolbar.style.left=Math.max(10,Math.min(v.width-toolbar.offsetWidth-10,left))+'px';toolbar.style.top=Math.max(8,top-toolbar.offsetHeight-10)+'px';}
    $('canvas-undo').disabled=!(undo&&undo.key===board.id&&undo.serial===changeNo);group.disabled=ids.length<2;ungroup.disabled=!(doc().groups||[]).some(g=>g.node_ids.some(id=>picks.has(id)));drawGroups();
  }
  function schedule(){if(!frame)frame=requestAnimationFrame(()=>{frame=0;paint();});}
  const originalSelect=select;
  function apply(ids,groupId=null){picks.clear();for(const id of ids)if(nodeBy(id))picks.add(id);groupMode=groupId;originalSelect(picks.size===1?[...picks][0]:null);schedule();}
  select=function(id){if(!board)return;apply(id?[id]:[]);};
  function drawGroups(){
    if(!board){groups.replaceChildren();return;}
    const wanted=new Set((doc().groups||[]).map(g=>g.id));for(const box of [...groups.children])if(!wanted.has(box.dataset.groupId))box.remove();
    for(const g of doc().groups||[]){const items=g.node_ids.map(nodeBy).filter(Boolean);if(!items.length)continue;const x=Math.min(...items.map(n=>n.x))-24,y=Math.min(...items.map(n=>n.y))-61,right=Math.max(...items.map(n=>n.x+(nodes.querySelector(`[data-id="${n.id}"]`)?.offsetWidth||290)))+24,bottom=Math.max(...items.map(n=>n.y+(nodes.querySelector(`[data-id="${n.id}"]`)?.offsetHeight||240)))+35;
      let box=groups.querySelector('[data-group-id=\"'+g.id+'\"]');if(!box){box=el('div','canvas-group');box.dataset.groupId=g.id;const title=el('button','canvas-group-title');title.type='button';title.dataset.groupId=g.id;title.title='点击选择分组；双击改名；Alt+拖动移动分组';title.ondblclick=e=>{e.preventDefault();e.stopPropagation();renameGroup(g.id);};box.append(title);groups.append(box);}Object.assign(box.style,{left:x+'px',top:y+'px',width:right-x+'px',height:bottom-y+'px'});box.querySelector('button').textContent=g.title+' · '+items.length;
    }
  }
  async function renameGroup(id){const g=(doc().groups||[]).find(g=>g.id===id);if(!g)return;const d=$('canvas-name-dialog'),input=$('canvas-name');if(d.open)return;d.querySelector('h2').textContent='重命名分组';input.value=g.title;d.returnValue='';d.showModal();const key=board.id;d.addEventListener('close',()=>{if(board?.id===key&&d.returnValue==='save'&&input.value.trim()){g.title=input.value.trim();touch();schedule();}},{once:true});input.focus();input.select();}
  function makeGroup(){const ids=currentIds();if(ids.length<2)return;const existing=doc().groups||[];if(existing.length>=100)throw Error('最多100个分组');doc().groups=existing.map(g=>({...g,node_ids:g.node_ids.filter(id=>!picks.has(id))})).filter(g=>g.node_ids.length);const title='分组'+(Math.max(0,...existing.map(g=>Number(g.title.match(/^分组(\d+)$/)?.[1]||0)))+1),g={id:uid(),title,node_ids:ids};doc().groups.push(g);touch();groupMode=g.id;schedule();}
  function ungroupSelection(){if(!board)return;doc().groups=(doc().groups||[]).filter(g=>!g.node_ids.some(id=>picks.has(id)));groupMode=null;touch();schedule();}
  async function deleteSelection(){return H3TrashMutation(async()=>{const ids=currentIds();if(!ids.length)return;if(ids.some(id=>busy.has(id)))throw Error('节点仍在处理');const key=board.id;await save();const result=await api(`/canvases/${key}/trash`,json('POST',{revision:board.revision,node_ids:ids,request_id:uid()}));if(board?.id===key){board=result.board;dirty=false;changeNo++;undo={key,serial:changeNo,ids,trashId:result.trash_id};apply([]);render();inspector();}message(`已移入回收站 ${ids.length} 个节点，可在回收站恢复或彻底删除。`);});}
  removeNode=function(){if(!picks.size&&selected)apply([selected]);return deleteSelection();};
  async function restore(){return H3TrashMutation(async()=>{if(!undo||board?.id!==undo.key)return false;await save();const value=undo,result=await api(`/canvas-trash/${value.trashId}/restore`,json('POST',{}));undo=null;if(board?.id===value.key){board=result;dirty=false;changeNo++;render();apply(value.ids);inspector();}message('已恢复节点和连线');return true;});}
  function copySelection(){const ids=currentIds();if(!ids.length)return;if(doc().nodes.length+ids.length>200)throw Error('复制后会超过200个节点');const source=doc().nodes.filter(n=>picks.has(n.id)),mapping=new Map(source.map(n=>[n.id,uid()])),edges=doc().edges.filter(e=>picks.has(e.source)&&picks.has(e.target));if(doc().edges.length+edges.length>400)throw Error('复制后会超过400条连线');for(const n of source){const value=structuredClone(n);value.id=mapping.get(n.id);value.x=Math.min(100000,n.x+60);value.y=Math.min(100000,n.y+80);value.title=(n.title+' 副本').slice(0,80);const job=jobOf(n);if(job&&stateOf(n)==='COMPLETED_UNREVIEWED')value.job_id=job;else delete value.job_id;doc().nodes.push(value);}doc().edges.push(...edges.map(e=>({source:mapping.get(e.source),target:mapping.get(e.target)})));const copies=(doc().groups||[]).filter(g=>g.node_ids.every(id=>picks.has(id))).map(g=>({id:uid(),title:(g.title+' 副本').slice(0,80),node_ids:g.node_ids.map(id=>mapping.get(id))}));if((doc().groups||[]).length+copies.length<=100&&copies.length)doc().groups.push(...copies);touch();render();apply([...mapping.values()]);inspector();}
  $('duplicate').onclick=()=>{try{copySelection();}catch(e){message(e.message);}};
  $('remove-node').onclick=()=>removeNode().catch(e=>message(e.message));
  async function downloadSelection(){const ids=currentIds(),key=board?.id;if(!ids.length)return;download.disabled=true;try{await save();const result=await api(`/canvases/${key}/download-selection`,json('POST',{node_ids:ids}));const a=el('a');a.href=result.url;a.download='选中素材.zip';document.body.append(a);a.click();a.remove();message(`已打包 ${result.files} 个文件`+(result.skipped?`，跳过 ${result.skipped} 个未完成节点`:'')+'。');}finally{download.disabled=false;}}
  function editable(target){return target.closest('input,textarea,select,dialog,[contenteditable=true],.edge-cut');}
  viewport.addEventListener('pointerdown',event=>{
    if(!board||event.button!==0||viewport.classList.contains('hand-mode')||event.target.closest('#node-composer,.zoom-controls,.canvas-navigation,#result-tools,#selection-toolbar,#toast'))return;
    const header=event.target.closest('.canvas-group-title');
    if(header){event.preventDefault();event.stopImmediatePropagation();const g=(doc().groups||[]).find(g=>g.id===header.dataset.groupId);if(!g)return;apply(event.shiftKey?[...picks,...g.node_ids]:g.node_ids,g.id);if(event.altKey){gesture={type:'group',pointer:event.pointerId,key:board.id,x:event.clientX,y:event.clientY,positions:g.node_ids.map(id=>({id,x:nodeBy(id).x,y:nodeBy(id).y}))};viewport.setPointerCapture(event.pointerId);}return;}
    if(event.target.closest('button,input,textarea,select,a,.edge-hit,.edge-cut'))return;
    const card=event.target.closest('.card');
    if(card){if(event.altKey||(!event.shiftKey&&!event.ctrlKey&&!event.metaKey))return;const video=event.target.closest('video');if(video&&event.clientY>video.getBoundingClientRect().bottom-44)return;event.preventDefault();event.stopImmediatePropagation();const ids=new Set(event.shiftKey||event.ctrlKey||event.metaKey?picks:[]);const id=card.dataset.id;if(ids.has(id)&&(event.shiftKey||event.ctrlKey||event.metaKey))ids.delete(id);else ids.add(id);apply([...ids]);return;}
    event.preventDefault();event.stopImmediatePropagation();gesture={type:'marquee',pointer:event.pointerId,key:board.id,x:event.clientX,y:event.clientY,base:event.shiftKey||event.ctrlKey||event.metaKey?[...picks]:[]};marquee.hidden=false;const r=viewport.getBoundingClientRect();Object.assign(marquee.style,{left:event.clientX-r.left+'px',top:event.clientY-r.top+'px',width:'0px',height:'0px'});viewport.setPointerCapture(event.pointerId);
  },true);
  nodes.addEventListener('click',event=>{if(!event.altKey&&!event.target.closest('button,input,textarea,select,a,video')){event.stopImmediatePropagation();}},true);
  groups.addEventListener('click',event=>event.stopPropagation());
  document.addEventListener('pointermove',event=>{
    if(!gesture||event.pointerId!==gesture.pointer||board?.id!==gesture.key)return;event.preventDefault();event.stopImmediatePropagation();
    if(gesture.type==='group'){const dx=(event.clientX-gesture.x)/doc().viewport.zoom,dy=(event.clientY-gesture.y)/doc().viewport.zoom;for(const p of gesture.positions){const n=nodeBy(p.id);if(!n)continue;n.x=Math.max(-100000,Math.min(100000,p.x+dx));n.y=Math.max(-100000,Math.min(100000,p.y+dy));const card=nodes.querySelector(`[data-id="${n.id}"]`);if(card){card.style.left=n.x+'px';card.style.top=n.y+'px';}}renderEdges();schedule();return;}
    const r=viewport.getBoundingClientRect(),left=Math.min(gesture.x,event.clientX),top=Math.min(gesture.y,event.clientY),right=Math.max(gesture.x,event.clientX),bottom=Math.max(gesture.y,event.clientY);Object.assign(marquee.style,{left:left-r.left+'px',top:top-r.top+'px',width:right-left+'px',height:bottom-top+'px'});
    gesture.hits=[...nodes.children].filter(card=>{const c=card.getBoundingClientRect();return c.right>=left&&c.left<=right&&c.bottom>=top&&c.top<=bottom;}).map(card=>card.dataset.id);const preview=new Set([...gesture.base,...gesture.hits]);for(const card of nodes.children)card.classList.toggle('multi-selected',preview.has(card.dataset.id));
  },true);
  function finish(cancel=false){if(!gesture)return;const value=gesture;gesture=null;marquee.hidden=true;if(board?.id===value.key){if(value.type==='group'){touch();schedule();}else if(!cancel)apply([...value.base,...(value.hits||[])]);else schedule();}if(viewport.hasPointerCapture(value.pointer))viewport.releasePointerCapture(value.pointer);}
  document.addEventListener('pointerup',()=>finish(),true);viewport.addEventListener('pointercancel',()=>finish(true));viewport.addEventListener('lostpointercapture',()=>finish(true));window.addEventListener('blur',()=>finish(true));
  window.addEventListener('keydown',event=>{if(!board||editable(event.target))return;const ctrl=event.ctrlKey||event.metaKey;
    if(ctrl&&event.key.toLowerCase()==='a'){event.preventDefault();event.stopImmediatePropagation();apply(doc().nodes.map(n=>n.id));}
    else if(ctrl&&event.key.toLowerCase()==='g'){event.preventDefault();event.stopImmediatePropagation();try{if(event.shiftKey)ungroupSelection();else makeGroup();}catch(e){message(e.message);}}
    else if(ctrl&&event.key.toLowerCase()==='d'&&picks.size){event.preventDefault();event.stopImmediatePropagation();try{copySelection();}catch(e){message(e.message);}}
    else if(ctrl&&event.key.toLowerCase()==='z'&&undo&&board.id===undo.key&&changeNo===undo.serial){event.preventDefault();event.stopImmediatePropagation();restore().catch(e=>message(e.message));}
    else if(event.key==='Delete'&&picks.size){event.preventDefault();event.stopImmediatePropagation();deleteSelection().catch(e=>message(e.message));}
    else if(event.key==='Escape'){if(document.body.classList.contains('node-focus-mode'))return;apply([]);}
    else if(picks.size>1&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)){event.preventDefault();event.stopImmediatePropagation();const speed=event.shiftKey?20:4,[x,y]=({ArrowLeft:[-speed,0],ArrowRight:[speed,0],ArrowUp:[0,-speed],ArrowDown:[0,speed]})[event.key];for(const id of picks){const n=nodeBy(id);n.x=Math.max(-100000,Math.min(100000,n.x+x));n.y=Math.max(-100000,Math.min(100000,n.y+y));}touch();render();}
  },true);
  const oldRender=render,oldInspector=inspector,oldView=view,oldOpen=openBoard;render=function(){oldRender();schedule();};inspector=function(){oldInspector();schedule();};view=function(){oldView();schedule();};openBoard=async function(key){finish(true);await oldOpen(key);if(board?.id===key){boardKey=key;apply([]);schedule();}};
  viewport.setAttribute('aria-label','无限创作画布。左键选择与框选，中键平移，滚轮缩放；左键拖动节点。');
  viewport.addEventListener('pointermove',schedule);
  nodes.addEventListener('load',schedule,true);new ResizeObserver(schedule).observe(viewport);
  const help=$('help-dialog').querySelector('form');for(const p of help.querySelectorAll('p')){if(p.textContent.startsWith('空白处拖动：'))p.textContent='左键拖框多选；中键拖动画布；滚轮或触控板双指缩放。';if(p.textContent.startsWith('拖动卡片标题栏：'))p.textContent='左键拖动节点主体：移动节点；方向键微调，Shift 加速。';}help.insertBefore(el('p','','左键选择/拖框多选；Shift/Ctrl 点击追加选择；中键平移。左键拖动移动节点；Alt+左键拖动分组标题移动分组。Ctrl+G 打组，Ctrl+Shift+G 取消分组；Delete 移出画布，Ctrl+Z 撤销最近删除。'),help.lastElementChild);
  $('canvas-undo').onclick=()=>restore().catch(e=>message(e.message));
  window.H3Selection={ids:currentIds,select:apply,refresh:schedule};
})();
