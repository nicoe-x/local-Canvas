/* Presentation and interaction refinements; no generation or storage protocol changes. */
'use strict';
(() => {
  const paths = {
    cursor:'<path d="m5 3 14 9-7 1-3 7z"/>',
    hand:'<path d="M8 13V6a2 2 0 0 1 4 0v6-8a2 2 0 0 1 4 0v8-5a2 2 0 0 1 4 0v9a6 6 0 0 1-6 6h-1a6 6 0 0 1-5-3l-4-6a2 2 0 0 1 3-2l1 2"/>',
    text:'<path d="M4 5h16M12 5v14M8 19h8"/>',
    image:'<rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="8" cy="8" r="1.5"/><path d="m4 17 5-5 4 3 3-4 4 6"/>',
    video:'<rect x="3" y="5" width="13" height="14" rx="3"/><path d="m16 10 5-3v10l-5-3"/>',
    cube:'<path d="m12 3 9 5-9 5-9-5zm-9 5v9l9 5 9-5V8m-9 5v9"/>',
    reverse:'<rect x="3" y="3" width="13" height="13" rx="3"/><path d="m6 12 3-3 4 4m2 7h7m-3-3 3 3-3 3"/>',
    upload:'<path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5"/>',
    library:'<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    help:'<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 0 1 6 0c0 2-3 2-3 5m0 3h.01"/>',
    plus:'<path d="M12 5v14M5 12h14"/>',
    minus:'<path d="M5 12h14"/>',
    close:'<path d="m6 6 12 12M6 18 18 6"/>',
    expand:'<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
    save:'<path d="M5 3h12l4 4v14H3V3zm2 0v6h10V3M7 21v-8h10v8"/>',
    pencil:'<path d="m15 4 5 5M4 20l5-1L21 7a3.5 3.5 0 0 0-5-5L4 14z"/>',
    link:'<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2"/>',
    copy:'<rect x="8" y="8" width="13" height="13" rx="3"/><path d="M16 8V3H3v13h5"/>',
    trash:'<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/>',
    undo:'<path d="M9 4 4 9l5 5M4 9h10a6 6 0 0 1 0 12h-3"/>',
    settings:'<path d="M4 7h16M4 17h16M9 4v6m6 4v6"/>',
    arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>',
    download:'<path d="M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4"/>',
    external:'<path d="M14 3h7v7m0-7L10 14M9 3H3v18h18v-6"/>',
    lock:'<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3"/>',
    eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7"/><circle cx="12" cy="12" r="3"/>',
    export:'<path d="M14 3h7v7m0-7-9 9M10 3H3v18h18v-7"/>',
    chevron:'<path d="m9 6 6 6-6 6"/>',
    person:'<circle cx="12" cy="5" r="3"/><path d="M5 21v-4a7 7 0 0 1 14 0v4M12 12v9"/>',
    chair:'<path d="M6 3h12v11H6zM5 14h14v4H5zm2 4v4m10-4v4"/>',
    table:'<path d="M3 9h18v4H3zm3 4v9m12-9v9"/>',
    camera:'<path d="M3 7h5l2-3h4l2 3h5v14H3z"/><circle cx="12" cy="13" r="4"/>',
    more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  };
  function icon(name) {
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
    svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');
    svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.65');
    svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');
    svg.setAttribute('aria-hidden','true');svg.classList.add('ui-icon');
    svg.innerHTML=paths[name]||paths.image;
    return svg;
  }
  function decorate(button,name,label,iconOnly=false) {
    if(!button)return;
    if(!button.dataset.polishLabel)button.dataset.polishLabel=label||button.textContent.trim();
    button.replaceChildren(icon(name));
    if(!iconOnly)button.append(el('span','button-label',button.dataset.polishLabel));
    button.setAttribute('aria-label',button.dataset.polishLabel);
    if(iconOnly)button.title=button.dataset.polishLabel;
    button.dataset.polishIcon=name;
  }
  const viewport=$('viewport');
  document.body.classList.add('canvas-refined');
  const rail=$('add-video').parentElement;
  for(const [kind,name,label] of [['reverse','reverse','图片反推'],['stage3d','cube','3D导演台']]){
    const button=el('button');button.id='add-'+kind;button.type='button';
    button.title=label;button.setAttribute('aria-label',label);
    button.append(icon(name),el('span','',label));
    button.onclick=protect(async()=>{if(!board)return;const node=add(kind);if(kind==='stage3d')await H3Stage.open(node.id);else $('composer-prompt').focus();});
    rail.insertBefore(button,$('upload-button'));
  }
  for(const [id,name,label] of [['add-note','text','提示词'],['add-image','image','图片'],['add-video','video','视频'],['upload-button','upload','上传'],['library-toggle','library','素材库'],['help','help','操作帮助']]){
    const button=$(id);button.replaceChildren(icon(name),el('span','',label));button.setAttribute('aria-label',label);
  }
  $('upload-button').classList.add('rail-section-start');
  const brand=document.querySelector('.brand');
  brand.replaceChildren(el('b','brand-mark','H3'),el('span','','创作画布'));
  const privacy=el('span','private-chip');privacy.append(icon('lock'),document.createTextNode('私人空间'));brand.after(privacy);
  for(const [id,name,label,only] of [
    ['rename-board','pencil','重命名画布',true],['new-board','plus','新建画布',false],['save','save','保存',false],
    ['zoom-out','minus','缩小',true],['zoom-in','plus','放大',true],['fit','expand','适应画布',false],['export','export','导出',false],
    ['start','plus','创建第一个节点',false],['inspector-close','close','关闭高级参数',true],['library-close','close','关闭素材库',true],
    ['duplicate','copy','复制节点',false],['remove-node','trash','移出画布',false],['expand-prompt','expand','放大编辑',false],
    ['media-close','close','关闭作品预览',true],
  ])decorate($(id),name,label,only);
  const back=document.querySelector('.back');back.replaceChildren(icon('external'),document.createTextNode('工作台'));
  for(const dialog of document.querySelectorAll('#prompt-dialog,#help-dialog')){
    decorate(dialog.querySelector('button[aria-label]'),'close','关闭',true);
  }
  $('welcome').querySelector('.eyebrow').textContent='PRIVATE CREATIVE WORKSPACE';
  $('welcome').querySelector('h1').textContent='从一个想法，连接更多可能。';
  $('welcome').querySelector('p').innerText='双击任意空白处添加节点，或从左侧放入素材。\n连接参考、调整画面，再开始你的创作。';

  // Selection/hand modes and a persistent undo affordance for graph-only removal.
  const navigation=el('div','canvas-navigation');navigation.setAttribute('aria-label','画布操作');
  let handMode=false,spaceHeld=false,lastRemoval=null;
  function navButton(id,name,label,action){const value=el('button');value.id=id;value.type='button';value.onclick=action;decorate(value,name,label,true);navigation.append(value);return value;}
  const pointer=navButton('canvas-select','cursor','选择工具（V）',()=>setHand(false));
  const hand=navButton('canvas-hand','hand','平移工具（H / 按住空格）',()=>setHand(true));
  const undo=navButton('canvas-undo','undo','撤销上次移除（Ctrl+Z）',()=>undoRemoval());undo.disabled=true;
  viewport.append(navigation);
  navigation.addEventListener('pointerdown',event=>event.stopPropagation());
  $('toast').addEventListener('pointerdown',event=>event.stopPropagation());
  const summary=el('div','canvas-summary');summary.id='canvas-summary';viewport.append(summary);
  const tips=el('div','canvas-tips');tips.append(el('span','','双击添加节点'),el('kbd','','Space'),el('span','','平移'),el('kbd','','F'),el('span','','适应画布'));viewport.append(tips);
  function setHand(value){handMode=value;syncNavigation();}
  function syncNavigation(){
    viewport.classList.toggle('hand-mode',handMode||spaceHeld);
    pointer.setAttribute('aria-pressed',String(!(handMode||spaceHeld)));hand.setAttribute('aria-pressed',String(handMode||spaceHeld));
    undo.disabled=!lastRemoval||lastRemoval.board!==board?.id;
    if(board)summary.textContent=`${doc().nodes.length} 个节点  /  ${doc().edges.length} 条连接`;
    document.body.classList.toggle('has-node-selection',!!selected);
  }
  viewport.addEventListener('pointerdown',event=>{
    const middle=event.button===1;
    if((!middle&&(!(handMode||spaceHeld)||event.button!==0))||event.target.closest('#node-composer,.zoom-controls,#canvas-navigation,#toast'))return;
    if(!middle&&event.target.closest('button,input,select,textarea,video,a'))return;
    if(!board)return;event.preventDefault();event.stopImmediatePropagation();
    dragging={type:'pan',startX:event.clientX,startY:event.clientY,x:doc().viewport.x,y:doc().viewport.y};
    viewport.classList.add('panning');viewport.setPointerCapture(event.pointerId);
  },true);
  // Suppress native wheel-button autoscroll and link opening over the canvas.
  for(const type of ['mousedown','auxclick'])viewport.addEventListener(type,event=>{
    if(board&&event.button===1&&!event.target.closest('#node-composer,.zoom-controls,#canvas-navigation,#toast'))event.preventDefault();
  },true);
  window.addEventListener('blur',()=>{if(dragging?.type==='pan')endDrag();});

  function undoRemoval(){
    if(!lastRemoval||lastRemoval.board!==board?.id)return;
    if(doc().nodes.length>=200){message('画布节点已达上限，无法恢复');return;}
    const value=lastRemoval;lastRemoval=null;
    if(!nodeBy(value.node.id))doc().nodes.push(value.node);
    for(const edge of value.edges)if(nodeBy(edge.source)&&nodeBy(edge.target)&&!doc().edges.some(e=>e.source===edge.source&&e.target===edge.target))doc().edges.push(edge);
    selected=value.node.id;touch();render();inspector();message('节点及其连接已恢复');
  }
  const originalRemove=removeNode;
  removeNode=function(){
    const node=selected&&nodeBy(selected);if(!node)return;
    const value={board:board.id,node:structuredClone(node),edges:structuredClone(doc().edges.filter(e=>e.source===selected||e.target===selected))};
    originalRemove();
    if(!nodeBy(node.id)){
      lastRemoval=value;syncNavigation();message('已移出画布，磁盘文件保留。');
      const restore=el('button','toast-undo','撤销');restore.onclick=undoRemoval;$('toast').append(restore);
    }
  };
  $('remove-node').onclick=()=>removeNode();
  function duplicateNode(){
    const node=selected&&nodeBy(selected);if(!node)return;
    const value=structuredClone(node);delete value.id;
    if(node.kind!=='asset')delete value.job_id;
    let x=node.x+335,y=node.y+24;
    for(let i=0;i<30&&doc().nodes.some(other=>x<other.x+310&&x+310>other.x&&y<other.y+370&&y+370>other.y);i++)y+=380;
    const copy=add(node.kind,{...value,x,y,title:(node.title+' 副本').slice(0,80)});
    focusNode(copy.id);
    return copy;
  }
  $('duplicate').onclick=duplicateNode;

  // A small accessible dialog replaces browser-native naming prompts.
  const nameDialog=el('dialog','name-dialog');nameDialog.id='canvas-name-dialog';
  const nameForm=el('form');nameForm.method='dialog';
  const nameTitle=el('h2'),nameLabel=el('label','','名称'),nameInput=el('input');nameInput.id='canvas-name';nameInput.maxLength=80;nameInput.required=true;nameLabel.append(nameInput);
  const nameActions=el('div','name-actions'),cancel=el('button','','取消'),confirm=el('button','primary','保存');cancel.value='cancel';cancel.formNoValidate=true;confirm.value='save';nameActions.append(cancel,confirm);nameForm.append(nameTitle,nameLabel,nameActions);nameDialog.append(nameForm);document.body.append(nameDialog);
  function askName(title,value){
    if(nameDialog.open)return Promise.resolve(null);
    nameTitle.textContent=title;nameInput.value=value;nameDialog.returnValue='';nameDialog.showModal();nameInput.focus();nameInput.select();
    return new Promise(resolve=>nameDialog.addEventListener('close',()=>resolve(nameDialog.returnValue==='save'?nameInput.value.trim():null),{once:true}));
  }
  $('rename-board').onclick=protect(async()=>{const title=await askName('重命名画布',doc().title);if(!title)return;doc().title=title;touch();await save();await boards();$('boards').value=board.id;});
  newBoard=async function(){
    if(busy.size||H3Stage.isOpen())throw Error('当前节点正在处理，请完成后再新建画布。');
    const title=await askName('新建画布','未命名画布');if(!title)return;
    await save();const value=await api('/canvases',json('POST',{title,nodes:[],edges:[],viewport:{x:80,y:80,zoom:1}}));
    await boards();await openBoard(value.id);
  };
  $('new-board').onclick=protect(()=>newBoard());

  const actions=el('div','node-actions-menu');actions.id='node-actions-menu';actions.hidden=true;actions.setAttribute('role','dialog');actions.setAttribute('aria-label','节点操作');
  let actionNode=null;
  for(const [action,name,label] of [['rename','pencil','重命名'],['copy','copy','复制节点'],['focus','expand','定位节点'],['remove','trash','移出画布']]){
    const button=el('button');button.type='button';button.dataset.nodeAction=action;decorate(button,name,label);if(action==='remove')button.classList.add('danger');
    button.onclick=protect(async()=>{
      const id=actionNode;actions.hidden=true;if(!id||!nodeBy(id))return;select(id);
      if(action==='copy')duplicateNode();
      if(action==='remove')removeNode();
      if(action==='rename'){const title=await askName('重命名节点',nodeBy(id).title);if(title&&nodeBy(id)){nodeBy(id).title=title;touch();render();inspector();}}
      if(action==='focus')focusNode(id);
    });actions.append(button);
  }
  actions.append(el('small','','移出节点不会删除磁盘文件'));document.body.append(actions);
  function showActions(id,x,y){
    actionNode=id;actions.hidden=false;
    const r=actions.getBoundingClientRect();actions.style.left=Math.max(8,Math.min(x,innerWidth-r.width-8))+'px';actions.style.top=Math.max(8,Math.min(y,innerHeight-r.height-8))+'px';
    actions.querySelector('button').focus({preventScroll:true});
  }
  viewport.addEventListener('contextmenu',event=>{
    const card=event.target.closest('.card');if(!card)return;event.preventDefault();event.stopImmediatePropagation();select(card.dataset.id);showActions(card.dataset.id,event.clientX,event.clientY);
  },true);
  document.addEventListener('pointerdown',event=>{if(!actions.contains(event.target))actions.hidden=true;},true);
  actions.onkeydown=event=>{
    if(event.key==='Escape'){actions.hidden=true;viewport.focus();}
    if(['ArrowDown','ArrowUp'].includes(event.key)){
      event.preventDefault();const buttons=[...actions.querySelectorAll('button')],index=buttons.indexOf(document.activeElement),step=event.key==='ArrowDown'?1:-1;buttons[(index+step+buttons.length)%buttons.length].focus();
    }
  };
  window.addEventListener('resize',()=>actions.hidden=true);
  viewport.addEventListener('wheel',()=>actions.hidden=true,{passive:true});

  function usableHeight(){const r=viewport.getBoundingClientRect(),composer=$('node-composer');return composer.hidden?r.height:Math.max(180,composer.getBoundingClientRect().top-r.top-28);}
  function focusNode(id){const node=nodeBy(id),r=viewport.getBoundingClientRect(),v=doc().viewport;v.x=r.width/2-(node.x+145)*v.zoom;v.y=usableHeight()/2-(node.y+155)*v.zoom;view();touch();}
  fit=function(){
    if(!board||!doc().nodes.length)return;
    const r=viewport.getBoundingClientRect(),height=usableHeight(),xs=doc().nodes.map(n=>n.x),ys=doc().nodes.map(n=>n.y),left=Math.min(...xs),top=Math.min(...ys),w=Math.max(...xs)+290-left,h=Math.max(...ys)+350-top,v=doc().viewport;
    v.zoom=Math.max(.15,Math.min(1,(r.width-110)/w,(height-70)/h));v.x=(r.width-w*v.zoom)/2-left*v.zoom;v.y=(height-h*v.zoom)/2-top*v.zoom;view();touch();
  };
  $('fit').onclick=()=>fit();
  window.addEventListener('keydown',event=>{
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();save().catch(error=>message(error.message));return;}
    if(event.target.closest('input,textarea,select,dialog'))return;
    if(event.key==='Escape'){actions.hidden=true;spaceHeld=false;syncNavigation();}
    if(event.code==='Space'){event.preventDefault();spaceHeld=true;syncNavigation();}
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z'){event.preventDefault();undoRemoval();}
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='d'){event.preventDefault();duplicateNode();}
    if(event.ctrlKey||event.metaKey||event.altKey)return;
    if(event.key.toLowerCase()==='v')setHand(false);
    if(event.key.toLowerCase()==='h')setHand(true);
    if(event.key.toLowerCase()==='f')fit();
  });
  window.addEventListener('keyup',event=>{if(event.code==='Space'){spaceHeld=false;syncNavigation();}});
  window.addEventListener('blur',()=>{spaceHeld=false;syncNavigation();});

  function polishCards(){
    if(!board)return;
    for(const card of $('nodes').children){
      const node=nodeBy(card.dataset.id);if(!node)continue;
      const name={note:'text',image:'image',video:'video',asset:'library',reverse:'reverse',stage3d:'cube'}[node.kind];
      const chip=card.querySelector('.kind');chip.replaceChildren(icon(name));chip.title={note:'提示词',image:'图片',video:'视频',asset:'参考素材',reverse:'图片反推',stage3d:'3D导演台'}[node.kind];
      const placeholder=card.querySelector('.card-placeholder span');if(placeholder)placeholder.replaceChildren(icon(name));
      const edit=card.querySelector('.card-foot button');if(edit&&edit.textContent==='设置 / 生成'){
        decorate(edit,'settings','编辑',false);edit.title='编辑当前节点';
      }
      const more=el('button','card-more');more.type='button';decorate(more,'more','节点操作',true);
      more.addEventListener('pointerdown',event=>event.stopPropagation());
      more.onclick=event=>{event.stopPropagation();select(node.id);const r=more.getBoundingClientRect();showActions(node.id,r.right,r.bottom+6);};
      card.querySelector('.card-head').append(more);
      for(const [side,label] of [['in','输入参考'],['out','拖动连接或创建下游']]){
        const port=card.querySelector('.port.'+side);if(port)port.title=label+' · '+node.title;
      }
    }
  }
  function polishComposer(){
    const composer=$('node-composer');if(!composer)return;
    const map=[['#composer-upload','plus','添加参考'],['#composer-expand','expand','放大编辑'],['#composer-advanced','settings','高级参数']];
    for(const [selector,name,label] of map){const button=composer.querySelector(selector);if(button&&!button.querySelector('svg'))decorate(button,name,label);}
    const run=$('composer-generate');
    if(run&&!run.querySelector('svg')){
      const label=run.textContent;run.dataset.polishLabel=label;decorate(run,'arrow',label);
    }
  }
  const originalRender=render,originalInspector=inspector;
  render=function(){originalRender();polishCards();syncNavigation();};
  inspector=function(){originalInspector();polishComposer();syncNavigation();};
  const originalRefreshRuns=refreshRuns;
  refreshRuns=async function(){await originalRefreshRuns();polishComposer();};
  new MutationObserver(()=>polishComposer()).observe($('composer-generate'),{childList:true});
  // Existing handlers captured the original refresh function; inspector() still
  // redecorates it when status changes. Static controls are never observed globally.
  syncNavigation();
  const help=$('help-dialog').querySelector('form');
  const shortcut=el('p','','V 选择 · H 平移 · 按住 Space 临时平移 · F 适应画布 · Ctrl+S 保存 · Ctrl+D 复制 · Ctrl+Z 撤销移除。');
  help.insertBefore(shortcut,help.lastElementChild);
  function polishStage(){
    for(const [id,name,label] of [['stage-add-person','person','人物'],['stage-add-box','cube','方块'],['stage-add-chair','chair','椅子'],['stage-add-table','table','桌子'],['stage-capture','camera','保存构图参考'],['stage-close','save','保存并关闭'],['stage-remove','trash','删除选中物体'],['stage-use-view','eye','当前视角作为摄影机']])decorate($(id),name,label);
  }
  new MutationObserver(records=>{
    if(records.some(record=>[...record.addedNodes].some(node=>node.id==='stage-dialog')))polishStage();
  }).observe(document.body,{childList:true});
  window.addEventListener('resize',()=>{if(innerWidth<700&&selected&&board&&!H3Stage.isOpen()&&!dragging)focusNode(selected);});
  window.addEventListener('hashchange',()=>{
    const key=location.hash.slice(1);
    if(!board||loading||key===board.id||!/^[a-f0-9]{32}$/.test(key))return;
    openBoard(key).catch(error=>{history.replaceState(null,'','#'+board.id);message(error.message);});
  });
})();
