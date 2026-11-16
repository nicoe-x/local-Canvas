/* Screen-sized node-anchored editor, expanded composition and geometry-aware connections. */
'use strict';
(() => {
  const viewport=$('viewport'),composer=$('node-composer'),prompt=$('composer-prompt');
  const expand=$('composer-expand'),upload=$('composer-upload');
  let layoutFrame=0;
  const svg=(name)=>{
    const value=document.createElementNS('http://www.w3.org/2000/svg','svg');
    value.setAttribute('viewBox','0 0 24 24');value.setAttribute('fill','none');
    value.setAttribute('stroke','currentColor');value.setAttribute('stroke-width','1.5');
    value.setAttribute('stroke-linecap','round');value.setAttribute('stroke-linejoin','round');
    value.classList.add('ui-icon');value.setAttribute('aria-hidden','true');
    const paths={plus:'M12 5v14M5 12h14',close:'m6 6 12 12M6 18 18 6',link:'M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2',expand:'M8 3H3v5m13-5h5v5M3 16v5h5m13 0h5v-5',collapse:'M3 8h5V3m8 0v5h5M3 16h5v5m8 0v-5h5'};
    const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',paths[name]||paths.plus);value.append(path);return value;
  };
  document.body.classList.add('node-editor-design');
  const brand=document.querySelector('.brand'),mark=document.createElement('img');
  mark.src='/canvas-favicon.svg?v=20261115-01';mark.alt='';mark.className='canvas-brand-symbol';mark.width=30;mark.height=30;
  const words=el('span','canvas-brand-words');words.append(el('strong','','H3 Canvas'),el('small','','私人创作画布'));
  brand.replaceChildren(mark,words);brand.setAttribute('aria-label','H3 Canvas 私人创作画布');

  const full=el('dialog','full-node-editor');full.id='full-node-editor';full.setAttribute('aria-label','完整节点编辑器');
  document.body.append(full);
  const inspectorPanel=$('inspector'),inspectorHome=document.createComment('inspector-home');inspectorPanel.before(inspectorHome);
  function placeAdvanced(){
    const opened=inspectorPanel.classList.contains('advanced-open');
    if(full.open&&opened){full.append(inspectorPanel);full.classList.add('full-has-advanced');}
    else{inspectorHome.parentNode.insertBefore(inspectorPanel,inspectorHome.nextSibling);full.classList.remove('full-has-advanced');}
  }
  const oldAdvanced=$('composer-advanced').onclick;
  $('composer-advanced').onclick=()=>{oldAdvanced();placeAdvanced();};
  const oldAdvancedClose=$('inspector-close').onclick;
  $('inspector-close').onclick=()=>{oldAdvancedClose();placeAdvanced();};
  const oldEditor=$('prompt-dialog');
  function setExpandLabel(){
    const label=full.open?'收起编辑':'展开编辑';expand.dataset.polishLabel=label;
    expand.replaceChildren(svg(full.open?'collapse':'expand'),el('span','button-label',label));
    expand.setAttribute('aria-label',label);expand.setAttribute('aria-expanded',String(full.open));
  }
  function openFull(){
    if(!selected||composer.hidden||full.open)return;
    if(oldEditor.open)oldEditor.close('cancel');
    full.append(composer);full.showModal();placeAdvanced();setExpandLabel();
    prompt.focus({preventScroll:true});
  }
  function closeFull(){closeMentions();if(full.open)full.close();}
  let backdropPress=false;
  function outsideFull(event){const r=full.getBoundingClientRect();return event.target===full&&(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom);}
  full.addEventListener('pointerdown',event=>{backdropPress=event.button===0&&outsideFull(event);});
  full.addEventListener('pointerup',event=>{if(backdropPress&&outsideFull(event)){if(!mentionList.hidden)closeMentions();else closeFull();}backdropPress=false;});
  full.addEventListener('pointercancel',()=>{backdropPress=false;});
  full.addEventListener('cancel',event=>{event.preventDefault();closeFull();});
  full.addEventListener('close',()=>{
    placeAdvanced();
    viewport.append(composer);setExpandLabel();scheduleLayout();scheduleFrame();
    save().catch(error=>message(error.message));
    expand.focus({preventScroll:true});
  });
  expand.onclick=()=>full.open?closeFull():openFull();
  $('expand-prompt').onclick=openFull;
  prompt.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();composer.requestSubmit();}});
  upload.dataset.polishLabel='上传';upload.replaceChildren(svg('plus'),el('span','button-label','上传'));upload.setAttribute('aria-label','上传参考图片');

  const lockNote=el('p','fineprint');lockNote.id='model-locked-params';$('image-params').after(lockNote);
  const references=el('div','dock-references');references.id='dock-references';references.hidden=true;
  composer.querySelector('.composer-top').after(references);
  const referenceButton=el('button','composer-tool');referenceButton.type='button';referenceButton.id='composer-canvas-reference';
  referenceButton.append(svg('link'),el('span','button-label','画布参考'));referenceButton.setAttribute('aria-label','选择画布参考图');
  upload.after(referenceButton);
  let pickTarget=null,pickBoard=null,range=null,mentionIndex=0,pickClickUntil=0,mentionOwner=null;
  const mentionList=el('div','reference-mentions');mentionList.id='reference-mentions';mentionList.hidden=true;
  mentionList.setAttribute('role','dialog');mentionList.setAttribute('aria-label','引用素材');composer.append(mentionList);
  const mentionMain=el('div','reference-menu-main'),mentionSearch=el('input','reference-menu-search'),mentionContent=el('div','reference-menu-content'),mentionSub=el('div','reference-menu-sub');
  mentionSearch.type='search';mentionSearch.placeholder='搜索';mentionSearch.setAttribute('aria-label','搜索画布素材');mentionSearch.autocomplete='off';mentionSub.hidden=true;mentionSub.setAttribute('role','listbox');mentionSub.setAttribute('aria-label','分类素材');
  mentionMain.append(mentionSearch,mentionContent);mentionList.append(mentionMain,mentionSub);
  let mentionQuery='',mentionCategory=null,menuAnchor=null;
  prompt.placeholder='描述画面，输入 @ 引用参考图，或点击“画布参考”选择图片…';
  prompt.setAttribute('aria-autocomplete','list');prompt.setAttribute('aria-controls',mentionList.id);prompt.setAttribute('aria-expanded','false');
  const pickButton=el('button','composer-tool');pickButton.type='button';pickButton.id='composer-pick-reference';pickButton.textContent='画布点选';pickButton.setAttribute('aria-pressed','false');referenceButton.after(pickButton);
  const pickBanner=el('div','reference-pick-banner');pickBanner.hidden=true;pickBanner.setAttribute('role','status');
  const cancelPick=el('button','','取消');cancelPick.type='button';cancelPick.onclick=()=>stopPicking();pickBanner.append(el('span','','点击画布中的一张图片作为参考 · Esc 取消'),cancelPick);viewport.append(pickBanner);
  function eligible(node,target){return node&&node.id!==target?.id&&['image','asset','stage3d'].includes(node.kind)&&preview(node)&&stateOf(node)==='COMPLETED_UNREVIEWED';}
  function closeMentions(){mentionList.hidden=true;referenceButton.setAttribute('aria-expanded','false');mentionSub.hidden=true;mentionCategory=null;menuAnchor=null;prompt.setAttribute('aria-expanded','false');prompt.removeAttribute('aria-activedescendant');mentionSearch.removeAttribute('aria-activedescendant');}
  function stopPicking(){pickTarget=null;pickBoard=null;pickBanner.hidden=true;document.body.classList.remove('picking-reference');pickButton.setAttribute('aria-pressed','false');}
  function beginPicking(){
    const target=selected&&nodeBy(selected);if(!target||!['image','video','reverse'].includes(target.kind))return;
    if(full.open){message('请先收起编辑器，再点选画布中的图片。');return;}
    if(pickTarget){stopPicking();return;}
    range={start:prompt.selectionStart,end:prompt.selectionEnd};pickTarget=target.id;pickBoard=board.id;closeMentions();
    document.body.classList.add('picking-reference');pickBanner.hidden=false;pickButton.setAttribute('aria-pressed','true');
  }
  pickButton.onclick=beginPicking;
  function useReference(source,targetId=selected){
    const target=targetId&&nodeBy(targetId);const isText=['note','reverse'].includes(source?.kind)&&source.text?.trim();if(!target||(!isText&&!eligible(source,target)))return false;
    const existing=doc().edges.some(edge=>edge.source===source.id&&edge.target===target.id);
    const count=doc().edges.filter(edge=>edge.target===target.id&&!['note','reverse'].includes(nodeBy(edge.source).kind)).length;
    const limit=target.kind==='reverse'?1:target.kind==='image'?4:9;
    if(!existing&&!isText&&count>=limit){message(`当前节点最多连接 ${limit} 张参考图，请先移除已有参考。`);return false;}
    if(!existing){connection=source.id;connect(target.id);connection=null;if(!doc().edges.some(e=>e.source===source.id&&e.target===target.id))return false;}
    if(isText){
      const text=target.text||'',start=Math.min(range?.start??text.length,text.length),end=Math.min(range?.end??start,text.length);target.text=text.slice(0,start)+text.slice(end);
      closeMentions();stopPicking();touch();render();inspector();message('已引用文本，生成时会合并该节点的提示词内容。');
    }else if(target.kind!=='reverse'){
      const aliases=target.settings.reference_mentions||={};let alias=Object.keys(aliases).find(key=>aliases[key]===source.id);
      if(!alias){let n=1;while(aliases['参考图'+n])n++;alias='参考图'+n;aliases[alias]=source.id;}
      const text=target.text||'',start=Math.min(range?.start??text.length,text.length),end=Math.min(range?.end??start,text.length);
      target.text=text.slice(0,start)+'@'+alias+' '+text.slice(end);const caret=start+alias.length+2;
      closeMentions();stopPicking();touch();render();inspector();prompt.focus({preventScroll:true});prompt.setSelectionRange(caret,caret);
    }else{closeMentions();stopPicking();touch();render();inspector();}
    range=null;requestAnimationFrame(()=>{if(selected===target.id)prompt.focus({preventScroll:true});});save().catch(error=>message(error.message));scheduleLayout();return true;
  }
  // Capture before node drag/select handlers; reference picking keeps its target.
  document.addEventListener('pointerdown',event=>{
    if(!pickTarget)return;
    if(board?.id!==pickBoard||!nodeBy(pickTarget)){stopPicking();return;}
    const card=event.target.closest('#nodes .card');if(!card||event.button!==0)return;
    event.preventDefault();event.stopImmediatePropagation();pickClickUntil=Date.now()+500;const source=nodeBy(card.dataset.id);
    if(!eligible(source,nodeBy(pickTarget))){message('请选择已完成的图片、上传素材或已保存的三维构图。');return;}
    useReference(source,pickTarget);
  },true);
  document.addEventListener('click',event=>{if(Date.now()>pickClickUntil||!event.target.closest('#nodes .card'))return;event.preventDefault();event.stopImmediatePropagation();},true);
  window.addEventListener('keydown',event=>{if(pickTarget&&event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();stopPicking();}},true);
  function menuItems(){return [...mentionList.querySelectorAll('[role=option]')].filter(n=>!n.disabled&&!n.closest('[hidden]'));}
  function highlightMention(){
    const items=menuItems();items.forEach((item,index)=>{const active=index===mentionIndex;item.setAttribute('aria-selected',String(active));if(active){prompt.setAttribute('aria-activedescendant',item.id);mentionSearch.setAttribute('aria-activedescendant',item.id);item.scrollIntoView({block:'nearest'});}});
  }
  function allMaterials(target){return doc().nodes.filter(n=>n.id!==target.id&&(['note','reverse'].includes(n.kind)?!!n.text?.trim():!!preview(n)&&stateOf(n)==='COMPLETED_UNREVIEWED'));}
  function categoryOf(node){return ['note','reverse'].includes(node.kind)?'text':node.kind==='video'?'video':node.kind==='asset'?'asset':'image';}
  function searchMatches(node,query,target){return (node.title||'未命名素材').toLocaleLowerCase().includes(query)||Object.entries(target.settings.reference_mentions||{}).some(([alias,id])=>id===node.id&&alias.includes(query));}
  const categoryNames={image:'图片',video:'视频',audio:'音频',text:'文本',asset:'资产'};
  const categoryPaths={image:'M4 4h16v16H4z M4 16l5-5 4 4 3-3 4 4 M8 8h.01',video:'M3 5h13v14H3z M16 9l5-3v12l-5-3',audio:'M4 9v6M8 5v14M12 3v18M16 7v10M20 9v6',text:'M5 4h14v16H5z M8 8h8M8 12h8M8 16h5',asset:'M3 7h7l2-3h9v16H3z'};
  function categoryIcon(kind){const icon=svg('link');icon.querySelector('path').setAttribute('d',categoryPaths[kind]);return icon;}
  function itemButton(node,target,inSub=false){
    const button=el('button','reference-mention');button.type='button';button.id='mention-'+node.id+(inSub?'-category':'');button.dataset.referenceId=node.id;button.setAttribute('role','option');
    if(preview(node)){const image=el('img');image.src=preview(node);image.alt='';image.loading='lazy';button.append(image);}else button.append(categoryIcon(categoryOf(node)));
    button.append(el('span','reference-item-name',node.title||'未命名素材'));
    if(node.kind==='video'||(target.kind==='reverse'&&['note','reverse'].includes(node.kind))){button.disabled=true;button.title=node.kind==='video'?'当前生成适配器暂不支持视频素材引用':'图片反推只支持引用一张图片';button.append(el('small','','暂不支持'));}
    else{button.onpointerdown=event=>event.preventDefault();button.onclick=()=>useReference(node,target.id);}
    return button;
  }
  function renderMenu(){
    const target=selected&&nodeBy(selected);if(!target){closeMentions();return;}
    mentionContent.replaceChildren();mentionSub.replaceChildren();mentionIndex=0;
    const available=allMaterials(target),query=mentionQuery.trim().toLocaleLowerCase();
    const connected=doc().edges.filter(e=>e.target===target.id).map(e=>nodeBy(e.source)).filter(n=>n&&available.some(a=>a.id===n.id));
    if(query){
      mentionCategory=null;mentionSub.hidden=true;mentionContent.append(el('p','reference-menu-label','搜索结果'));
      const found=available.filter(n=>searchMatches(n,query,target));for(const node of found)mentionContent.append(itemButton(node,target));
      if(!found.length)mentionContent.append(el('p','reference-menu-empty','没有匹配的素材'));
    }else{
      mentionContent.append(el('p','reference-menu-label','已引用'));
      const linked=el('div','reference-linked-list');linked.setAttribute('role','listbox');linked.setAttribute('aria-label','已连接素材');
      for(const node of connected)linked.append(itemButton(node,target));
      if(!connected.length)linked.append(el('p','reference-menu-empty','暂无已引用素材'));
      mentionContent.append(linked,el('p','reference-menu-label','素材引用'));
      for(const kind of ['image','video','audio','text','asset']){
        const row=el('button','reference-category');row.type='button';row.dataset.category=kind;row.setAttribute('aria-haspopup','listbox');row.setAttribute('aria-expanded',String(mentionCategory===kind));
        row.append(categoryIcon(kind),el('span','',categoryNames[kind]),el('span','reference-chevron','›'));
        const open=()=>{mentionCategory=kind;renderCategory();};row.onclick=open;row.onpointerenter=open;mentionContent.append(row);
      }
      if(mentionCategory)renderCategory();else mentionSub.hidden=true;
    }
    highlightMention();positionMenu();
  }
  function renderCategory(){
    const target=selected&&nodeBy(selected);if(!target||!mentionCategory)return;
    mentionSub.replaceChildren();mentionSub.hidden=false;mentionIndex=0;
    const head=el('div','reference-sub-head'),back=el('button','','‹');back.type='button';back.setAttribute('aria-label','返回素材分类');back.onclick=()=>{mentionCategory=null;mentionSub.hidden=true;mentionSearch.focus();};head.append(back,el('strong','',categoryNames[mentionCategory]));mentionSub.append(head);
    const items=allMaterials(target).filter(n=>categoryOf(n)===mentionCategory);for(const node of items)mentionSub.append(itemButton(node,target,true));
    if(!items.length)mentionSub.append(el('p','reference-menu-empty','画布中暂无'+categoryNames[mentionCategory]+'素材'));
    for(const row of mentionContent.querySelectorAll('[data-category]')){row.setAttribute('aria-expanded',String(row.dataset.category===mentionCategory));row.classList.toggle('active',row.dataset.category===mentionCategory);}
    positionMenu();
  }
  function caretAnchor(){
    const rect=prompt.getBoundingClientRect(),mirror=document.createElement('div'),style=getComputedStyle(prompt);
    for(const name of ['fontFamily','fontSize','fontWeight','lineHeight','letterSpacing','paddingTop','paddingRight','paddingBottom','paddingLeft','borderTopWidth','borderRightWidth','borderBottomWidth','borderLeftWidth','boxSizing','wordSpacing','tabSize'])mirror.style[name]=style[name];
    Object.assign(mirror.style,{position:'fixed',visibility:'hidden',whiteSpace:'pre-wrap',overflowWrap:'break-word',width:rect.width+'px',left:rect.left+'px',top:rect.top+'px'});
    mirror.textContent=prompt.value.slice(0,range?.start??prompt.selectionStart);const marker=document.createElement('span');marker.textContent='@';mirror.append(marker);document.body.append(mirror);const point=marker.getBoundingClientRect();mirror.remove();
    return {x:Math.max(rect.left+8,Math.min(rect.right-12,point.left-prompt.scrollLeft)),y:Math.max(rect.top+8,Math.min(rect.bottom-8,point.bottom-prompt.scrollTop))};
  }
  function positionMenu(){
    if(mentionList.hidden)return;
    const point=menuAnchor||caretAnchor(),margin=12,mainWidth=Math.min(224,innerWidth-24),mainLeft=Math.max(margin,Math.min(point.x,innerWidth-mainWidth-margin));
    const hasSub=!mentionSub.hidden,right=innerWidth-mainLeft-mainWidth-margin,left=mainLeft-margin,reverse=hasSub&&right<228&&left>=228,stacked=hasSub&&right<228&&left<228;
    mentionList.style.setProperty('--reference-menu-width',mainWidth+'px');mentionList.classList.toggle('reference-menu-stacked',stacked);mentionList.classList.toggle('reference-menu-left',reverse);
    mentionList.style.left=(reverse?mainLeft-228:mainLeft)+'px';
    const height=Math.min(mentionList.getBoundingClientRect().height,innerHeight-24),below=point.y+8;
    mentionList.style.top=Math.max(margin,Math.min(below,innerHeight-height-margin))+'px';
  }
  function suggest(){
    const target=selected&&nodeBy(selected);if(!target||!['image','video'].includes(target.kind)||prompt.selectionStart!==prompt.selectionEnd){closeMentions();return;}
    const match=prompt.value.slice(0,prompt.selectionStart).match(/@([^@\s]*)$/u);
    if(!match){closeMentions();return;}
    mentionOwner=target.id;const at=prompt.selectionStart-match[1].length-1;range={start:at,end:prompt.selectionStart};
    mentionQuery=match[1];mentionSearch.value=mentionQuery;mentionCategory=null;mentionSub.hidden=true;menuAnchor=caretAnchor();
    mentionList.hidden=false;prompt.setAttribute('aria-expanded','true');renderMenu();
  }
  mentionSearch.addEventListener('input',()=>{mentionQuery=mentionSearch.value;mentionCategory=null;renderMenu();});
  function menuKeys(event){
    if(event.isComposing||mentionList.hidden)return;
    const items=menuItems();
    if(event.key==='ArrowRight'&&!mentionQuery){event.preventDefault();event.stopImmediatePropagation();mentionCategory=mentionCategory||'image';renderCategory();const first=mentionSub.querySelector('[role=option]:not(:disabled)');first?.focus();return;}
    if(event.key==='ArrowLeft'&&mentionCategory){event.preventDefault();event.stopImmediatePropagation();mentionCategory=null;mentionSub.hidden=true;mentionSearch.focus();return;}
    if(['ArrowDown','ArrowUp','Enter','Escape'].includes(event.key)){
      event.preventDefault();event.stopImmediatePropagation();
      if(event.key==='Escape'){closeMentions();prompt.focus({preventScroll:true});return;}
      if(event.key==='Enter'){if(event.target.matches('[data-category]'))event.target.click();else if(event.target.closest('.reference-menu-sub')&&event.target.matches('[role=option]'))event.target.click();else items[mentionIndex]?.click();return;}
      if(items.length){mentionIndex=(mentionIndex+(event.key==='ArrowDown'?1:-1)+items.length)%items.length;highlightMention();}
    }
  }
  window.addEventListener('keydown',event=>{if(!mentionList.hidden&&event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();closeMentions();prompt.focus({preventScroll:true});}},true);
  prompt.addEventListener('input',event=>{if(!event.isComposing)suggest();});prompt.addEventListener('compositionend',suggest);
  prompt.addEventListener('keydown',menuKeys,true);mentionList.addEventListener('keydown',menuKeys,true);
  prompt.addEventListener('scroll',()=>{if(!mentionList.hidden){menuAnchor=caretAnchor();positionMenu();}});
  window.addEventListener('resize',positionMenu);window.addEventListener('scroll',positionMenu,true);
  let dismissPromptClick=false;
  prompt.addEventListener('click',()=>{if(dismissPromptClick){dismissPromptClick=false;return;}suggest();});
  document.addEventListener('pointerdown',event=>{if(!mentionList.hidden&&!mentionList.contains(event.target)&&!referenceButton.contains(event.target)){dismissPromptClick=event.target===prompt;closeMentions();}},true);
  referenceButton.setAttribute('aria-haspopup','dialog');referenceButton.setAttribute('aria-controls',mentionList.id);referenceButton.setAttribute('aria-expanded','false');
  referenceButton.onclick=()=>{
    const target=selected&&nodeBy(selected);if(!target)return;
    if(!mentionList.hidden){closeMentions();return;}
    stopPicking();range={start:prompt.selectionStart,end:prompt.selectionEnd};mentionOwner=target.id;mentionQuery='';mentionSearch.value='';mentionCategory=null;mentionSub.hidden=true;
    const rect=referenceButton.getBoundingClientRect();menuAnchor={x:rect.left,y:rect.bottom};mentionList.hidden=false;referenceButton.setAttribute('aria-expanded','true');prompt.setAttribute('aria-expanded','true');renderMenu();mentionSearch.focus({preventScroll:true});
  };
  function renderReferences(){
    const node=selected&&nodeBy(selected);if(mentionOwner!==node?.id)closeMentions();references.replaceChildren();
    const edges=node?doc().edges.filter(edge=>edge.target===node.id):[];
    references.hidden=!edges.length;
    referenceButton.hidden=!node||!['image','video','reverse'].includes(node.kind);pickButton.hidden=referenceButton.hidden;
    if(pickTarget&&(node?.id!==pickTarget||board?.id!==pickBoard))stopPicking();
    let mediaNumber=0;
    for(const edge of edges){
      const source=nodeBy(edge.source),chip=el('div','dock-reference');
      const imageUrl=preview(source),media=imageUrl&&stateOf(source)==='COMPLETED_UNREVIEWED';
      if(media){mediaNumber++;chip.classList.add('image-reference-chip');const image=el('img');image.src=imageUrl;image.alt='';chip.append(image,el('span','reference-index',String(mediaNumber)));}
      else chip.append(svg('link'));
      const alias=Object.keys(node.settings.reference_mentions||{}).find(key=>node.settings.reference_mentions[key]===source.id);const label=el('button','reference-chip-insert',(alias?'@'+alias+' · ':'')+source.title);label.type='button';label.title='点击在提示词中引用 '+source.title;label.setAttribute('aria-label',label.title);label.onclick=()=>{range={start:prompt.selectionStart,end:prompt.selectionEnd};useReference(source);};chip.append(label);
      const remove=el('button','reference-chip-remove');remove.type='button';remove.append(svg('close'));remove.setAttribute('aria-label','移除参考 '+source.title);
      remove.onclick=()=>{const aliases=node.settings.reference_mentions||{};for(const [alias,id] of Object.entries(aliases)){if(id===source.id){node.text=(node.text||'').replace(new RegExp('@'+alias+'(?![0-9])','g'),'');delete aliases[alias];}}doc().edges=doc().edges.filter(item=>item!==edge);touch();render();inspector();save().catch(error=>message(error.message));};
      chip.append(remove);references.append(chip);
    }
  }

  function updateFrames(){
    if(!board)return;
    for(const card of $('nodes').children){
      const node=nodeBy(card.dataset.id);if(!node)continue;
      card.dataset.kind=node.kind;
      const body=card.querySelector('.card-body'),image=body.querySelector('img');
      let ratio=node.settings?.ratio||'16:9';
      if(node.kind==='asset'&&image?.naturalWidth)ratio=`${image.naturalWidth}/${image.naturalHeight}`;
      else ratio=ratio.replace(':','/');
      const numbers=ratio.split('/').map(Number);
      if(!numbers.every(Number.isFinite)||numbers[1]<=0||numbers[0]/numbers[1]<.25||numbers[0]/numbers[1]>4)ratio='1/1';
      const aspect=['note','reverse'].includes(node.kind)?'auto':ratio;
      if(body.dataset.aspect!==aspect){body.style.aspectRatio=aspect;body.dataset.aspect=aspect;}
      for(const port of card.querySelectorAll('.port')){
        const top=(body.offsetTop+body.offsetHeight/2-port.offsetHeight/2)+'px';
        if(port.style.top!==top)port.style.top=top;
        if(!port.dataset.circularPort){port.replaceChildren(svg('plus'));port.dataset.circularPort='true';}
      }
    }
  }
  renderEdges=function(){
    if(!board)return;
    updateFrames();
    const positions=new Map();
    for(const card of $('nodes').children){
      const node=nodeBy(card.dataset.id);if(!node)continue;
      const ports={};for(const side of ['in','out']){const port=card.querySelector('.port.'+side);if(port)ports[side]={x:node.x+port.offsetLeft+port.offsetWidth/2,y:node.y+port.offsetTop+port.offsetHeight/2};}
      positions.set(node.id,ports);
    }
    $('edges').replaceChildren();
    for(const edge of doc().edges){
      const a=positions.get(edge.source)?.out,b=positions.get(edge.target)?.in;if(!a||!b)continue;
      const path=document.createElementNS('http://www.w3.org/2000/svg','path'),d=Math.max(28,Math.abs(b.x-a.x)*.35);
      path.setAttribute('d',`M ${a.x} ${a.y} C ${a.x+d} ${a.y}, ${b.x-d} ${b.y}, ${b.x} ${b.y}`);$('edges').append(path);
    }
    scheduleLayout();
  };
  function positionDock(){
    layoutFrame=0;
    if(!board||!selected||composer.hidden||full.open)return;
    const card=$('nodes').querySelector(`[data-id="${selected}"]`);if(!card)return;
    const outer=viewport.getBoundingClientRect(),rect=card.getBoundingClientRect();
    const width=Math.max(180,Math.min(680,outer.width-24));composer.style.width=width+'px';
    const height=composer.offsetHeight,maxLeft=Math.max(12,outer.width-width-12),maxTop=Math.max(12,outer.height-height-76);
    const left=Math.max(12,Math.min(maxLeft,rect.left-outer.left+(rect.width-width)/2));
    let top=rect.bottom-outer.top+12;
    const above=rect.top-outer.top-height-12;
    if(top>maxTop&&above>=12)top=above;
    top=Math.max(12,Math.min(maxTop,top));
    const changed=composer.style.left!==left+'px'||composer.style.top!==top+'px';
    composer.style.left=left+'px';composer.style.top=top+'px';
    if(changed&&!mentionList.hidden){menuAnchor=caretAnchor();positionMenu();}
  }
  function scheduleLayout(){if(!layoutFrame)layoutFrame=requestAnimationFrame(positionDock);}
  function scheduleFrame(){scheduleLayout();}
  window.addEventListener('pointerdown',event=>{if(event.target.closest('.port.out'))document.body.classList.add('reference-drag');},true);
  window.addEventListener('pointerup',()=>{requestAnimationFrame(()=>document.body.classList.remove('reference-drag'));},true);
  window.addEventListener('pointercancel',()=>{document.body.classList.remove('reference-drag');},true);
  window.addEventListener('blur',()=>{document.body.classList.remove('reference-drag');});
  const originalView=view,originalRender=render,originalInspector=inspector;
  view=function(){originalView();scheduleLayout();};
  render=function(){originalRender();updateFrames();renderEdges();document.body.classList.toggle('connection-pending',!!connection);scheduleLayout();};
  inspector=function(){
    originalInspector();renderReferences();setExpandLabel();scheduleLayout();
    const node=board&&selected&&nodeBy(selected),variant=node?.settings?.variant||'z_image_turbo',fixed=node?.kind==='image'&&['z_image_turbo','h3_image_w4a8'].includes(variant);
    lockNote.hidden=!fixed;lockNote.textContent=fixed?(variant==='z_image_turbo'?'Z-Image Turbo 固定使用 8 步 / CFG 1。':'H3 Image 固定使用 6 步 / CFG 1。')+'选择 Qwen 可调整采样步数和 CFG；画幅、风格和种子可以修改。':'';
    if(fixed)$('image-params').hidden=true;
    // A single click opens editing without moving the target under the pointer.
    // Explicit double-click inspection owns camera centering.
  };
  $('nodes').addEventListener('load',()=>{updateFrames();renderEdges();scheduleLayout();},true);
  composer.addEventListener('change',event=>{if(event.target.id==='composer-ratio'){updateFrames();renderEdges();scheduleFrame();}});
  new ResizeObserver(()=>scheduleLayout()).observe(composer);
  new ResizeObserver(()=>{scheduleLayout();renderEdges();}).observe(viewport);
  new MutationObserver(records=>{
    if(records.some(record=>[...record.removedNodes].some(node=>node.id==='stage-dialog')))scheduleFrame();
  }).observe(document.body,{childList:true});
  window.addEventListener('resize',scheduleLayout);
  const originalOpen=openBoard;
  openBoard=async function(key){if(full.open)closeFull();closeMentions();stopPicking();return originalOpen(key);};
  const originalConnect=connect;
  connect=function(target){const source=connection;originalConnect(target);if(source&&doc().edges.some(edge=>edge.source===source&&edge.target===target))select(target);};
  fit=function(){
    if(!board||!doc().nodes.length||full.open)return;
    const r=viewport.getBoundingClientRect(),reserve=composer.hidden?70:composer.getBoundingClientRect().height+100;
    const bounds=doc().nodes.map(node=>{const card=$('nodes').querySelector(`[data-id="${node.id}"]`);return{x:node.x,y:node.y,w:card?.offsetWidth||290,h:card?.offsetHeight||350};});
    const left=Math.min(...bounds.map(b=>b.x)),top=Math.min(...bounds.map(b=>b.y)),w=Math.max(...bounds.map(b=>b.x+b.w))-left,h=Math.max(...bounds.map(b=>b.y+b.h))-top;
    const area=Math.max(100,r.height-reserve),v=doc().viewport;v.zoom=Math.max(.15,Math.min(1,(r.width-100)/w,(area-60)/h));
    v.x=(r.width-w*v.zoom)/2-left*v.zoom;v.y=70+(area-h*v.zoom)/2-top*v.zoom;view();touch();scheduleLayout();
  };
  const help=$('help-dialog').querySelector('form'),line=el('p','','提示词与模型面板跟随选中节点移动，优先显示在节点下方，靠近边缘时自动避让；面板大小不随画布缩放。点击空白处关闭引用菜单或放大编辑框。Ctrl+Enter 运行当前节点。');help.insertBefore(line,help.lastElementChild);
})();
