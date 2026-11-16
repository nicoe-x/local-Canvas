/* Directed CSS flow and accessible, graph-only disconnection on existing curves. */
(() => {
  const ns='http://www.w3.org/2000/svg',svg=$('edges');let lastZoom=null,chosen=null,chosenBoard=null;
  function choose(group,fromUser=false){if(group&&fromUser){if(window.H3Selection)window.H3Selection.select([]);else select(null);}chosen=group?group.dataset.source+':'+group.dataset.target:null;chosenBoard=board?.id;for(const item of svg.querySelectorAll('.flow-edge')){const active=item.dataset.source+':'+item.dataset.target===chosen;item.classList.toggle('edge-selected',active);item.querySelector('.edge-cut').hidden=!active;item.querySelector('.edge-hit').setAttribute('aria-pressed',String(active));}}
  document.addEventListener('pointerdown',event=>{if(!event.target.closest('.flow-edge'))choose(null);},true);
  window.addEventListener('keydown',event=>{if(event.key==='Escape')choose(null);},true);
  function element(name,attributes={}){const value=document.createElementNS(ns,name);for(const [key,v] of Object.entries(attributes))value.setAttribute(key,v);return value;}
  function sizeButtons(){
    if(!board)return;const zoom=doc().viewport.zoom;if(lastZoom===zoom)return;lastZoom=zoom;
    for(const group of svg.querySelectorAll('.flow-edge')){
      const holder=group.querySelector('foreignObject'),path=group.querySelector('.edge-base');if(!holder||!path)continue;
      const mid=path.getPointAtLength(path.getTotalLength()/2),size=38/zoom;
      for(const [key,value] of Object.entries({x:mid.x-size/2,y:mid.y-size/2,width:size,height:size}))holder.setAttribute(key,value);
    }
  }
  function disconnect(source,target,key){
    if(board?.id!==key)return;
    const count=doc().edges.length;doc().edges=doc().edges.filter(edge=>edge.source!==source||edge.target!==target);
    if(doc().edges.length===count)return;
    chosen=null;
    touch();render();inspector();message('已断开连接，节点和已生成内容已保留。');
  }
  const original=renderEdges;
  renderEdges=function(){
    original();if(!board)return;if(chosenBoard!==board.id)chosen=null;
    const paths=[...svg.children],edges=doc().edges.filter(edge=>$('nodes').querySelector(`[data-id="${edge.source}"] .port.out`)&&$('nodes').querySelector(`[data-id="${edge.target}"] .port.in`));
    for(let index=0;index<paths.length;index++){
      const base=paths[index],edge=edges[index];if(!edge||base.tagName.toLowerCase()!=='path')continue;
      const group=element('g',{'class':'flow-edge','data-source':edge.source,'data-target':edge.target});base.classList.add('edge-base');
      base.replaceWith(group);group.append(base);
      group.append(element('path',{'class':'edge-flow',d:base.getAttribute('d'),pathLength:100,'aria-hidden':'true'}));
      const hit=element('path',{'class':'edge-hit',d:base.getAttribute('d'),'vector-effect':'non-scaling-stroke',role:'button',tabindex:'0','aria-label':'选择连线：'+(nodeBy(edge.source)?.title||'源节点')+' → '+(nodeBy(edge.target)?.title||'目标节点')});group.append(hit);
      const holder=element('foreignObject',{'class':'edge-cut-holder'}),button=document.createElement('button');button.type='button';button.className='edge-cut';
      const label='断开 '+(nodeBy(edge.source)?.title||'源节点')+' → '+(nodeBy(edge.target)?.title||'目标节点');button.title=label;button.setAttribute('aria-label',label);
      const icon=element('svg',{viewBox:'0 0 24 24','aria-hidden':'true'});icon.append(element('path',{d:'m8 8 12 12M8 16 12 12l8-8M9 6a3 3 0 1 1-6 0 3 3 0 0 1 6 0ZM9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z'}));button.append(icon);holder.append(button);group.append(holder);
      const key=board.id;button.onclick=event=>{event.preventDefault();event.stopPropagation();disconnect(edge.source,edge.target,key);};
      group.addEventListener('click',event=>{if(event.target.closest('.edge-cut'))return;event.stopPropagation();choose(group,true);});
      hit.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();event.stopPropagation();choose(group,true);}});
      button.onkeydown=event=>{if(['Delete','Backspace'].includes(event.key)){event.preventDefault();event.stopPropagation();disconnect(edge.source,edge.target,key);}};
      group.addEventListener('pointerdown',event=>{if(event.button===0){event.stopPropagation();}});
      group.addEventListener('dblclick',event=>event.stopPropagation());
    }
    choose(chosen?[...svg.querySelectorAll('.flow-edge')].find(g=>g.dataset.source+':'+g.dataset.target===chosen):null);
    lastZoom=null;sizeButtons();
  };
  const originalView=view;view=function(){originalView();sizeButtons();};
})();
