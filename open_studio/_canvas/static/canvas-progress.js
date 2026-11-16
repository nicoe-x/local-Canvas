/* Generation progress comes from the existing owner-scoped run polling. */
(() => {
  const active=new Set(['QUEUED','STARTING','RUNNING','SUBMITTED','PENDING','CANCELLING','PAUSING','PAUSED','RESUMING']);
  function update(){
    if(!board)return;
    for(const card of $('nodes').children){
      const node=nodeBy(card.dataset.id);if(!node||!['image','video'].includes(node.kind))continue;
      const state=stateOf(node),pending=busy.has(node.id)&&!active.has(state),running=pending||active.has(state);
      let panel=card.querySelector('.node-generation-progress');
      card.setAttribute('aria-busy',String(running));
      if(!running){panel?.remove();continue;}
      const run=latest(node.id),job=jobInfo.get(node.job_id),source=run?.job_state?run:job;
      const value=source?.progress;
      // Zero/missing progress and queue states have no known completion estimate.
      const known=!pending&&state==='RUNNING'&&typeof value==='number'&&Number.isFinite(value)&&value>0&&value<=100;
      const percent=known?Math.round(value):null;
      const fallback={QUEUED:'等待调度',STARTING:'正在启动',SUBMITTED:'已提交，等待开始',PENDING:'提交结果待核对',CANCELLING:'正在取消',PAUSING:'正在暂停',PAUSED:'已暂停',RESUMING:'正在恢复',RUNNING:'正在生成'};
      const stage=pending?'正在提交…':source?.stage||fallback[state]||'正在生成';
      if(!panel){
        panel=el('div','node-generation-progress');
        const caption=el('div','node-progress-caption');caption.append(el('span','node-progress-stage'),el('span','node-progress-percent'));
        const track=el('div','node-progress-track');track.setAttribute('role','progressbar');track.setAttribute('aria-valuemin','0');track.setAttribute('aria-valuemax','100');track.append(el('span','node-progress-fill'));
        panel.append(caption,track);card.querySelector('.card-body').append(panel);
      }
      panel.querySelector('.node-progress-stage').textContent=stage;
      panel.querySelector('.node-progress-percent').textContent=known?percent+'%':'';
      const track=panel.querySelector('.node-progress-track');track.setAttribute('aria-label',node.title+'生成进度');track.setAttribute('aria-valuetext',known?`${stage}，${percent}%`:stage);
      if(known)track.setAttribute('aria-valuenow',String(percent));else track.removeAttribute('aria-valuenow');
      panel.classList.toggle('indeterminate',!known&&!['PAUSED','PENDING'].includes(state));
      panel.classList.toggle('progress-paused',['PAUSED','PENDING'].includes(state));
      panel.querySelector('.node-progress-fill').style.width=known?percent+'%':null;
    }
  }
  const previousRender=render,previousInspector=inspector;
  render=function(){previousRender();update();};
  inspector=function(){previousInspector();update();};
  update();
})();
