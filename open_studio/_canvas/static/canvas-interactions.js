/* Direct canvas creation and node-bound composer. Uses existing forms/queue. */
'use strict';
(() => {
  const viewport = $('viewport');
  const menu = el('div', 'node-menu');
  menu.id = 'node-menu';
  menu.hidden = true;
  menu.setAttribute('role', 'dialog');
  menu.setAttribute('aria-label', '添加节点或资源');
  const heading = el('div', 'menu-heading', '添加节点');
  const search = el('input');
  search.type = 'search';
  search.placeholder = '搜索节点或资源';
  search.setAttribute('aria-label', '搜索节点或资源');
  menu.append(heading, search);
  let anchor = null, placement = null, composerNode = null, menuSource = null;
  const entries = [
    ['note', '文本 / 提示词', 'text'],
    ['h3prompt', 'H3 提示词转换', 'text'],
    ['image', '图片生成', 'image'],
    ['video', '视频生成', 'video'],
    ['reverse', '图片反推', 'reverse'],
    ['stage3d', '3D 导演台', 'stage'],
    ['upload', '上传图片', 'upload'],
    ['history', '从生成历史选择', 'history'],
  ];
  const icons = {
    text: '<path d="M4 5h16M12 5v14M8 19h8"/>',
    image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m4 18 5-5 4 3 3-5 4 7"/>',
    video: '<rect x="3" y="5" width="13" height="14" rx="3"/><path d="m16 10 5-3v10l-5-3"/>',
    upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 15v5h16v-5"/>',
    history: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    reverse: '<rect x="3" y="3" width="13" height="13" rx="2"/><path d="m5 13 4-4 4 4M15 20h7m-3-3 3 3-3 3"/>',
    stage: '<path d="m12 2 9 5v10l-9 5-9-5V7zm0 10 9-5M12 12 3 7m9 5v10"/>',
  };
  function icon(key) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.6');
    svg.setAttribute('aria-hidden', 'true');
    // Only fixed, developer-owned SVG paths; no user-supplied markup.
    svg.innerHTML = icons[key];
    return svg;
  }
  const menuButtons = [];
  for (const [kind, label, symbol] of entries) {
    if (kind === 'upload') menu.append(el('div', 'menu-heading menu-divider', '添加资源'));
    const button = el('button', 'node-menu-item');
    button.type = 'button';
    button.dataset.kind = kind;
    button.append(icon(symbol), el('span', '', label));
    button.onclick = protect(async () => {
      const position = {...anchor};
      const source = menuSource;
      closeMenu();
      placement = {board: board.id, ...position, offset: 0, source};
      if (kind === 'upload') {
        $('upload').click();
      } else if (kind === 'history') {
        $('library').hidden = false;
        libraryPage = 1;
        await loadLibrary();
      } else {
        const added = add(kind);
        placement = null;
        if(kind==='stage3d') await H3Stage.open(added.id);
        else $('composer-prompt').focus({preventScroll: true});
      }
    });
    menuButtons.push(button);
    menu.append(button);
  }
  document.body.append(menu);

  function closeMenu(focus = false) {
    menu.hidden = true;
    menuSource = null;
    if (focus) viewport.focus({preventScroll: true});
  }
  function openMenu(clientX, clientY, source = null) {
    if (!board) return;
    anchor = worldPoint(clientX, clientY);
    menuSource = source;
    connection = null;
    placement = null;
    selected = null;
    render();
    inspector();
    search.value = '';
    heading.textContent = source ? '引用此节点生成' : '添加节点';
    filterMenu();
    menu.hidden = false;
    const rect = menu.getBoundingClientRect();
    menu.style.left = Math.max(8, Math.min(clientX, innerWidth - rect.width - 8)) + 'px';
    menu.style.top = Math.max(8, Math.min(clientY, innerHeight - rect.height - 8)) + 'px';
    search.focus({preventScroll: true});
  }
  function filterMenu(){
    const kind=menuSource&&nodeBy(menuSource)?.kind;
    const targets=kind&&['note','reverse'].includes(kind)?['image','video']:['image','video','reverse'];
    for(const button of menuButtons)button.hidden=!button.textContent.includes(search.value.trim())||(!!menuSource&&!targets.includes(button.dataset.kind));
    menu.querySelector('.menu-divider').hidden=!!menuSource;
  }
  search.oninput = filterMenu;
  menu.onkeydown = event => {
    const buttons = menuButtons.filter(button => !button.hidden);
    const index = buttons.indexOf(document.activeElement);
    if (event.key === 'Escape') { event.preventDefault(); closeMenu(true); }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      buttons[(index + step + buttons.length) % buttons.length]?.focus();
    }
    if (event.key === 'Enter' && document.activeElement === search) {
      event.preventDefault(); buttons[0]?.click();
    }
  };
  viewport.addEventListener('dblclick', event => {
    if (event.target.closest('.card,button,input,textarea,select,a,video,#node-composer,.zoom-controls')) return;
    event.preventDefault();
    openMenu(event.clientX, event.clientY);
  });
  viewport.addEventListener('contextmenu', event => {
    if (event.target.closest('.card,#node-composer,button,textarea,input,select,video')) return;
    event.preventDefault(); openMenu(event.clientX, event.clientY);
  });
  viewport.addEventListener('keydown', event => {
    if (event.target !== viewport || !['Enter', 'ContextMenu'].includes(event.key)) return;
    event.preventDefault();
    const rect = viewport.getBoundingClientRect();
    openMenu(rect.left + rect.width / 2, rect.top + rect.height / 2);
  });
  document.addEventListener('pointerdown', event => {
    if (!menu.hidden && !menu.contains(event.target)) closeMenu();
  }, true);
  window.addEventListener('resize', () => closeMenu());

  const composer = el('form', 'node-composer');
  composer.id = 'node-composer';
  composer.hidden = true;
  composer.setAttribute('aria-label', '选中节点的提示词与模型');
  const top = el('div', 'composer-top');
  const title = el('strong', 'composer-title');
  title.id = 'composer-title';
  const reference = el('button', 'composer-tool', '＋ 添加参考');
  reference.id = 'composer-upload';
  reference.type = 'button';
  reference.onclick = () => {
    // Uploads attach to the selected generation node rather than just appearing nearby.
    placement = {board: board.id, ...centre(), offset: 0, target: selected};
    $('upload').click();
  };
  const expand = el('button', 'composer-tool', '放大编辑 ↗');
  expand.id = 'composer-expand';
  expand.type = 'button'; expand.onclick = () => $('expand-prompt').click();
  const advanced = el('button', 'composer-tool', '高级参数');
  advanced.id = 'composer-advanced';
  advanced.type = 'button';
  advanced.setAttribute('aria-expanded', 'false');
  advanced.onclick = () => {
    const open = !$('inspector').classList.contains('advanced-open');
    $('inspector').classList.toggle('advanced-open', open);
    advanced.setAttribute('aria-expanded', String(open));
  };
  top.append(title, reference, expand, advanced);
  const prompt = el('textarea');
  prompt.id = 'composer-prompt';
  prompt.rows = 4;
  prompt.maxLength = 50000;
  prompt.setAttribute('aria-label', '当前节点提示词');
  prompt.placeholder = '描述画面，输入 @ 引用参考图，或点击“画布参考”选择图片…';
  const bottom = el('div', 'composer-bottom');
  const fields = {};
  for (const [id, original, label] of [
    ['composer-model', 'model', '生成模型'],
    ['composer-ratio', 'ratio', '画面比例'],
    ['composer-style', 'style', '视觉风格'],
  ]) {
    const select = el('select');
    select.id = id; select.setAttribute('aria-label', label);
    select.onchange = () => {
      const node=selected&&nodeBy(selected);
      const invalidate=node?.kind==='stage3d'&&original==='ratio'&&node.settings.ratio!==select.value;
      if(invalidate)delete node.media_id;
      $(original).value = select.value;
      $(original).dispatchEvent(new Event(original === 'model' ? 'change' : 'input'));
      if(invalidate){render();inspector();}
      syncComposer();
    };
    fields[original] = select;
    bottom.append(select);
  }
  const seconds = el('input');
  seconds.id = 'composer-seconds'; seconds.type = 'number';
  seconds.min = 4; seconds.max = 15; seconds.step = .01;
  seconds.setAttribute('aria-label', '视频时长（秒）');
  seconds.oninput = () => { $('seconds').value = seconds.value; updateSettings(); };
  bottom.append(seconds);
  const run = el('button', 'primary', '开始生成');
  run.type = 'submit'; run.id = 'composer-generate';
  bottom.append(run);
  const status = el('p', 'composer-status');
  status.id = 'composer-status'; status.setAttribute('aria-live', 'polite');
  composer.append(top, prompt, bottom, status);
  viewport.append(composer);
  composer.addEventListener('pointerdown', event => event.stopPropagation());
  composer.addEventListener('wheel', event => event.stopPropagation());
  prompt.oninput = () => { $('node-text').value = prompt.value; updateSettings(); };
  composer.onsubmit = protect(async event => {
    event.preventDefault();
    const node = selected && nodeBy(selected);
    if (!node) return;
    if (node.kind === 'note') { await save(); message('文本已保存'); return; }
    if (node.kind === 'stage3d') { await H3Stage.open(node.id); return; }
    if (node.kind === 'reverse') { await runReverse(node); return; }
    $('settings').requestSubmit();
  });
  // preventDefault must run synchronously; protect() defers its callback.
  composer.addEventListener('submit', event => event.preventDefault());

  const language=el('select');language.id='composer-reverse-language';language.setAttribute('aria-label','反推提示词语言');
  for(const [value,label] of [['zh','反推结果 · 中文'],['en','反推结果 · English']]){const option=el('option','',label);option.value=value;language.append(option);}
  language.onchange=()=>{
    const node=nodeBy(selected);if(!node||node.kind!=='reverse')return;
    node.settings.reverse_language=language.value;
    if(node.settings.reverse_prompts?.[language.value])node.text=node.settings.reverse_prompts[language.value];
    touch();render();inspector();
  };
  bottom.prepend(language);
  async function runReverse(node){
    if(busy.has(node.id))return;
    const incoming=doc().edges.filter(edge=>edge.target===node.id).map(edge=>nodeBy(edge.source));
    if(incoming.length!==1||!['image','asset','stage3d'].includes(incoming[0].kind))throw Error('图片反推需要连接一张原图，可从图片节点拖线，或点击“添加参考”上传。');
    const source=incoming[0],url=preview(source);
    if(!url||stateOf(source)!=='COMPLETED_UNREVIEWED')throw Error('上游图片尚未生成或三维构图尚未保存，请先完成上游节点。');
    const graph=board.id;busy.add(node.id);inspector();
    try{
      await save();
      const response=await fetch(url);if(!response.ok)throw Error('无法读取原图，请检查作品是否已删除');
      const blob=await response.blob(),body=new FormData();body.append('image',new File([blob],'reference.png',{type:blob.type}));
      const result=await api('/images/reverse',{method:'POST',body,signal:AbortSignal.timeout(130000)});
      if(board.id!==graph||!nodeBy(node.id))throw Error('画布已改变，无法写入反推结果');
      node.settings.reverse_prompts={zh:result.prompt_zh,en:result.prompt_en,negative:result.negative_prompt||'',model:result.model||''};
      node.text=node.settings.reverse_prompts[node.settings.reverse_language||'zh'];
      touch();await save();render();inspector();message('图片反推已完成。可编辑结果，并拖线传递给图片或视频生成节点。');
    }finally{busy.delete(node.id);inspector();}
  }

  function syncComposer() {
    const node = board && selected && nodeBy(selected);
    const editable = node && ['note', 'image', 'video', 'reverse', 'stage3d'].includes(node.kind);
    composer.hidden = !editable;
    if (!editable) {
      composerNode = null;
      $('inspector').classList.remove('advanced-open');
      advanced.setAttribute('aria-expanded', 'false');
      return;
    }
    if (composerNode !== node.id) {
      $('inspector').classList.remove('advanced-open');
      advanced.setAttribute('aria-expanded', 'false');
    }
    composerNode = node.id;
    title.textContent = node.title;
    if (document.activeElement !== prompt || prompt.value !== (node.text || '')) prompt.value = node.text || '';
    for (const key of ['model', 'ratio', 'style']) {
      fields[key].replaceChildren(...[...$(key).options].map(option => option.cloneNode(true)));
      fields[key].value = $(key).value;
      fields[key].hidden = ['note','reverse'].includes(node.kind) || (key === 'model' && node.kind !== 'image') || (key === 'style' && node.kind === 'stage3d');
    }
    // The currently integrated video generation route uses H3's default workflow.
    let videoModel = $('composer-video-model');
    if (!videoModel) {
      videoModel = el('select'); videoModel.id = 'composer-video-model';
      videoModel.setAttribute('aria-label', '视频生成模型');
      const option = el('option', '', 'Minimax H3'); option.value = 'default';
      videoModel.append(option); bottom.prepend(videoModel);
    }
    videoModel.hidden = node.kind !== 'video';
    language.hidden=node.kind!=='reverse';language.value=node.settings.reverse_language||'zh';
    seconds.hidden = node.kind !== 'video'; seconds.value = $('seconds').value;
    reference.hidden = ['note','stage3d'].includes(node.kind);
    advanced.hidden = node.kind === 'note';
    run.disabled = ['reverse','stage3d'].includes(node.kind)?busy.has(node.id):node.kind !== 'note' && $('generate').disabled;
    run.textContent = node.kind === 'note' ? '保存文本' : node.kind==='reverse'?(busy.has(node.id)?'正在反推…':'开始图片反推'):node.kind==='stage3d'?'打开 3D 导演台':$('generate').textContent;
    status.textContent = node.kind === 'note' ? '文本将按连线顺序传递给生成节点。' : $('input-summary').textContent + ' · ' + $('run-status').textContent;
    if(node.kind==='reverse')status.textContent=busy.has(node.id)?'正在调用已有图片反推服务…':node.settings.reverse_prompts?'反推结果已保存，可继续编辑或拖线作为提示词。':'连接一张已生成图片或上传原图，再开始反推。';
    if(node.kind==='stage3d')status.textContent=node.media_id?'三维构图参考已保存，可拖线给图片或视频生成节点。':'摆放人物和道具，调整摄影机后保存构图参考。';
    if(node.kind==='image'&&['z_image_turbo','flux_dev'].includes(node.settings.variant)&&doc().edges.some(edge=>edge.target===node.id&&!['note','reverse'].includes(nodeBy(edge.source).kind))){
      status.textContent='已连接参考图；当前模型仅支持文生图，请切换 H3-Image 或 Qwen。';run.disabled=true;
    }
    prompt.placeholder=node.kind==='stage3d'?'可填写场景备注；点击下方按钮进入三维摆位与摄影机取景。':node.kind==='reverse'?'图片反推完成后，提示词会显示在这里。':'描述画面，输入 @ 引用参考图，或点击“画布参考”选择图片…';
  }

  const originalInspector = inspector;
  inspector = function() { originalInspector(); syncComposer(); };
  $('prompt-dialog').addEventListener('close', syncComposer);
  $('settings').addEventListener('input', syncComposer);
  const originalAdd = add;
  add = function(kind, extra = {}) {
    const position = placement?.board === board?.id ? {...placement} : null;
    if (position) {
      extra = {...extra, x: position.x + position.offset, y: position.y + position.offset};
      if(position.source && kind==='image' && !['note','reverse'].includes(nodeBy(position.source)?.kind)) {
        extra.settings={variant:'h3_image_w4a8',steps:6,cfg:1,ratio:'16:9',style:'自定义风格',image_task:'general'};
      }
      placement.offset += 30;
    }
    const node = originalAdd(kind, extra);
    if(position?.source && nodeBy(position.source)){
      connection=position.source;connect(node.id);
    }
    if (position?.target && nodeBy(position.target) && node.kind === 'asset') {
      doc().edges.push({source: node.id, target: position.target});
      selected = position.target;
      touch(); render(); inspector();
    }
    if (position && !position.target && kind !== 'asset') placement = null;
    return node;
  };
  const originalUpload = upload;
  upload = async function(files) {
    try { return await originalUpload(files); }
    finally { placement = null; }
  };
  $('upload').addEventListener('cancel', () => placement = null);
  $('library-close').addEventListener('click', () => placement = null);
  $('library-items').addEventListener('click', () => placement = null);
  $('inspector-close').onclick = () => {
    $('inspector').classList.remove('advanced-open');
    advanced.setAttribute('aria-expanded', 'false');
  };
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {closeMenu();cancelWire();}
  });

  // A port press captures on the viewport, so redraws cannot lose the gesture.
  const ghost=document.createElementNS('http://www.w3.org/2000/svg','svg');
  ghost.id='wire-preview';ghost.setAttribute('aria-hidden','true');ghost.style.display='none';
  const ghostPath=document.createElementNS('http://www.w3.org/2000/svg','path');ghost.append(ghostPath);viewport.append(ghost);
  let wire=null,suppressPortClick=false;
  function cancelWire(){
    if(wire&&viewport.hasPointerCapture(wire.pointer))viewport.releasePointerCapture(wire.pointer);
    wire=null;ghost.style.display='none';ghostPath.removeAttribute('d');
  }
  viewport.addEventListener('pointerdown',event=>{
    const port=event.target.closest('.port.out');if(!port||event.button!==0)return;
    event.preventDefault();event.stopImmediatePropagation();closeMenu();
    const source=port.closest('.card').dataset.id;
    wire={source,board:board.id,pointer:event.pointerId,x:event.clientX,y:event.clientY,moved:false};
    select(source);viewport.setPointerCapture(event.pointerId);
  },true);
  document.addEventListener('pointermove',event=>{
    if(!wire||wire.pointer!==event.pointerId)return;
    if(wire.board!==board.id||!nodeBy(wire.source)){cancelWire();return;}
    wire.moved ||= Math.hypot(event.clientX-wire.x,event.clientY-wire.y)>5;
    if(!wire.moved)return;
    const r=viewport.getBoundingClientRect(),port=$('nodes').querySelector(`[data-id="${wire.source}"] .port.out`).getBoundingClientRect();
    const x=port.left+port.width/2-r.left,y=port.top+port.height/2-r.top,tx=event.clientX-r.left,ty=event.clientY-r.top,d=Math.max(40,Math.abs(tx-x)*.35);
    ghost.style.display='block';ghostPath.setAttribute('d',`M ${x} ${y} C ${x+d} ${y}, ${tx-d} ${ty}, ${tx} ${ty}`);
  },true);
  document.addEventListener('pointerup',event=>{
    if(!wire||wire.pointer!==event.pointerId)return;
    const value=wire;cancelWire();event.preventDefault();event.stopImmediatePropagation();suppressPortClick=true;
    setTimeout(()=>suppressPortClick=false,0);
    if(!value.moved){connection=connection===value.source?null:value.source;render();return;}
    const hit=document.elementFromPoint(event.clientX,event.clientY),card=hit?.closest('.card');
    if(card){
      const target=nodeBy(card.dataset.id);
      if(!target||['note','asset','stage3d'].includes(target.kind)){message('请连接图片、视频或图片反推节点的输入端。');return;}
      connection=value.source;connect(target.id);
    }else if(hit?.closest('#viewport')&&!hit.closest('#node-composer,.zoom-controls,button')){
      openMenu(event.clientX,event.clientY,value.source);
    }
  },true);
  document.addEventListener('click',event=>{
    if(suppressPortClick&&viewport.contains(event.target)){event.preventDefault();event.stopImmediatePropagation();suppressPortClick=false;}
  },true);
  viewport.addEventListener('pointercancel',cancelWire);window.addEventListener('blur',cancelWire);
  const originalOpenBoard=openBoard,originalNewBoard=newBoard;
  openBoard=async function(key){if(busy.size||H3Stage.isOpen())throw Error('当前节点正在处理，请完成后再切换画布。');closeMenu();cancelWire();return originalOpenBoard(key);};
  newBoard=async function(){if(busy.size||H3Stage.isOpen())throw Error('当前节点正在处理，请完成后再新建画布。');return originalNewBoard();};
})();
