/* Project metadata is separate from graph content and generation records. */
(() => {
  let active = 'unclassified', projects = [], initialized=false;
  const selector = el('select'); selector.id='projects'; selector.setAttribute('aria-label','选择项目');
  const manage=el('button','','项目管理'); manage.id='manage-projects';
  document.querySelector('.project').prepend(selector,manage);
  const dialog=el('dialog','project-manager');dialog.id='project-manager';
  const head=el('div','panel-title'),title=el('h2','','项目与画布'),close=el('button','','关闭');
  close.onclick=()=>dialog.close();head.append(title,close);
  const tools=el('div','project-tools'),name=el('input');name.placeholder='新项目名称';name.maxLength=80;name.setAttribute('aria-label','项目名称');
  const create=el('button','primary','新建项目'),rename=el('button','','重命名项目'),newCanvas=el('button','','新建画布');tools.append(name,create,rename,newCanvas);
  const help=el('p','muted','一个项目可以包含多个独立画布。已有画布保留在未分类，移动分类会保留素材、节点和生成记录。');
  const list=el('div','project-board-list');list.id='project-board-list';dialog.append(head,help,tools,list);document.body.append(dialog);
  const error=el('p','danger');error.setAttribute('role','alert');tools.after(error);
  function action(fn){return async()=>{error.textContent='';try{await fn();}catch(e){error.textContent=e.message;}};}
  function guard(){if(busy.size||H3Stage.isOpen())throw Error('当前节点正在处理，请完成后再切换项目。');}
  const originalAdd=add;
  add=function(...args){if(!board)throw Error('请先在当前项目中新建画布。');return originalAdd(...args);};
  async function catalog(){const value=await api('/canvas-projects');projects=value.items;selector.replaceChildren();
    for(const p of [{id:'unclassified',name:'未分类',canvas_count:value.unclassified_count},...projects]){const o=el('option','',`${p.name} · ${p.canvas_count}`);o.value=p.id;selector.append(o);}selector.value=active;
  }
  boards=async function(){if(!initialized){initialized=true;const key=location.hash.slice(1);if(/^[a-f0-9]{32}$/.test(key)){const value=await api('/canvases/'+key);active=value.project_id||'unclassified';}}await catalog();const items=await api('/canvases?project_id='+active);$('boards').replaceChildren();
    for(const item of items){const o=el('option','',item.title);o.value=item.id;$('boards').append(o);}if(board)$('boards').value=board.id;return items;
  };
  const originalOpen=openBoard;
  openBoard=async function(key){await originalOpen(key);if(board?.id!==key)return;active=board.project_id||'unclassified';await boards();document.body.classList.remove('empty-project');};
  function empty(){board=null;selected=null;runs=[];dirty=false;connection=null;inspector();$('nodes').replaceChildren();$('edges').replaceChildren();$('welcome').hidden=false;document.body.classList.add('empty-project');$('save-state').textContent='当前项目还没有画布';history.replaceState(null,'',location.pathname);}
  async function switchProject(key){guard();await save();active=key;const items=await boards();if(items.length)await openBoard(items[0].id);else empty();}
  selector.onchange=protect(async()=>{const previous=active;try{await switchProject(selector.value);}catch(e){active=previous;selector.value=previous;throw e;}});
  newBoard=async function(){guard();await save();
    // Reuse the existing accessible naming dialog rather than a browser prompt.
    const d=$('canvas-name-dialog'),input=$('canvas-name');d.querySelector('h2').textContent='新建画布';input.value='未命名画布';d.returnValue='';d.showModal();input.focus();input.select();
    const value=await new Promise(resolve=>d.addEventListener('close',()=>resolve(d.returnValue==='save'?input.value.trim():null),{once:true}));if(!value)return;
    const result=await api('/canvases',json('POST',{title:value,nodes:[],edges:[],viewport:{x:80,y:80,zoom:1},project_id:active==='unclassified'?null:active}));await openBoard(result.id);
  };
  async function showList(){await catalog();const items=await boards();list.replaceChildren();rename.disabled=active==='unclassified';
    if(!items.length)list.append(el('p','muted','这个项目还没有画布，点击“新建画布”开始。'));
    for(const item of items){const row=el('div','project-board'),info=el('div'),open=el('button','',item.title);open.onclick=action(async()=>{await openBoard(item.id);dialog.close();});info.append(open,el('small','muted',`${item.node_count} 个节点`));
      const target=el('select');target.setAttribute('aria-label','移动 '+item.title+' 到项目');for(const p of [{id:'unclassified',name:'未分类'},...projects]){const o=el('option','',p.name);o.value=p.id;target.append(o);}target.value=item.project_id||'unclassified';
      const moveButton=el('button','','移动');moveButton.onclick=action(async()=>{guard();await save();const current=await api('/canvases/'+item.id);const result=await api(`/canvases/${item.id}/project`,json('PUT',{revision:current.revision,project_id:target.value==='unclassified'?null:target.value}));if(board?.id===item.id){board.revision=result.revision;board.project_id=result.project_id;}await switchProject(target.value);await showList();message('画布已移动，素材和生成记录已保留。');});row.append(info,target,moveButton);list.append(row);
    }
  }
  manage.onclick=protect(async()=>{await showList();dialog.showModal();});
  create.onclick=action(async()=>{guard();await save();const p=await api('/canvas-projects',json('POST',{name:name.value}));name.value='';await switchProject(p.id);await showList();});
  rename.onclick=action(async()=>{await api('/canvas-projects/'+active,json('PUT',{name:name.value}));name.value='';await showList();});
  newCanvas.onclick=action(async()=>{dialog.close();await newBoard();});
  // Empty projects expose only project/canvas navigation, never an old project's graph.
  const start=$('start'),startOriginal=start.onclick;start.onclick=protect(event=>board?startOriginal(event):newBoard());
  const welcome=$('welcome');const emptyLabel=el('p','project-empty-label','此项目暂无画布，请点击上方“新建”创建。');welcome.append(emptyLabel);
})();
