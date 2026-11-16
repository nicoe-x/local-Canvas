/* Local-only Three.js blocking editor. Exports camera composition, not a final render. */
'use strict';
window.H3Stage = (() => {
  let active = null, opening = false;
  const defaults = () => ({actors:[{id:uid(),kind:'person',x:-.9,z:0,rotation:20,height:1.75,color:'#6b73b7'},
    {id:uid(),kind:'person',x:.9,z:0,rotation:-20,height:1.7,color:'#bc7c79'}],
    camera:{position:[4,2.5,6],target:[0,1,0],fov:40}});

  async function open(nodeId) {
    if (active || opening) return;
    const node = nodeBy(nodeId);
    if (!node || node.kind !== 'stage3d') return;
    opening = true;
    let THREE, OrbitControls;
    try {
      THREE = await import('/vendor/three/three.module.js');
      ({OrbitControls} = await import('/vendor/three/OrbitControls.js'));
    } catch (error) { opening=false;message('3D组件加载失败，请刷新页面。\n错误代码：H3_STAGE_LOAD'); return; }
    const graphId = board.id;
    const state = structuredClone(node.settings.stage3d || defaults());
    let actorId = state.actors[0]?.id, dirtyStage = false, exported = false;
    const dialog = el('dialog', 'stage-dialog'); dialog.id = 'stage-dialog';
    const toolbar = el('div', 'stage-toolbar');
    const title = el('h2','','3D 导演台');
    const note = el('span','fineprint','摆位与摄影机取景 · 构图参考，不占生成显卡');
    const capture = el('button','primary','保存构图参考');capture.id='stage-capture';
    const close = el('button','','保存并关闭');close.id='stage-close';
    toolbar.append(title,note,capture,close);
    const layout=el('div','stage-layout'),view=el('div','stage-viewport'),panel=el('div','stage-panel');
    view.id='stage-viewport';
    const help=el('div','stage-hint','左键环绕 · 右键平移 · 滚轮缩放；切换“移动物体”后可在地面拖动人物。');view.append(help);
    const preview=el('div','stage-preview');preview.id='stage-preview';
    panel.append(el('h3','','摄影机画面'),preview);
    const status=el('p','fineprint','调整后请重新保存构图参考，新的构图可拖线用于图片或视频生成。');status.id='stage-status';
    panel.append(status);
    function button(label,action,id) { const value=el('button','',label);value.type='button';if(id)value.id=id;value.onclick=action;return value; }
    const actions=el('div','stage-actions');
    for(const [kind,label] of [['person','＋ 人物'],['box','＋ 方块'],['chair','＋ 椅子'],['table','＋ 桌子']]) {
      actions.append(button(label,()=>{
        if(state.actors.length>=30){message('最多30个人物或道具');return;}
        const actor={id:uid(),kind,x:0,z:0,rotation:0,height:kind==='person'?1.75:1,color:'#72939f'};
        state.actors.push(actor);actorId=actor.id;changed();rebuild();syncFields();
      },'stage-add-'+kind));
    }
    panel.append(actions);
    const mode=el('select');mode.id='stage-mode';mode.setAttribute('aria-label','三维编辑操作');
    for(const [value,label] of [['orbit','环绕查看'],['move','移动物体']]){const option=el('option','',label);option.value=value;mode.append(option);}
    panel.append(mode);
    const picker=el('select');picker.id='stage-actor';picker.setAttribute('aria-label','选择人物或道具');
    picker.onchange=()=>{actorId=picker.value;syncFields();};panel.append(picker);
    const actorFields={};
    function field(container,label,id,min,max,step,callback,type='number') {
      const wrap=el('label','',label),input=el('input');input.type=type;input.id=id;
      if(type==='number'){input.min=min;input.max=max;input.step=step;input.required=true;}
      input.oninput=()=>{if(input.checkValidity())callback(type==='color'?input.value:Number(input.value));};
      wrap.append(input);container.append(wrap);return input;
    }
    const actorGrid=el('div','stage-fields');
    for(const [key,label,min,max,step] of [['x','左右 X（米）',-50,50,.1],['z','前后 Z（米）',-50,50,.1],['rotation','朝向（度）',-360,360,5],['height','高度（米）',.3,5,.05]]) {
      actorFields[key]=field(actorGrid,label,'stage-actor-'+key,min,max,step,value=>{
        const actor=state.actors.find(a=>a.id===actorId);if(!actor)return;actor[key]=value;changed();rebuild();
      });
    }
    actorFields.color=field(actorGrid,'标识颜色','stage-actor-color',0,0,0,value=>{const actor=state.actors.find(a=>a.id===actorId);if(actor){actor.color=value;changed();rebuild();}},'color');
    panel.append(el('h3','','人物与道具'),actorGrid,button('删除选中物体',()=>{state.actors=state.actors.filter(a=>a.id!==actorId);actorId=state.actors[0]?.id;changed();rebuild();syncFields();},'stage-remove'));
    panel.append(el('h3','','摄影机'));
    const camFields=[],cameraGrid=el('div','stage-fields');
    for(const [group,names] of [['position',['机位 X','机位高度 Y','机位 Z']],['target',['目标 X','目标高度 Y','目标 Z']]]) {
      for(let axis=0;axis<3;axis++) {
        const input=field(cameraGrid,names[axis],'stage-'+group+'-'+axis,-100,100,.1,value=>{
          const next=[...state.camera[group]];next[axis]=value;
          const pos=group==='position'?next:state.camera.position,target=group==='target'?next:state.camera.target;
          if(pos.reduce((sum,n,i)=>sum+(n-target[i])**2,0)<.01)return;
          state.camera[group]=next;changed();updateCamera();
        });camFields.push([group,axis,input]);
      }
    }
    const fov=field(cameraGrid,'镜头视角 FOV','stage-fov',15,90,1,value=>{state.camera.fov=value;changed();updateCamera();});
    panel.append(cameraGrid);
    const presets=el('div','stage-actions');
    presets.append(button('当前视角作为摄影机',()=>{state.camera.position=editor.position.toArray();state.camera.target=controls.target.toArray();changed();updateCamera();syncCameraFields();},'stage-use-view'),
      button('正面机位',()=>{state.camera={position:[0,1.6,6],target:[0,1,0],fov:40};changed();updateCamera();syncCameraFields();}),
      button('俯视摆位',()=>{editor.position.set(0,12,.01);controls.target.set(0,0,0);controls.update();}));
    panel.append(presets,el('p','fineprint','人物使用比例人偶表示站位和朝向；不会自动替换为角色照片。将构图与人物参考图一起连接给生成节点。'));
    layout.append(view,panel);dialog.append(toolbar,layout);document.body.append(dialog);
    let renderer,previewRenderer;
    try {
      renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
      previewRenderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});
    } catch(error){opening=false;dialog.remove();message('浏览器无法启动WebGL，请开启浏览器硬件加速。\n错误代码：H3_STAGE_WEBGL');return;}
    renderer.setPixelRatio(Math.min(devicePixelRatio,2));previewRenderer.setPixelRatio(1);
    renderer.domElement.id='stage-editor-canvas';previewRenderer.domElement.id='stage-preview-canvas';
    view.prepend(renderer.domElement);preview.append(previewRenderer.domElement);
    const scene=new THREE.Scene();scene.background=new THREE.Color('#dce0e5');
    scene.add(new THREE.HemisphereLight(0xffffff,0x708090,2.5));
    const light=new THREE.DirectionalLight(0xffffff,3);light.position.set(5,8,4);scene.add(light);
    const floor=new THREE.Mesh(new THREE.PlaneGeometry(200,200),new THREE.MeshStandardMaterial({color:0xcccccf,roughness:1}));floor.rotation.x=-Math.PI/2;floor.position.y=-.015;scene.add(floor);
    const grid=new THREE.GridHelper(20,40,0x777e8a,0xa0a5ae);scene.add(grid);
    const editor=new THREE.PerspectiveCamera(45,1,.05,300);editor.position.set(7,6,8);
    const shot=new THREE.PerspectiveCamera(state.camera.fov,16/9,.05,300);
    const controls=new OrbitControls(editor,renderer.domElement);controls.target.set(0,1,0);controls.maxDistance=80;controls.minDistance=1;controls.update();
    const cameraHelper=new THREE.CameraHelper(shot);scene.add(cameraHelper);
    const objects=new THREE.Group();scene.add(objects);
    const dimensions=(node.settings.ratio||'16:9').split(':').map(Number);
    const requestedRatio=dimensions[0]/dimensions[1];
    const ratio=Number.isFinite(requestedRatio)&&requestedRatio>=.5&&requestedRatio<=2?requestedRatio:16/9;
    let disposed=false,frame,drag=null;
    function changed(){dirtyStage=true;exported=false;status.textContent='场景已修改；保存构图参考后才能把新构图用于生成。';}
    function mesh(geometry,material,x,y,z,parent){const result=new THREE.Mesh(geometry,material);result.position.set(x,y,z);parent.add(result);return result;}
    function disposeGroup(group){group.traverse(child=>{child.geometry?.dispose();if(Array.isArray(child.material))child.material.forEach(m=>m.dispose());else child.material?.dispose();});}
    function rebuild(){
      for(const child of [...objects.children]){disposeGroup(child);objects.remove(child);}
      for(const actor of state.actors){
        const group=new THREE.Group();group.userData.actor=actor.id;
        const material=new THREE.MeshStandardMaterial({color:actor.color,roughness:.7});
        const skin=new THREE.MeshStandardMaterial({color:'#e8d5be',roughness:.8});
        const dark=new THREE.MeshStandardMaterial({color:'#222a38',roughness:.8});
        if(actor.kind==='person'){
          mesh(new THREE.SphereGeometry(.12,20,16),skin,0,1.63,0,group);
          mesh(new THREE.BoxGeometry(.31,.48,.19),material,0,1.24,0,group);
          mesh(new THREE.BoxGeometry(.28,.15,.18),material,0,.93,0,group);
          for(const sign of [-1,1]){
            mesh(new THREE.CylinderGeometry(.055,.045,.8,12),dark,sign*.09,.49,0,group);
            mesh(new THREE.BoxGeometry(.11,.08,.23),dark,sign*.09,.05,.055,group);
            const arm=mesh(new THREE.CylinderGeometry(.045,.035,.54,12),material,sign*.22,1.15,0,group);arm.rotation.z=sign*.15;
            mesh(new THREE.SphereGeometry(.045,12,8),skin,sign*.26,.86,0,group);
            mesh(new THREE.SphereGeometry(.013,8,6),dark,sign*.04,1.65,.108,group);
          }
          mesh(new THREE.ConeGeometry(.06,.13,12),skin,0,1.60,.13,group).rotation.x=Math.PI/2;
          group.scale.setScalar(actor.height/1.75);
        }else if(actor.kind==='chair'){
          mesh(new THREE.BoxGeometry(.55,.1,.55),material,0,.48,0,group);
          mesh(new THREE.BoxGeometry(.55,.55,.07),material,0,.8,-.24,group);
          for(const x of [-.22,.22])for(const z of [-.22,.22])mesh(new THREE.BoxGeometry(.05,.45,.05),dark,x,.23,z,group);
          group.scale.setScalar(actor.height);
        }else if(actor.kind==='table'){
          mesh(new THREE.BoxGeometry(1.5,.1,.8),material,0,.75,0,group);
          for(const x of [-.65,.65])for(const z of [-.3,.3])mesh(new THREE.BoxGeometry(.06,.7,.06),dark,x,.35,z,group);
          group.scale.setScalar(actor.height);
        }else mesh(new THREE.BoxGeometry(actor.height,actor.height,actor.height),material,0,actor.height/2,0,group);
        group.position.set(actor.x,0,actor.z);group.rotation.y=actor.rotation*Math.PI/180;objects.add(group);
      }
    }
    function syncFields(){picker.replaceChildren();state.actors.forEach((actor,index)=>{const option=el('option','',`${index+1}. ${{person:'人物',box:'方块',chair:'椅子',table:'桌子'}[actor.kind]}`);option.value=actor.id;picker.append(option);});picker.value=actorId||'';const actor=state.actors.find(a=>a.id===actorId);for(const [key,input] of Object.entries(actorFields)){input.disabled=!actor;if(actor)input.value=actor[key];}}
    function updateCamera(){shot.position.fromArray(state.camera.position);shot.fov=state.camera.fov;shot.aspect=ratio;shot.lookAt(new THREE.Vector3().fromArray(state.camera.target));shot.updateProjectionMatrix();cameraHelper.update();}
    function syncCameraFields(){for(const [group,axis,input] of camFields)input.value=Number(state.camera[group][axis].toFixed(3));fov.value=state.camera.fov;}
    const raycaster=new THREE.Raycaster(),plane=new THREE.Plane(new THREE.Vector3(0,1,0),0),point=new THREE.Vector3();
    function ray(event){const r=renderer.domElement.getBoundingClientRect();raycaster.setFromCamera(new THREE.Vector2((event.clientX-r.left)/r.width*2-1,-(event.clientY-r.top)/r.height*2+1),editor);}
    renderer.domElement.addEventListener('pointerdown',event=>{
      if(mode.value!=='move'||event.button!==0)return;ray(event);
      const hit=raycaster.intersectObjects(objects.children,true)[0];if(!hit)return;
      let group=hit.object;while(group.parent!==objects)group=group.parent;
      actorId=group.userData.actor;syncFields();controls.enabled=false;
      const actor=state.actors.find(a=>a.id===actorId);
      if(raycaster.ray.intersectPlane(plane,point))drag={x:actor.x-point.x,z:actor.z-point.z};
      renderer.domElement.setPointerCapture(event.pointerId);
    });
    renderer.domElement.addEventListener('pointermove',event=>{if(!drag)return;ray(event);if(!raycaster.ray.intersectPlane(plane,point))return;const actor=state.actors.find(a=>a.id===actorId);actor.x=Math.max(-50,Math.min(50,point.x+drag.x));actor.z=Math.max(-50,Math.min(50,point.z+drag.z));changed();rebuild();syncFields();});
    function finishDrag(){drag=null;controls.enabled=true;}
    renderer.domElement.addEventListener('pointerup',finishDrag);renderer.domElement.addEventListener('lostpointercapture',finishDrag);
    function resize(){const width=view.clientWidth,height=view.clientHeight;renderer.setSize(Math.max(1,width),Math.max(1,height));editor.aspect=width/Math.max(1,height);editor.updateProjectionMatrix();const w=Math.max(1,preview.clientWidth);previewRenderer.setSize(w,w/ratio);}
    function animate(){if(disposed)return;grid.visible=true;cameraHelper.visible=true;renderer.render(scene,editor);grid.visible=false;cameraHelper.visible=false;previewRenderer.render(scene,shot);frame=requestAnimationFrame(animate);}
    function persist(){if(board.id!==graphId||!nodeBy(nodeId))throw Error('画布或节点已改变，无法保存');const target=nodeBy(nodeId);target.settings.stage3d=structuredClone(state);if(dirtyStage&&!exported)delete target.media_id;touch();render();inspector();}
    capture.onclick=protect(async()=>{
      capture.disabled=true;
      try{
        persist();await save();grid.visible=false;cameraHelper.visible=false;
        previewRenderer.setSize(1024,Math.round(1024/ratio));previewRenderer.render(scene,shot);
        const blob=await new Promise(resolve=>previewRenderer.domElement.toBlob(resolve,'image/png'));
        if(!blob)throw Error('无法导出摄影机构图');
        const result=await api(`/canvases/${graphId}/media`,{method:'POST',headers:{'Content-Type':'image/png'},body:blob});
        nodeBy(nodeId).media_id=result.media_id;exported=true;dirtyStage=false;touch();await save();render();inspector();
        status.textContent='构图参考已保存，可拖出连线用于生成。';resize();
      }finally{capture.disabled=false;resize();}
    });
    close.onclick=protect(async()=>{persist();await save();dialog.close();});
    dialog.addEventListener('cancel',event=>{event.preventDefault();close.click();});
    function warnUnsaved(event){if(dirtyStage){event.preventDefault();event.returnValue='';}}
    window.addEventListener('beforeunload',warnUnsaved);
    dialog.addEventListener('close',()=>{disposed=true;window.removeEventListener('beforeunload',warnUnsaved);cancelAnimationFrame(frame);controls.dispose();observer.disconnect();disposeGroup(scene);renderer.dispose();previewRenderer.dispose();renderer.forceContextLoss();previewRenderer.forceContextLoss();dialog.remove();active=null;});
    const observer=new ResizeObserver(resize);observer.observe(view);
    active=dialog;opening=false;dialog.showModal();rebuild();syncFields();updateCamera();syncCameraFields();resize();animate();
  }
  return {open, defaults, isOpen:()=>!!active||opening};
})();
