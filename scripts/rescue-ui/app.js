'use strict';
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const GiB = 1024 ** 3;
const memory = (n) => n == null ? '—' : (n / GiB).toFixed(2);
const basename = (p) => String(p).split('/').filter(Boolean).pop() || '알 수 없음';
const shortPath = (p) => String(p).replace(/^\/Users\/[^/]+\/Desktop\/repositories\//, '').replace(/^\/Users\/[^/]+\//, '~/');
const duration = (seconds) => seconds >= 86400 ? `${Math.floor(seconds / 86400)}일 ${Math.floor(seconds % 86400 / 3600)}시간` : seconds >= 3600 ? `${Math.floor(seconds/3600)}시간 ${Math.floor(seconds%3600/60)}분` : `${Math.max(1,Math.floor(seconds/60))}분`;
let token = location.hash.slice(1);
try { if (token) sessionStorage.setItem('rescue-token', token); else token = sessionStorage.getItem('rescue-token') || ''; } catch {}
history.replaceState(null,'',location.pathname);
let data = null, view = 'groups', filter = 'all', busy = false, refreshing = false, activePlan = null, expiryTimer = null;
let theme = 'auto';
try { theme = localStorage.getItem('rescue-theme') || 'auto'; } catch {}
const media = matchMedia('(prefers-color-scheme: dark)');
function applyTheme() {
  document.documentElement.dataset.theme = theme === 'auto' ? (media.matches ? 'dark' : 'light') : theme;
  $('#theme').textContent = '화면 테마: ' + ({auto:'자동',dark:'어둡게',light:'밝게'}[theme]);
}
applyTheme(); media.addEventListener('change',applyTheme);
$('#theme').addEventListener('click',() => { theme = ({auto:'dark',dark:'light',light:'auto'}[theme]); try {localStorage.setItem('rescue-theme',theme);} catch {} applyTheme(); });

async function api(path, body) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(),25000);
  try {
    const response = await fetch('/api/'+path,{method:body == null ? 'GET':'POST',headers:{'X-Rescue-Token':token,'Content-Type':'application/json'},body:body == null ? undefined:JSON.stringify(body),signal:controller.signal});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '요청을 처리하지 못했습니다.');
    return result;
  } finally { clearTimeout(timer); }
}
let toastTimer;
function toast(message) { $('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,7000); }

function renderMetrics() {
  const s=data.system, total=data.groups.reduce((sum,g)=>sum+g.footprint,0);
  $('#pressure').textContent=s.pressure;
  $('#pressure').style.color=s.pressure==='정상'?'var(--accent)':s.pressure==='위험'?'var(--red)':'var(--amber)';
  $('#pressure-note').textContent=s.pressure==='정상'?'현재 메모리 압력이 안정적입니다':'큰 실행 그룹부터 확인해 보세요';
  $('#pressure-bar').style.width=s.pressure==='정상'?'25%':s.pressure==='위험'?'100%':'65%';
  $('#pressure-bar').style.background=s.pressure==='정상'?'var(--accent)':s.pressure==='위험'?'var(--red)':'var(--amber)';
  $('#group-memory').innerHTML=memory(total)+'<small>GiB</small>';
  $('#group-note').textContent=`${data.groups.length}개 실행 그룹 · ${data.groups.reduce((n,g)=>n+g.pids.length,0)}개 프로세스`;
  $('#swap').innerHTML=memory(s.swap_used)+'<small>GiB</small>';
  $('#compressed').textContent=`압축 메모리 ${memory(s.compressed)} GiB`;
  $('#disk').innerHTML=memory(s.disk_free)+'<small>GiB</small>';
  $('#ram').textContent=`물리 메모리 ${memory(s.ram)} GiB`;
  $('#sample-time').textContent=new Date(data.time).toLocaleTimeString('ko-KR')+' 측정';
  $('#nav-count').textContent=data.groups.length;
  const series=data.history.map(h=>h.swap_used/GiB), lo=Math.min(...series)-.1, hi=Math.max(...series)+.1;
  $('#sparkline path').setAttribute('d',series.length<2?'M0 12 L240 12':series.map((v,i)=>`${i?'L':'M'}${i/(series.length-1)*240} ${22-(v-lo)/(hi-lo)*20}`).join(' '));
  $('#sparkline').setAttribute('aria-label',`최근 ${series.length}회 스왑 사용 변화`);
}

function groupCells(g) {
  const name=basename(g.project), chrome=g.kind==='chrome';
  const tags=[];
  if(g.footprint>=2*GiB) tags.push('<span class="badge">높은 메모리</span>');
  if(g.age>=86400) tags.push('<span class="badge neutral">24시간 이상</span>');
  if(g.reasons.includes('부모 소실/분리')) tags.push('<span class="badge neutral">분리 실행</span>');
  if(!tags.length) tags.push('<span class="muted">—</span>');
  const ratio=Math.min(100,g.footprint/Math.max(...data.groups.map(x=>x.footprint),1)*100);
  return `<td><div class="project-cell"><div class="project-icon ${chrome?'chrome':''}" aria-hidden="true">${chrome?'◎':'⌘'}</div><div><div class="project-name">${escapeHTML(name)}</div><div class="project-meta" title="${escapeHTML(g.cwd)}">${chrome?'자동화 Chrome':'개발 서버'} · ${g.pids.length}개 · ROOT ${g.root}${g.ports.length?' · :'+g.ports.join(', :'):''}</div></div></div></td><td><div class="memory-num">${memory(g.footprint)}<small>GiB${g.partial?' *':''}</small></div><div class="memory-bar ${g.footprint>=2*GiB?'warm':''}"><i data-width="${ratio}"></i></div></td><td class="age">${duration(g.age)}</td><td>${tags.join('')}</td><td><button class="details-btn" data-detail="${g.root}" aria-label="${escapeHTML(name)} ROOT ${g.root} 상세 보기">상세 <span aria-hidden="true">↗</span></button></td>`;
}

function renderList() {
  if(!data) return;
  const query=$('#search').value.trim().toLowerCase(), sort=$('#sort').value;
  let items=view==='groups'?data.groups:data.rows;
  items=items.filter(item=>{
    const hay=view==='groups'?`${item.project} ${item.cwd} ${item.root} ${item.ports.join(' ')} ${item.kind}`:`${item.name} ${item.cwd} ${item.pid}`;
    return hay.toLowerCase().includes(query)&&(filter!=='memory'||item.footprint>=2*GiB)&&(filter!=='old'||item.age>=86400);
  }).sort((a,b)=>sort==='age'?b.age-a.age:sort==='name'?String(a.project||a.name).localeCompare(String(b.project||b.name)):(b.footprint||0)-(a.footprint||0));
  $('#group-count').textContent=view==='groups'?data.groups.length:data.rows.length;
  $('#result-count').textContent=`${items.length}개 표시`;
  $('#thead').innerHTML=view==='groups'?'<tr><th>프로젝트 / 실행 그룹</th><th>메모리</th><th>실행 시간</th><th>검토 근거</th><th><span class="sr-only">상세 보기</span></th></tr>':'<tr><th>프로세스 / 작업 경로</th><th>메모리</th><th>실행 시간</th><th>PID / 부모 PID</th><th>작업</th></tr>';
  const focus=document.activeElement?.dataset.detail;
  $('#rows').innerHTML=items.length?items.map(item=>view==='groups'?`<tr>${groupCells(item)}</tr>`:`<tr><td><div class="project-name">${escapeHTML(basename(item.name))}</div><div class="project-meta" title="${escapeHTML(item.cwd)}">${escapeHTML(shortPath(item.cwd)||'작업 경로 확인 불가')}</div></td><td class="memory-num">${memory(item.footprint)}<small>GiB</small></td><td class="age">${duration(item.age)}</td><td class="numeric">${item.pid} <span class="muted">/ ${item.ppid}</span></td><td>${item.can_stop?`<button class="tiny-stop" data-stop-pid="${item.pid}" aria-label="PID ${item.pid} 종료 미리보기">종료…</button>`:'<span class="badge neutral">조회 전용</span>'}</td></tr>`).join(''):'<tr><td colspan="5" class="empty"><strong>조건에 맞는 실행이 없습니다.</strong>검색어나 필터를 바꿔 다시 확인해 보세요.</td></tr>';
  $$('[data-width]').forEach(el=>el.style.width=el.dataset.width+'%');
  if(focus) $(`[data-detail="${focus}"]`)?.focus({preventScroll:true});
}

async function refresh() {
  if(busy||refreshing) return;
  refreshing=true;$('#refresh').disabled=true;
  try {
    data=await api('status'); renderMetrics();renderList();
    $('#error').hidden=true;$('#live-text').textContent='실시간 연결';
  } catch(error) {
    $('#error').textContent=error.name==='AbortError'?'응답이 지연되고 있습니다. 잠시 후 새로고침해 주세요.':error.message;
    $('#error').hidden=false;$('#live-text').textContent='연결 확인 필요';
  } finally {refreshing=false;$('#refresh').disabled=false;}
}

function setView(next) {
  view=next;
  $$('.nav').forEach(el=>{el.classList.toggle('active',el.dataset.view===view);el.setAttribute('aria-current',el.dataset.view===view?'page':'false');});
  $('#workspace').hidden=view==='guide';$('#guide').hidden=view!=='guide';
  $('#crumb').textContent=({groups:'실행 그룹',processes:'전체 프로세스',guide:'실행과 복구'}[view]);
  $('#list-title').firstChild.textContent=view==='groups'?'실행 그룹 ':'전체 프로세스 ';
  $('#list-description').textContent=view==='groups'?'같이 시작된 프로세스를 한 묶음으로 보여드립니다.':'시스템과 작업 앱도 함께 표시합니다. 개발·자동화 프로세스만 종료할 수 있습니다.';
  renderList();
}
function detail(root) {
  const g=data.groups.find(x=>x.root===root);if(!g)return;
  const rows=g.pids.map(p=>data.rows.find(r=>r.pid===p)).filter(Boolean);
  const chain=[], seen=new Set();let current=data.rows.find(r=>r.pid===root);
  while(current&&!seen.has(current.pid)){chain.push(current);seen.add(current.pid);current=data.rows.find(r=>r.pid===current.ppid);}
  $('#detail-body').innerHTML=`<h2 id="detail-title">${escapeHTML(basename(g.project))}</h2><div class="path">${escapeHTML(g.cwd)}</div><div class="detail-stats"><div><small>그룹 메모리</small><strong>${memory(g.footprint)} <span class="muted">GiB</span></strong></div><div><small>실행 시간</small><strong>${(g.age/3600).toFixed(1)} <span class="muted">시간</span></strong></div><div><small>프로세스</small><strong>${rows.length} <span class="muted">개</span></strong></div></div><h3>검토 근거</h3><p>${g.reasons.map(x=>`<span class="badge neutral">${escapeHTML(x)}</span>`).join('')||'<span class="muted">특별한 검토 근거가 없습니다.</span>'}</p><div class="detail-note">오래된 실행과 분리된 부모는 정상일 수 있습니다. 지금 사용 중인 작업인지 확인한 뒤 정리하세요.</div><h3>열린 포트</h3><p class="path">${g.ports.map(p=>':'+p).join(' · ')||'확인된 TCP 리스너 없음'}</p><div class="detail-actions"><button class="button danger" data-stop-group="${root}" ${g.can_stop?'':'disabled'}>이 그룹 종료…</button><button class="danger-quiet" data-force-group="${root}" ${g.can_stop?'':'disabled'}>강제 종료…</button></div>${!g.can_stop?'<p class="detail-note">보호된 프로세스가 포함돼 그룹 종료가 제한됩니다.</p>':''}<h3>함께 실행된 프로세스</h3>${rows.map(r=>`<div class="process-row"><div class="process-main"><strong>${escapeHTML(basename(r.name))}</strong><small>PID ${r.pid} · 부모 ${r.ppid}</small></div><code>${memory(r.footprint)} G</code>${r.can_stop?`<button class="tiny-stop" data-stop-pid="${r.pid}" aria-label="PID ${r.pid} 개별 종료 미리보기">종료…</button>`:'<span class="muted">보호됨</span>'}</div>`).join('')}<h3>시작된 경로</h3><div class="ancestry">${chain.reverse().map(r=>`${escapeHTML(basename(r.name))} <span class="numeric">${r.pid}</span>`).join(' → ')}</div>`;
  $('#detail').showModal();
}
async function preview(target,mode,force=false) {
  if(busy) return;busy=true;
  try {
    activePlan=await api('plan',{target,mode,force});
    $('#confirm-title').textContent=force?'선택한 실행을 강제 종료할까요?':'선택한 실행을 종료할까요?';
    $('#confirm-description').textContent=`${basename(activePlan.project)}의 ${mode==='group'?'실행 그룹을':'프로세스 하나를'} 종료합니다.`;
    $('#plan-summary').textContent=`${activePlan.rows.length}개 프로세스 · ${memory(activePlan.footprint)} GiB 점유 · ${force?'SIGKILL':'SIGTERM'}`;
    $('#plan-rows').innerHTML=activePlan.rows.map(r=>`<tr><td class="numeric">${r.pid}</td><td>${escapeHTML(basename(r.name))}</td><td class="numeric">${memory(r.footprint)} G</td></tr>`).join('');
    $('#impact').textContent=(force?'저장·정리 처리를 건너뜁니다. ':'')+'해당 개발 서버의 연결·진행 중 요청 또는 자동화 탭·테스트가 중단됩니다.'+(mode==='pid'?' 부모가 재실행하거나 자식이 남을 수 있습니다.':'');
    $('#phrase').textContent=activePlan.phrase;$('#confirm-input').value='';$('#execute').disabled=true;
    $('#execute').textContent=force?'강제 종료':'실행 종료';$('#confirm-error').hidden=true;
    $('#confirm').showModal();$('#confirm-input').focus();
    clearTimeout(expiryTimer);expiryTimer=setTimeout(()=>{activePlan=null;$('#execute').disabled=true;$('#confirm-error').textContent='미리보기가 만료됐습니다. 닫은 후 다시 확인해 주세요.';$('#confirm-error').hidden=false;},60000);
  }catch(error){toast(error.message);}finally{busy=false;}
}
function cancel(){if(busy)return;$('#confirm').close();activePlan=null;clearTimeout(expiryTimer);}
$('#confirm-input').addEventListener('input',()=>{$('#execute').disabled=!activePlan||$('#confirm-input').value!==activePlan.phrase;});
$('#execute').addEventListener('click',async()=>{
  if(!activePlan||busy)return;busy=true;$('#execute').disabled=true;$('#cancel').disabled=true;$('#cancel-x').disabled=true;clearTimeout(expiryTimer);
  try{
    const result=await api('execute',{id:activePlan.id,phrase:$('#confirm-input').value});
    $('#confirm').close();$('#detail').close();
    const remaining=result.remaining.length+result.new_children.length;
    toast(`${result.sent.length}개에 종료 신호를 보냈습니다.`+(remaining?` 남은/새 PID ${remaining}개는 다시 확인하세요.`:'')+(result.errors.length?' 일부 오류: '+result.errors.join(', '):''));
  }catch(error){$('#confirm-error').textContent=error.message+' 목록을 새로 확인한 뒤 다시 시도하세요.';$('#confirm-error').hidden=false;}
  finally{activePlan=null;busy=false;$('#cancel').disabled=false;$('#cancel-x').disabled=false;await refresh();}
});
$('#cancel').addEventListener('click',cancel);$('#cancel-x').addEventListener('click',cancel);
$('#confirm').addEventListener('cancel',event=>{if(busy)event.preventDefault();else{activePlan=null;clearTimeout(expiryTimer);}});
$('.close-detail').addEventListener('click',()=>$('#detail').close());
document.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.view)setView(button.dataset.view);
  if(button.dataset.filter){filter=button.dataset.filter;$$('[data-filter]').forEach(el=>{el.classList.toggle('active',el.dataset.filter===filter);el.setAttribute('aria-pressed',String(el.dataset.filter===filter));});renderList();}
  if(button.dataset.detail)detail(Number(button.dataset.detail));
  if(button.dataset.stopGroup)preview(Number(button.dataset.stopGroup),'group');
  if(button.dataset.forceGroup)preview(Number(button.dataset.forceGroup),'group',true);
  if(button.dataset.stopPid)preview(Number(button.dataset.stopPid),'pid');
  if(button.dataset.copy)navigator.clipboard.writeText(button.dataset.copy).then(()=>toast('명령을 복사했습니다.')).catch(()=>toast('복사 권한이 없습니다. 명령을 직접 선택해 복사하세요.'));
});
$('#search').addEventListener('input',renderList);$('#sort').addEventListener('change',renderList);$('#refresh').addEventListener('click',refresh);
document.addEventListener('keydown',event=>{if(event.key==='/'&&!['INPUT','TEXTAREA'].includes(event.target.tagName)&&!$('dialog[open]')){event.preventDefault();$('#search').focus();}});
setInterval(()=>{if($('#auto').checked&&!document.hidden&&!$('dialog[open]'))refresh();},15000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&$('#auto').checked&&!$('dialog[open]'))refresh();});
refresh();
