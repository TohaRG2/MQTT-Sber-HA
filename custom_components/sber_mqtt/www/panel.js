// Sber MQTT Bridge — панель управления
// Токен вшивается сервером: window.HA_ACCESS_TOKEN


// ═══════════════════════════════════════════════════════════
// API
// ═══════════════════════════════════════════════════════════
// ── API ──────────────────────────────────────────────────────────
// Токен вшит в страницу сервером (window.HA_ACCESS_TOKEN).
// Используется для Bearer авторизации API запросов.
let _token = window.HA_ACCESS_TOKEN || null;

async function api(url, opts={}) {
  const headers = { 'Content-Type': 'application/json' };
  if (_token) headers['Authorization'] = 'Bearer ' + _token;
  const r = await fetch(url, { headers, ...opts });
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e.error || `HTTP ${r.status}`);
  }
  return r.json();
}

// ================================================================

// ═══════════════════════════════════════════════════════════
// КОНФИГУРАЦИЯ И СОСТОЯНИЕ
// ═══════════════════════════════════════════════════════════
const TYPE_LABELS = { relay:'Реле', sensor_temp:'Датчик температуры/влажности', scenario_button:'Сценарная кнопка', hvac_ac:'Кондиционер', vacuum_cleaner:'Пылесос', valve:'Кран', light:'Лампа', cover:'Рулонные шторы / жалюзи', water_leak:'Датчик протечки', humidifier:'Увлажнитель воздуха', socket:'Розетка', smoke:'Датчик дыма' };
const STEPS = {
  relay:           ['Тип устройства','Источник в HA','Параметры'],
  sensor_temp:     ['Тип устройства','Датчики в HA','Параметры'],
  scenario_button: ['Тип устройства','Источник в HA','Параметры'],
  hvac_ac:         ['Тип устройства','Источник в HA','Параметры'],
  vacuum_cleaner:  ['Тип устройства','Источник в HA','Параметры'],
  valve:           ['Тип устройства','Источник в HA','Параметры'],
  light:           ['Тип устройства','Источник в HA','Параметры'],
  cover:           ['Тип устройства','Источник в HA','Параметры'],
  water_leak:      ['Тип устройства','Датчик в HA','Параметры'],
  smoke:           ['Тип устройства','Датчик в HA','Параметры'],
  humidifier:      ['Тип устройства','Источник в HA','Параметры'],
  socket:          ['Тип устройства','Источник в HA','Параметры'],
};

let devices=[], sortField='name', sortAsc=true, delId=null;
let wStep=1, wType=null, wData={}, haRelay=[], haSensors=[], haSocket=[], sFilter='', spField=null;

// Множество entity_id, уже используемых в добавленных устройствах
let usedEntities=new Set();
function refreshUsedEntities(){
  usedEntities=new Set();
  const attrKeys=['entity_id','power_entity','current_entity','voltage_entity',
    'temperature_entity','humidity_entity','battery_entity',
    'water_percentage_entity','replace_filter_entity','alarm_mute_entity'];
  for(const d of devices){
    for(const k of attrKeys){
      const v=d.attributes?.[k];
      if(v) usedEntities.add(v);
    }
  }
}
function isUsed(eid){return usedEntities.has(eid);}
function usedCls(eid){return isUsed(eid)?'used':'';}
function usedBadge(eid){return isUsed(eid)?'<span class="p-used-badge">уже добавлено</span>':'';}


async function loadStatus() {
  try {
    const d = await api('/api/sber_mqtt/status');
    document.getElementById('dot').className='dot '+(d.connected?'ok':'err');
    document.getElementById('connText').textContent=d.connected?`${d.login} · ${d.broker}`:'Нет подключения';
  } catch(e) {
    document.getElementById('connText').textContent='Ошибка';
  }
}

async function loadDevices() {
  try {
    const d = await api('/api/sber_mqtt/devices');
    devices=d.devices||[];
    refreshUsedEntities();
    renderTable();
    document.getElementById('cntLabel').textContent=`Устройств: ${devices.length}`;
  } catch(e) {
    document.getElementById('tbody').innerHTML=
      `<tr><td colspan="6" style="color:var(--danger);text-align:center;padding:20px">Ошибка: ${esc(e.message)}</td></tr>`;
  }
}

function fmtState(s) {
  if (!s || !Object.keys(s).length) return '—';
  // Красиво форматируем states: [{"key":"on_off","value":{"bool_value":true}}]
  // → on_off: true, online: true
  if (Array.isArray(s.states)) {
    return s.states.map(item => {
      const v = item.value || {};
      const val = v.bool_value !== undefined ? v.bool_value
                : v.integer_value !== undefined ? v.integer_value
                : v.enum_value !== undefined ? v.enum_value
                : JSON.stringify(v);
      return `${item.key}: ${val}`;
    }).join(' | ');
  }
  return JSON.stringify(s);
}


// ═══════════════════════════════════════════════════════════
// ТАБЛИЦА УСТРОЙСТВ
// ═══════════════════════════════════════════════════════════
function renderTable() {
  const rows=[...devices].sort((a,b)=>{
    const va=(a[sortField]||'').toString().toLowerCase();
    const vb=(b[sortField]||'').toString().toLowerCase();
    return sortAsc?va.localeCompare(vb,'ru'):vb.localeCompare(va,'ru');
  });
  ['name','id','room','device_type'].forEach(f=>{
    const el=document.getElementById(`si-${f}`);
    if(el){el.textContent=sortField===f?(sortAsc?'▲':'▼'):'';el.closest('th').classList.toggle('sorted',sortField===f);}
  });
  const tb=document.getElementById('tbody');
  if(!rows.length){
    tb.innerHTML=`<tr><td colspan="6"><div class="empty"><div class="ei">🏠</div><h3>Нет устройств</h3><p>Нажмите «Добавить устройство»</p></div></td></tr>`;
    return;
  }
  tb.innerHTML=rows.map(d=>{
    const attrs=Object.entries(d.attributes||{}).map(([k,v])=>`<div><b>${esc(k)}:</b> ${esc(v||'—')}</div>`).join('');
    return `<tr>
      <td><b>${esc(d.name)}</b><br><span class="id-cell">${esc(d.id)}</span></td>
      <td>${esc(d.room||'—')}</td>
      <td><span class="type-badge">${esc(TYPE_LABELS[d.device_type]||d.device_type)}</span></td>
      <td class="attrs">${attrs||'—'}</td>
      <td class="state-col">
        <div class="state-wrap">
          <span class="state-cell" title="${fmtState(d.last_state)}">${esc(fmtState(d.last_state))}</span>
          <button class="btn-sync" id="sync-${esc(d.id)}" onclick="publishOneStatus('${esc(d.id)}')" title="Отправить состояние">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>
          </button>
        </div>
      </td>
      <td class="del-col"><button class="btn btn-ghost btn-sm" onclick="askDel('${esc(d.id)}','${esc(d.name)}')">🗑</button></td>
    </tr>`;
  }).join('');
}

function sortBy(f){if(sortField===f)sortAsc=!sortAsc;else{sortField=f;sortAsc=true;}renderTable();}


// ═══════════════════════════════════════════════════════════
// ЭКСПОРТ / ИМПОРТ
// ═══════════════════════════════════════════════════════════
// ── Экспорт / Импорт ──────────────────────────────────────────────────────
async function doExport(){
  try{
    const data = await api('/api/sber_mqtt/devices');
    const devs = data.devices || [];
    const json = JSON.stringify({sber_mqtt_export:true, version:1, devices:devs}, null, 2);
    const blob = new Blob([json], {type:'application/json'});
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href=url; a.download=`sber_mqtt_${new Date().toISOString().slice(0,10)}.json`;
    a.click(); URL.revokeObjectURL(url);
    toast(`Экспортировано ${devs.length} устройств`);
  }catch(e){toast('Ошибка экспорта: '+e.message,'err');}
}

async function doImport(input){
  const file=input.files[0]; input.value='';
  if(!file) return;
  let parsed;
  try{parsed=JSON.parse(await file.text());}
  catch(e){toast('Не удалось прочитать файл','err');return;}
  if(!parsed.sber_mqtt_export||!Array.isArray(parsed.devices)){toast('Неверный формат файла','err');return;}
  if(!parsed.devices.length){toast('Файл не содержит устройств','err');return;}
  showImportConfirm(parsed.devices);
}

function showImportConfirm(devs){
  const existingIds=new Set(devices.map(d=>d.id));
  const newCnt=devs.filter(d=>!existingIds.has(d.id)).length;
  const updCnt=devs.filter(d=> existingIds.has(d.id)).length;
  const overlay=document.createElement('div');
  overlay.className='overlay';
  overlay.style.zIndex='200';
  const safeDevs=esc(JSON.stringify(devs));
  overlay.innerHTML=`
    <div class="modal" style="max-width:420px">
      <div class="m-head"><span style="font-weight:700">Импорт устройств</span>
        <button class="close" onclick="this.closest('.overlay').remove()">✕</button></div>
      <div class="m-body" style="padding:20px">
        <p style="margin:0 0 12px">В файле <b>${devs.length}</b> устройств:</p>
        <ul style="margin:0 0 14px;padding-left:20px;line-height:1.9">
          ${newCnt?`<li><b>${newCnt}</b> новых — будут добавлены</li>`:''}
          ${updCnt?`<li><b>${updCnt}</b> совпадают по ID — будут перезаписаны</li>`:''}
        </ul>
        <p style="margin:0 0 20px;font-size:12px;color:var(--muted)">Устройства с другими ID не затрагиваются.</p>
        <div style="display:flex;gap:8px;justify-content:flex-end">
          <button class="btn btn-ghost" onclick="this.closest('.overlay').remove()">Отмена</button>
          <button class="btn btn-primary" id="btnConfirmImport">Импортировать</button>
        </div>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#btnConfirmImport').addEventListener('click', async function(){
    this.disabled=true; this.innerHTML='<div class="spin"></div>';
    let ok=0,fail=0;
    for(const dev of devs){
      try{
        await api('/api/sber_mqtt/devices',{method:'POST',body:JSON.stringify({
          id:dev.id, name:dev.name, room:dev.room||'',
          device_type:dev.device_type, attributes:dev.attributes||{}
        })});
        ok++;
      }catch(e){fail++;}
    }
    overlay.remove();
    toast(fail?`Импортировано ${ok}, ошибок ${fail}`:`Импортировано ${ok} устройств`);
    await loadDevices();
    if(ok) doPublishConfig();
  });
}

async function doPublishConfig(){
  try{const r=await api('/api/sber_mqtt/publish_config',{method:'POST'});toast(`Конфигурация (${r.devices_count} устройств) отправлена`,'ok');}
  catch(e){toast('Ошибка: '+e.message,'err');}
}

async function doPublishStatus(){
  try{
    const r=await api('/api/sber_mqtt/publish_status',{method:'POST'});
    if(r.ok){
      // Обновляем last_state в локальном массиве и перерисовываем таблицу
      for(const [device_id, last] of Object.entries(r.states||{})){
        const d=devices.find(x=>x.id===device_id);
        if(d) d.last_state=last;
      }
      renderTable();
      toast(`Состояния (${Object.keys(r.states||{}).length} устройств) отправлены`,'ok');
    }
  } catch(e){toast('Ошибка: '+e.message,'err');}
}

async function publishOneStatus(deviceId){
  const btn=document.getElementById('sync-'+deviceId);
  if(btn) btn.classList.add('spinning');
  try{
    const r=await api('/api/sber_mqtt/publish_status',{method:'POST',body:JSON.stringify({device_id:deviceId})});
    if(r.ok){
      const last=r.states?.[deviceId];
      if(last){
        const d=devices.find(x=>x.id===deviceId);
        if(d){d.last_state=last;renderTable();}
      }
      toast('Состояние отправлено','ok');
    }
  } catch(e){toast('Ошибка: '+e.message,'err');}
  finally{
    // Останавливаем анимацию (кнопка могла перерисоваться через renderTable)
    const b=document.getElementById('sync-'+deviceId);
    if(b) b.classList.remove('spinning');
  }
}

function askDel(id,name){delId=id;document.getElementById('confTxt').textContent=`Устройство «${name}» будет удалено.`;document.getElementById('conf').style.display='flex';}
function closeConf(){delId=null;document.getElementById('conf').style.display='none';}
async function doDelete(){
  if(!delId)return;const id=delId;closeConf();
  try{await api(`/api/sber_mqtt/devices/${id}`,{method:'DELETE'});toast('Удалено','ok');await loadDevices();}
  catch(e){toast('Ошибка: '+e.message,'err');}
}


// ═══════════════════════════════════════════════════════════
// WIZARD — ЯДРО
// ═══════════════════════════════════════════════════════════
function openWizard(){
  // Состояние уже сброшено в closeWizard(), просто показываем и рендерим
  document.getElementById('wiz').style.display='flex';
  renderWiz();
}
function closeWizard(){
  document.getElementById('wiz').style.display='none';
  // Полный сброс состояния чтобы следующее открытие начиналось чисто
  wStep=1;wType=null;wData={};sFilter='';spField=null;haRelay=[];haSensors=[];haClimate=[];haVacuum=[];haValve=[];haLight=[];haCover=[];haWaterLeak=[];haHumidifier=[];haSmoke=[];
  const btn=document.getElementById('btnNext');
  if(btn){btn.disabled=false;btn.textContent='Далее →';}
}

async function wizNext(){
  if(!await wizValidate())return;
  const total=(STEPS[wType]||['','','']).length;
  if(wStep<total){
    wStep++;
    // Загружаем список сущностей при переходе на шаг 2 (если ещё не загружены)
    if(wStep===2){if(wType==='relay')await Promise.all([fetchRelay(),fetchSensors()]);if(wType==='sensor_temp')await fetchSensors();if(wType==='scenario_button')await fetchRelay();if(wType==='hvac_ac')await Promise.all([fetchClimate(),fetchSensors(),fetchSocket()]);if(wType==='vacuum_cleaner')await Promise.all([fetchVacuum(),fetchSensors()]);if(wType==='valve')await fetchValve();if(wType==='light')await fetchLight();if(wType==='cover')await Promise.all([fetchCover(),fetchSensors()]);if(wType==='water_leak')await Promise.all([fetchWaterLeak(),fetchSensors()]);if(wType==='humidifier')await Promise.all([fetchHumidifier(),fetchSensors()]);if(wType==='socket')await Promise.all([fetchSocket(),fetchSensors()]);if(wType==='smoke')await Promise.all([fetchSmoke(),fetchSensors()]);}
    renderWiz();
  }else{
    await submitDevice();
  }
}
function wizBack(){if(wStep>1){wStep--;renderWiz();}}

async function wizValidate(){
  const total=(STEPS[wType]||['','','']).length;
  const isLast=wStep===total;

  if(wStep===1){
    // Шаг 1: выбор типа
    if(!wType){toast('Выберите тип','err');return false;}
  } else if(wStep===2&&!isLast){
    // Шаг 2 — выбор сущности (только если не последний шаг)
    if(wType==='relay'&&!wData.entity_id){toast('Выберите сущность','err');return false;}
    if(wType==='socket'&&!wData.entity_id){toast('Выберите сущность','err');return false;}
    if(wType==='scenario_button'&&!wData.entity_id){toast('Выберите сущность','err');return false;}
    if(wType==='hvac_ac'&&!wData.entity_id){toast('Выберите климатическую сущность','err');return false;}
    if(wType==='vacuum_cleaner'&&!wData.entity_id){toast('Выберите пылесос','err');return false;}
    if(wType==='valve'&&!wData.entity_id){toast('Выберите сущность крана','err');return false;}
    if(wType==='light'&&!wData.entity_id){toast('Выберите лампу','err');return false;}
    if(wType==='cover'&&!wData.entity_id){toast('Выберите шторы/жалюзи','err');return false;}
    if(wType==='water_leak'&&!wData.entity_id){toast('Выберите датчик протечки','err');return false;}
    if(wType==='smoke'&&!wData.entity_id){toast('Выберите датчик дыма','err');return false;}
    if(wType==='humidifier'&&!wData.entity_id){toast('Выберите увлажнитель','err');return false;}
    if(wType==='sensor_temp'&&!wData.temperature_entity&&!wData.humidity_entity){toast('Выберите температуру или влажность','err');return false;}
  }

  if(isLast){
    // Последний шаг — параметры устройства
    const name=document.getElementById('dName')?.value?.trim();
    const id=document.getElementById('dId')?.value?.trim();
    if(!name){toast('Введите имя','err');return false;}
    // Валидация имени по требованиям Салюта: только русские буквы, цифры и пробелы, 3–33 символа
    if(!/^[а-яёА-ЯЁ0-9 ]{3,33}$/.test(name)){
      toast('Имя: только русские буквы, цифры и пробелы, от 3 до 33 символов','err');
      return false;
    }
    if(!id){toast('Введите ID','err');return false;}
    if(!/^[a-z0-9_]+$/.test(id)){toast('ID: только a-z, 0-9 и _','err');return false;}
    if(devices.find(d=>d.id===id)){toast(`ID «${id}» уже занят`,'err');return false;}
    wData.name=name;wData.id=id;wData.room=document.getElementById('dRoom')?.value?.trim()||'';
  }
  return true;
}

function renderWiz(){
  const steps=STEPS[wType]||['Тип','Выбор','Параметры'];
  document.getElementById('wizTitle').textContent=steps[wStep-1];
  document.getElementById('btnBack').style.display=wStep>1?'':'none';
  document.getElementById('btnNext').textContent=wStep===steps.length?'Готово ✓':'Далее →';
  document.getElementById('wizSteps').innerHTML=steps.map((lbl,i)=>{
    const n=i+1,cls=n<wStep?'done':n===wStep?'active':'';
    return `<div class="step ${cls}"><div class="step-c">${n<wStep?'✓':n}</div><div class="step-lbl">${lbl}</div></div>`;
  }).join('');
  const c=document.getElementById('wizContent');
  if(wStep===1)c.innerHTML=renderStep1();
  else if(wStep===2){if(wType==='relay')c.innerHTML=renderStep2Relay();else if(wType==='scenario_button')c.innerHTML=renderStep2ScenarioButton();else if(wType==='hvac_ac')c.innerHTML=renderStep2HvacAc();else if(wType==='vacuum_cleaner')c.innerHTML=renderStep2Vacuum();else if(wType==='valve')c.innerHTML=renderStep2Valve();else if(wType==='light')c.innerHTML=renderStep2Light();else if(wType==='cover')c.innerHTML=renderStep2Cover();else if(wType==='water_leak')c.innerHTML=renderStep2WaterLeak();else if(wType==='humidifier')c.innerHTML=renderStep2Humidifier();else if(wType==='socket')c.innerHTML=renderStep2Socket();else if(wType==='smoke')c.innerHTML=renderStep2Smoke();else c.innerHTML=renderStep2Sensor();}
  else c.innerHTML=renderStep3();
}

function renderStep1(){
  const groups=[
    {label:'Управление', items:[
      {id:'relay',          icon:'🔌', name:'Реле',                    desc:'switch, light, input_boolean, media_player, script, button — включение и выключение'},
      {id:'socket',         icon:'🔋', name:'Розетка',                 desc:'switch, input_boolean — включение/выключение + энергомониторинг (мощность, ток, напряжение)'},
      {id:'light',          icon:'💡', name:'Лампа',                   desc:'light — яркость, цвет, цветовая температура'},
      {id:'hvac_ac',        icon:'❄️', name:'Кондиционер',             desc:'climate — температура и режимы работы'},
      {id:'humidifier',     icon:'💧', name:'Увлажнитель воздуха',     desc:'humidifier — влажность, режим, скорость вентилятора'},
      {id:'vacuum_cleaner', icon:'🤖', name:'Пылесос',                 desc:'vacuum — управление уборкой'},
      {id:'valve',          icon:'🚰', name:'Кран',                    desc:'valve, switch — открытие и закрытие'},
      {id:'cover',          icon:'🪟', name:'Рулонные шторы / жалюзи', desc:'cover — открытие, закрытие, позиционирование'},
    ]},
    {label:'Датчики', items:[
      {id:'sensor_temp',    icon:'🌡️', name:'Датчик температуры/влажности', desc:'sensor — температура и влажность'},
      {id:'water_leak',     icon:'🌊', name:'Датчик протечки',              desc:'binary_sensor (moisture) — обнаружение воды'},
      {id:'smoke',          icon:'🔥', name:'Датчик дыма',                  desc:'binary_sensor (smoke) — обнаружение дыма'},
    ]},
    {label:'Автоматизации', items:[
      {id:'scenario_button',icon:'🔔', name:'Сценарная кнопка', desc:'Прокидывает события из HA в Салют: вкл → click, выкл → double_click'},
    ]},
  ];
  return groups.map(g=>`
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin:14px 0 6px;padding-left:2px">${g.label}</div>
    ${g.items.map(t=>`<div class="type-card ${wType===t.id?'sel':''}" onclick="pickType('${t.id}')">
      <div class="type-icon">${t.icon}</div>
      <div><div class="type-name">${t.name}</div><div class="type-desc">${t.desc}</div></div></div>`).join('')}
  `).join('');
}
function pickType(t){wType=t;renderWiz();}


// ═══════════════════════════════════════════════════════════
// WIZARD: РЕЛЕ
// ═══════════════════════════════════════════════════════════
function renderStep2Relay(){
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите сущность HA:</label></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('plist').innerHTML=relayItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('plist').innerHTML=relayItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" style="max-height:200px" id="plist">${relayItems()}</div>
    </div>
    ${wData.entity_id?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(wData.entity_id)}</b></div>`:''}`;
}
let _relaySensorPickerKey='', _relaySensorPickerDc='';
function openRelaySensorPicker(key, dc){
  _relaySensorPickerKey=key; _relaySensorPickerDc=dc;
  const wrap=document.getElementById('relaySensorPickerWrap');
  wrap.style.display='';
  document.getElementById('relaySensorInput').value='';
  renderRelaySensorList('');
  wrap.scrollIntoView({behavior:'smooth'});
}
function renderRelaySensorList(q){
  q=(q||'').toLowerCase();
  let list=haSensors.filter(s=>s.device_class===_relaySensorPickerDc);
  if(q)list=list.filter(s=>(s.area+s.entity_id+s.friendly_name).toLowerCase().includes(q));
  const el=document.getElementById('relaySensorList');if(!el)return;
  el.innerHTML=list.length?list.map(s=>`<div class="p-item ${wData[_relaySensorPickerKey]===s.entity_id?'sel':''} ${usedCls(s.entity_id)}" onclick="pickRelaySensor('${esc(s.entity_id)}','${esc(s.friendly_name)}')">
    <span class="dom-badge">${esc(s.device_class)}</span><span class="p-area">${esc(s.area||'—')}</span>
    <span class="p-name">${esc(s.friendly_name)}</span><span class="p-eid">${esc(s.entity_id)}</span></div>`).join(''):`<div class="p-empty">Нет сенсоров класса «${_relaySensorPickerDc}»</div>`;
}
function pickRelaySensor(eid,name){
  wData[_relaySensorPickerKey]=eid;
  document.getElementById('wizContent').innerHTML=renderStep2Relay();
}
function clearRelaySensor(key){delete wData[key];document.getElementById('wizContent').innerHTML=renderStep2Relay();}

function relayItems(){
  const list=haRelay.filter(e=>!sFilter||(e.area+e.domain+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Ничего не найдено</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area)}','${esc(e.device_id||'')}')">
    <span class="dom-badge">${esc(e.domain)}</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickEntity(eid,name,area,deviceId){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  document.getElementById('wizContent').innerHTML=renderStep2Relay();
}

function pickEntity(eid,name,area,deviceId){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  document.getElementById('wizContent').innerHTML=renderStep2Relay();
}


// ═══════════════════════════════════════════════════════════
// WIZARD: РОЗЕТКА
// ═══════════════════════════════════════════════════════════
// ── Socket (розетка с энергомониторингом) ────────────────────────────────────
async function fetchSocket(){
  try{const d=await api('/api/sber_mqtt/ha_entities/socket');haSocket=d.entities||[];}
  catch(e){haSocket=[];}
}
function socketItems(){
  const list=haSocket.filter(e=>!sFilter||(e.area+e.domain+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Ничего не найдено</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickSocketEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area)}','${esc(e.device_id||'')}')">
    <span class="dom-badge">${esc(e.domain)}</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickSocketEntity(eid,name,area,deviceId){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  // Автоподбор энергосенсоров по device_id
  if(deviceId){
    const byDc={power:'power_entity',current:'current_entity',voltage:'voltage_entity'};
    for(const [dc,key] of Object.entries(byDc)){
      const found=haSensors.find(s=>s.device_class===dc&&s.device_id===deviceId);
      if(found)wData[key]=found.entity_id; else delete wData[key];
    }
  }
  document.getElementById('wizContent').innerHTML=renderStep2Socket();
}
let _socketSensorPickerKey='', _socketSensorPickerDc='';
function openSocketSensorPicker(key,dc){
  _socketSensorPickerKey=key; _socketSensorPickerDc=dc;
  const wrap=document.getElementById('socketSensorPickerWrap');
  wrap.style.display='';
  document.getElementById('socketSensorInput').value='';
  renderSocketSensorList('');
  wrap.scrollIntoView({behavior:'smooth'});
}
function renderSocketSensorList(q){
  q=(q||'').toLowerCase();
  let list=haSensors.filter(s=>s.device_class===_socketSensorPickerDc);
  if(q)list=list.filter(s=>(s.area+s.entity_id+s.friendly_name).toLowerCase().includes(q));
  const el=document.getElementById('socketSensorList');if(!el)return;
  el.innerHTML=list.length?list.map(s=>`<div class="p-item ${wData[_socketSensorPickerKey]===s.entity_id?'sel':''} ${usedCls(s.entity_id)}" onclick="pickSocketSensor('${esc(s.entity_id)}')">
    <span class="dom-badge">${esc(s.device_class)}</span><span class="p-area">${esc(s.area||'—')}</span>
    <span class="p-name">${esc(s.friendly_name)}</span><span class="p-eid">${esc(s.entity_id)}</span></div>`).join(''):`<div class="p-empty">Нет сенсоров класса «${_socketSensorPickerDc}»</div>`;
}
function pickSocketSensor(eid){
  wData[_socketSensorPickerKey]=eid;
  document.getElementById('wizContent').innerHTML=renderStep2Socket();
}
function clearSocketSensor(key){delete wData[key];document.getElementById('wizContent').innerHTML=renderStep2Socket();}

function renderStep2Socket(){
  const energySlots=[
    {key:'power_entity',   label:'⚡ Мощность',  dc:'power'},
    {key:'current_entity', label:'🔌 Ток',        dc:'current'},
    {key:'voltage_entity', label:'🔋 Напряжение', dc:'voltage'},
  ];
  const energyHtml=energySlots.map(slot=>{
    const eid=wData[slot.key]||'';
    const s=eid?haSensors.find(x=>x.entity_id===eid):null;
    return `<div class="sf">
      <label>${slot.label} <span style="color:var(--danger);font-weight:400">*</span></label>
      <button class="sf-btn ${eid?'filled':''}" onclick="openSocketSensorPicker('${slot.key}','${slot.dc}')">
        <span>${eid?(s?.friendly_name||eid):'Выбрать сенсор…'}</span><span>${eid?'✓':'▾'}</span>
      </button>
      ${eid?`<div class="sf-sub">${esc(eid)} <button class="sf-clr" onclick="clearSocketSensor('${slot.key}')">✕</button></div>`:''}
    </div>`;
  }).join('');

  return `<div class="fg" style="margin-bottom:10px"><label>Выберите сущность HA:</label>
    <div style="font-size:11px;color:var(--muted);margin-top:3px">switch или input_boolean</div></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('sklist').innerHTML=socketItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('sklist').innerHTML=socketItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" style="max-height:150px" id="sklist">${socketItems()}</div>
    </div>
    ${wData.entity_id?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(wData.entity_id)}</b></div>`:''}
    <div style="margin-top:14px;padding:12px 14px;border:1px solid var(--border);border-radius:8px;background:#fafafa">
      <div style="font-size:12px;font-weight:600;margin-bottom:6px;color:var(--fg)">⚡ Энергомониторинг</div>
      <div style="font-size:11px;color:var(--muted);margin-bottom:10px">Сенсоры автоматически подбираются при выборе устройства. Обязательны для типа «Розетка».</div>
      ${energyHtml}
    </div>
    <div id="socketSensorPickerWrap" style="display:none;margin-top:10px">
      <div class="picker">
        <div class="psearch"><span style="color:var(--muted)">🔍</span>
          <input id="socketSensorInput" type="text" placeholder="Поиск…" oninput="renderSocketSensorList(this.value)"/>
          <button class="clr" onclick="socketSensorInput.value='';renderSocketSensorList('')">✕</button>
        </div>
        <div class="p-head"><div>Класс</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
        <div class="p-list" style="max-height:150px" id="socketSensorList"></div>
      </div>
    </div>`;
}

function renderStep2ScenarioButton(){
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите сущность HA:</label>
    <div style="font-size:11px;color:var(--muted);margin-top:3px">Включение → <b>click</b> · Выключение → <b>double_click</b> · Кнопка/сценарий → <b>click</b></div></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('sblist').innerHTML=scenarioBtnItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('sblist').innerHTML=scenarioBtnItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" id="sblist">${scenarioBtnItems()}</div>
    </div>
    ${wData.entity_id?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(wData.entity_id)}</b></div>`:''}`;
}
function scenarioBtnItems(){
  const list=haRelay.filter(e=>!sFilter||(e.area+e.domain+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Ничего не найдено</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickScenarioBtnEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area)}')">
    <span class="dom-badge">${esc(e.domain)}</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickScenarioBtnEntity(eid,name,area){wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;document.getElementById('wizContent').innerHTML=renderStep2ScenarioButton();}


// ═══════════════════════════════════════════════════════════
// WIZARD: ДАТЧИК ТЕМПЕРАТУРЫ/ВЛАЖНОСТИ
// ═══════════════════════════════════════════════════════════
const SENSOR_SLOTS=[
  {key:'temperature_entity',label:'🌡 Температура',cls:'temperature',req:true},
  {key:'humidity_entity',label:'💧 Влажность',cls:'humidity',req:true},
  {key:'battery_entity',label:'🔋 Заряд батареи',cls:'battery',req:false},
];
function renderStep2Sensor(){
  const slots=SENSOR_SLOTS.map(s=>{
    const val=wData[s.key];const entity=val?haSensors.find(x=>x.entity_id===val):null;
    return `<div class="sf"><label>${s.label}${s.req?' <span style="color:var(--danger)">*</span>':''}</label>
      <button class="sf-btn ${val?'filled':''}" onclick="openSP('${s.key}')">
        <span>${val?(entity?.friendly_name||val):'Выбрать сенсор…'}</span><span>${val?'✓':'▾'}</span></button>
      ${val?`<div class="sf-sub">${esc(val)} <button class="sf-clr" onclick="clearSP('${s.key}')">✕</button></div>`:''}</div>`;
  }).join('');
  return `<div style="margin-bottom:12px;font-size:12px;color:var(--muted)">Температура или влажность обязательны.</div>
    <div class="sg">${slots}</div>
    <div id="spWrap" class="sp-wrap" style="display:none">
      <div class="picker">
        <div class="psearch"><span style="color:var(--muted)">🔍</span>
          <input id="spInput" type="text" placeholder="Поиск…" oninput="renderSPList(this.value)"/>
          <button class="clr" onclick="spInput.value='';renderSPList('')">✕</button>
        </div>
        <div class="p-head"><div>Класс</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
        <div class="p-list" id="spList"></div>
      </div>
    </div>`;
}
function openSP(key){spField=key;document.getElementById('spWrap').style.display='';document.getElementById('spInput').value='';renderSPList('');document.getElementById('spWrap').scrollIntoView({behavior:'smooth'});}
function renderSPList(q){
  q=(q||'').toLowerCase();
  const clsMap={temperature_entity:'temperature',battery_entity:'battery'};
  let list=spField==='humidity_entity'
    ? haSensors.filter(s=>s.device_class==='humidity'||s.device_class==='moisture')
    : (clsMap[spField]?haSensors.filter(s=>s.device_class===clsMap[spField]):haSensors);
  if(q)list=list.filter(s=>(s.area+s.device_class+s.entity_id+s.friendly_name).toLowerCase().includes(q));
  const el=document.getElementById('spList');if(!el)return;
  el.innerHTML=list.length?list.map(s=>`<div class="p-item ${wData[spField]===s.entity_id?'sel':''} ${usedCls(s.entity_id)}" onclick="pickSensor('${esc(s.entity_id)}','${esc(s.friendly_name)}','${esc(s.area)}')">
    <span class="dom-badge">${esc(s.device_class)}</span><span class="p-area">${esc(s.area||'—')}</span>
    <span class="p-name">${esc(s.friendly_name)}</span><span class="p-eid">${esc(s.entity_id)}</span></div>`).join(''):`<div class="p-empty">Не найдено</div>`;
}
function pickSensor(eid,name,area){
  if(!spField)return;
  wData[spField]=eid;wData[spField+'_name']=name;wData[spField+'_area']=area;

  // Автоподбор батареи по device_id при выборе температуры или влажности
  if(spField==='temperature_entity'||spField==='humidity_entity'){
    const picked=haSensors.find(s=>s.entity_id===eid);
    if(picked&&picked.device_id&&!wData.battery_entity){
      const bat=haSensors.find(s=>s.device_class==='battery'&&s.device_id===picked.device_id);
      if(bat){wData.battery_entity=bat.entity_id;wData.battery_entity_name=bat.friendly_name;wData.battery_entity_area=bat.area||'';}
    }
  }

  spField=null;document.getElementById('wizContent').innerHTML=renderStep2Sensor();
}
function clearSP(key){delete wData[key];delete wData[key+'_name'];delete wData[key+'_area'];document.getElementById('wizContent').innerHTML=renderStep2Sensor();}


// ═══════════════════════════════════════════════════════════
// WIZARD: ШАГ 3 — ПАРАМЕТРЫ
// ═══════════════════════════════════════════════════════════
function renderStep3(){
  let defName='',defRoom='';
  if(wType==='relay'||wType==='socket'||wType==='scenario_button'||wType==='hvac_ac'||wType==='vacuum_cleaner'||wType==='valve'||wType==='light'||wType==='cover'||wType==='water_leak'||wType==='humidifier'||wType==='smoke'){defName=wData.entity_name||'';defRoom=wData.entity_area||'';}
  else{defName=wData.temperature_entity_name||wData.humidity_entity_name||'';defRoom=wData.temperature_entity_area||wData.humidity_entity_area||'';}
  return `<div class="fg"><label>Имя <span style="color:var(--danger)">*</span></label>
    <input type="text" id="dName" value="${esc(wData.name||defName)}" oninput="autoId()" placeholder="Свет в гостиной"/>
    <div style="font-size:11px;color:var(--text-muted,#888);margin-top:4px">Только русские буквы, цифры и пробелы · от 3 до 33 символов</div></div>
    <div class="fg"><label>ID <span style="color:var(--danger)">*</span></label>
    <input type="text" id="dId" value="${esc(wData.id||slugify(wData.name||defName))}" placeholder="relay_living_room"/>
    <div class="hint">Только a–z, 0–9, _ . Уникальный идентификатор в Сбере.</div></div>
    <div class="fg"><label>Комната</label>
    <input type="text" id="dRoom" value="${esc(wData.room!==undefined?wData.room:defRoom)}" placeholder="Гостиная"/></div>`;
}
function autoId(){const n=document.getElementById('dName')?.value||'';const f=document.getElementById('dId');if(f&&(!wData.id||f.value===slugify(wData.name||'')))f.value=slugify(n);}

async function submitDevice(){
  const attrs={};
  if(wType==='relay'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    if(wData.power_entity)  attrs.power_entity=wData.power_entity;
    if(wData.current_entity)attrs.current_entity=wData.current_entity;
    if(wData.voltage_entity)attrs.voltage_entity=wData.voltage_entity;
  }
  else if(wType==='scenario_button'){attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';}
  else if(wType==='hvac_ac'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    if(wData.temperature_entity)attrs.temperature_entity=wData.temperature_entity;
  }
  else if(wType==='vacuum_cleaner'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    if(wData.battery_entity)attrs.battery_entity=wData.battery_entity;
  }
  else if(wType==='valve'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
  }
  else if(wType==='cover'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    if(wData.battery_entity)attrs.battery_entity=wData.battery_entity;
  }
  else if(wType==='water_leak'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    if(wData.battery_entity)attrs.battery_entity=wData.battery_entity;
  }
  else if(wType==='smoke'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    if(wData.battery_entity)    attrs.battery_entity=wData.battery_entity;
    if(wData.alarm_mute_entity) attrs.alarm_mute_entity=wData.alarm_mute_entity;
  }
  else if(wType==='humidifier'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    if(wData.water_percentage_entity)attrs.water_percentage_entity=wData.water_percentage_entity;
    if(wData.replace_filter_entity)  attrs.replace_filter_entity=wData.replace_filter_entity;
  }
  else if(wType==='socket'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    if(wData.power_entity)  attrs.power_entity=wData.power_entity;
    if(wData.current_entity)attrs.current_entity=wData.current_entity;
    if(wData.voltage_entity)attrs.voltage_entity=wData.voltage_entity;
  }
  else if(wType==='light'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    // Сохраняем выбранные фичи как булевые флаги
    for(const f of ['light_brightness','light_colour','light_colour_temp','light_mode']){
      attrs[f]=!!(wData.light_features&&wData.light_features.includes(f));
    }
  }
  else{['temperature_entity','humidity_entity','battery_entity'].forEach(k=>{if(wData[k])attrs[k]=wData[k];});}
  const body={id:wData.id,name:wData.name,room:wData.room||'',device_type:wType,attributes:attrs};
  const btn=document.getElementById('btnNext');btn.disabled=true;btn.innerHTML='<div class="spin"></div>';
  try{
    const res = await api('/api/sber_mqtt/devices',{method:'POST',body:JSON.stringify(body)});
    closeWizard();
    toast('Устройство добавлено','ok');
    await loadDevices();
    // Применяем last_state из ответа — он уже содержит начальное состояние
    if(res.device?.last_state && Object.keys(res.device.last_state).length){
      const d=devices.find(x=>x.id===res.device.id);
      if(d){d.last_state=res.device.last_state;renderTable();}
    }
  }
  catch(e){
    btn.disabled=false;btn.textContent='Готово ✓';
    if(e.message&&e.message.includes('already exists')){
      toast(`ID «${wData.id}» уже занят — измените ID устройства`,'err');
      // Возвращаемся на шаг 3 чтобы пользователь мог сменить ID
      wStep=STEPS[wType].length;
      renderWiz();
      setTimeout(()=>{const f=document.getElementById('dId');if(f){f.focus();f.select();}},100);
    } else {
      toast('Ошибка: '+e.message,'err');
    }
  }
}

async function fetchRelay(){if(haRelay.length)return;try{haRelay=(await api('/api/sber_mqtt/ha_entities/relay')).entities||[];}catch(e){toast('Ошибка загрузки сущностей','err');}}
async function fetchSensors(){if(haSensors.length)return;try{haSensors=(await api('/api/sber_mqtt/ha_entities/sensors?classes=temperature,humidity,moisture,battery,signal_strength,power,current,voltage')).entities||[];}catch(e){toast('Ошибка загрузки сенсоров','err');}}

let haClimate=[];

// ═══════════════════════════════════════════════════════════
// WIZARD: КОНДИЦИОНЕР
// ═══════════════════════════════════════════════════════════
async function fetchClimate(){if(haClimate.length)return;try{haClimate=(await api('/api/sber_mqtt/ha_entities/climate')).entities||[];}catch(e){toast('Ошибка загрузки климата','err');}}

function renderStep2HvacAc(){
  const sel=wData.entity_id;
  const tempSel=wData.temperature_entity;
  const tempEntity=tempSel?haSensors.find(x=>x.entity_id===tempSel):null;
  const climateList=haClimate.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите климатическую сущность (climate):</label></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('hvaclist').innerHTML=hvacItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('hvaclist').innerHTML=hvacItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" id="hvaclist">${hvacItems()}</div>
    </div>
    ${sel?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(sel)}</b></div>`:''}
    <div style="margin-top:18px">
      <div class="sf"><label>🌡 Датчик текущей температуры <span style="color:var(--muted);font-weight:400">(опционально)</span></label>
        <button class="sf-btn ${tempSel?'filled':''}" onclick="openHvacTempPicker()">
          <span>${tempSel?(tempEntity?.friendly_name||tempSel):'Выбрать сенсор…'}</span><span>${tempSel?'✓':'▾'}</span>
        </button>
        ${tempSel?`<div class="sf-sub">${esc(tempSel)} <button class="sf-clr" onclick="clearHvacTemp()">✕</button></div>`:''}
        <div class="hint">Если не указан — используется встроенный датчик кондиционера (current_temperature из атрибутов).</div>
      </div>
    </div>
    <div id="hvacTempPicker" style="display:none;margin-top:10px">
      <div class="picker">
        <div class="psearch"><span style="color:var(--muted)">🔍</span>
          <input id="hvacTempInput" type="text" placeholder="Поиск…" oninput="renderHvacTempList(this.value)"/>
          <button class="clr" onclick="hvacTempInput.value='';renderHvacTempList('')">✕</button>
        </div>
        <div class="p-head"><div>Класс</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
        <div class="p-list" id="hvacTempList"></div>
      </div>
    </div>`;
}
function hvacItems(){
  const list=haClimate.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Ничего не найдено</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickHvacEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area)}')">
    <span class="dom-badge">climate</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickHvacEntity(eid,name,area){wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;document.getElementById('wizContent').innerHTML=renderStep2HvacAc();}
function openHvacTempPicker(){const el=document.getElementById('hvacTempPicker');el.style.display='';document.getElementById('hvacTempInput').value='';renderHvacTempList('');el.scrollIntoView({behavior:'smooth'});}
function renderHvacTempList(q){
  q=(q||'').toLowerCase();
  let list=haSensors.filter(s=>s.device_class==='temperature');
  if(q)list=list.filter(s=>(s.area+s.entity_id+s.friendly_name).toLowerCase().includes(q));
  const el=document.getElementById('hvacTempList');if(!el)return;
  el.innerHTML=list.length?list.map(s=>`<div class="p-item ${wData.temperature_entity===s.entity_id?'sel':''} ${usedCls(s.entity_id)}" onclick="pickHvacTemp('${esc(s.entity_id)}','${esc(s.friendly_name)}')">
    <span class="dom-badge">${esc(s.device_class)}</span><span class="p-area">${esc(s.area||'—')}</span>
    <span class="p-name">${esc(s.friendly_name)}</span><span class="p-eid">${esc(s.entity_id)}</span></div>`).join(''):`<div class="p-empty">Нет датчиков температуры</div>`;
}
function pickHvacTemp(eid,name){wData.temperature_entity=eid;wData.temperature_entity_name=name;document.getElementById('wizContent').innerHTML=renderStep2HvacAc();}
function clearHvacTemp(){delete wData.temperature_entity;delete wData.temperature_entity_name;document.getElementById('wizContent').innerHTML=renderStep2HvacAc();}


// ═══════════════════════════════════════════════════════════
// WIZARD: ПЫЛЕСОС
// ═══════════════════════════════════════════════════════════
// ── Пылесос ──────────────────────────────────────────────────────────────
let haVacuum=[];
async function fetchVacuum(){
  if(haVacuum.length)return;
  try{haVacuum=(await api('/api/sber_mqtt/ha_entities/vacuum')).entities||[];}
  catch(e){toast('Ошибка загрузки пылесосов','err');}
}

function renderStep2Vacuum(){
  const sel=wData.entity_id;
  const batSel=wData.battery_entity;
  // Ищем отображаемое имя выбранного батарейного сенсора
  const batEntity=batSel?haSensors.find(x=>x.entity_id===batSel):null;
  const vacList=haVacuum.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите пылесос (vacuum):</label></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('vaclist').innerHTML=vacItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('vaclist').innerHTML=vacItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" id="vaclist">${vacItems()}</div>
    </div>
    ${sel?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(sel)}</b></div>`:''}
    <div style="margin-top:18px">
      <div class="sf"><label>🔋 Датчик заряда батареи <span style="color:var(--muted);font-weight:400">(опционально)</span></label>
        <button class="sf-btn ${batSel?'filled':''}" onclick="openVacBatteryPicker()">
          <span>${batSel?(batEntity?.friendly_name||batSel):'Выбрать сенсор…'}</span><span>${batSel?'✓':'▾'}</span>
        </button>
        ${batSel?`<div class="sf-sub">${esc(batSel)} <button class="sf-clr" onclick="clearVacBattery()">✕</button></div>`:''}
        <div class="hint">Автоматически подтянется датчик батареи того же устройства. Если не задан — используется атрибут battery_level пылесоса.</div>
      </div>
    </div>
    <div id="vacBatteryPicker" style="display:none;margin-top:10px">
      <div class="picker">
        <div class="psearch"><span style="color:var(--muted)">🔍</span>
          <input id="vacBatInput" type="text" placeholder="Поиск…" oninput="renderVacBatList(this.value)"/>
          <button class="clr" onclick="vacBatInput.value='';renderVacBatList('')">✕</button>
        </div>
        <div class="p-head"><div>Класс</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
        <div class="p-list" id="vacBatList"></div>
      </div>
    </div>`;
}

function vacItems(){
  const list=haVacuum.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Нет пылесосов</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickVacEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area)}','${esc(e.device_id||'')}')">
    <span class="dom-badge">vacuum</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}

function pickVacEntity(eid, name, area, deviceId){
  wData.entity_id=eid; wData.entity_name=name; wData.entity_area=area;
  // Автоматически ищем датчик батареи того же устройства HA
  if(deviceId){
    const batSensor=haSensors.find(s=>s.device_class==='battery' && s.device_id===deviceId);
    if(batSensor){
      wData.battery_entity=batSensor.entity_id;
      wData.battery_entity_name=batSensor.friendly_name;
    }
  }
  document.getElementById('wizContent').innerHTML=renderStep2Vacuum();
}

function openVacBatteryPicker(){
  const el=document.getElementById('vacBatteryPicker');
  el.style.display='';
  document.getElementById('vacBatInput').value='';
  renderVacBatList('');
  el.scrollIntoView({behavior:'smooth'});
}
function renderVacBatList(q){
  q=(q||'').toLowerCase();
  let list=haSensors.filter(s=>s.device_class==='battery');
  if(q)list=list.filter(s=>(s.area+s.entity_id+s.friendly_name).toLowerCase().includes(q));
  const el=document.getElementById('vacBatList'); if(!el)return;
  el.innerHTML=list.length?list.map(s=>`<div class="p-item ${wData.battery_entity===s.entity_id?'sel':''} ${usedCls(s.entity_id)}" onclick="pickVacBattery('${esc(s.entity_id)}','${esc(s.friendly_name)}')">
    <span class="dom-badge">${esc(s.device_class)}</span><span class="p-area">${esc(s.area||'—')}</span>
    <span class="p-name">${esc(s.friendly_name)}</span><span class="p-eid">${esc(s.entity_id)}</span></div>`).join(''):`<div class="p-empty">Нет датчиков батареи</div>`;
}
function pickVacBattery(eid,name){wData.battery_entity=eid;wData.battery_entity_name=name;document.getElementById('wizContent').innerHTML=renderStep2Vacuum();}
function clearVacBattery(){delete wData.battery_entity;delete wData.battery_entity_name;document.getElementById('wizContent').innerHTML=renderStep2Vacuum();}


// ═══════════════════════════════════════════════════════════
// WIZARD: КРАН
// ═══════════════════════════════════════════════════════════
// ── Кран ──────────────────────────────────────────────────────────────────
let haValve=[];
async function fetchValve(){
  if(haValve.length)return;
  try{haValve=(await api('/api/sber_mqtt/ha_entities/valve')).entities||[];}
  catch(e){toast('Ошибка загрузки кранов','err');}
}

function renderStep2Valve(){
  const sel=wData.entity_id;
  const list=haValve.filter(e=>!sFilter||(e.area+e.domain+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите сущность крана (valve или switch):</label>
    <div style="font-size:11px;color:var(--muted);margin-top:3px">valve: поддерживает open/close/stop · switch: поддерживает open/close</div></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('valvelist').innerHTML=valveItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('valvelist').innerHTML=valveItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" id="valvelist">${valveItems()}</div>
    </div>
    ${sel?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(sel)}</b></div>`:''}`;
}
function valveItems(){
  const list=haValve.filter(e=>!sFilter||(e.area+e.domain+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Нет подходящих сущностей</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickValveEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area)}')">
    <span class="dom-badge">${esc(e.domain)}</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickValveEntity(eid,name,area){wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;document.getElementById('wizContent').innerHTML=renderStep2Valve();}


// ═══════════════════════════════════════════════════════════
// WIZARD: ЛАМПА
// ═══════════════════════════════════════════════════════════
// ── Лампа ──────────────────────────────────────────────────────────────────
let haLight=[];
async function fetchLight(){
  if(haLight.length)return;
  try{haLight=(await api('/api/sber_mqtt/ha_entities/light')).entities||[];}
  catch(e){toast('Ошибка загрузки ламп','err');}
}

// Человекочитаемые названия фич
const LIGHT_FEATURE_LABELS = {
  light_brightness:   '🔆 Яркость',
  light_colour:       '🎨 Цвет',
  light_colour_temp:  '🌡 Цветовая температура',
  light_mode:         '🔀 Режим (белый / цветной)',
};

function renderStep2Light(){
  const sel = wData.entity_id;
  const selEntity = haLight.find(e=>e.entity_id===sel);
  // Автозаполняем фичи при первом выборе лампы
  if(!wData.light_features && selEntity){
    wData.light_features = [...(selEntity.supported_features||[])];
  }
  const list = haLight.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите лампу (light):</label></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('lightlist').innerHTML=lightItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('lightlist').innerHTML=lightItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" id="lightlist">${lightItems()}</div>
    </div>
    ${sel?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(sel)}</b></div>`:''}
    ${sel?renderLightFeatures(selEntity):''}`;
}

function lightItems(){
  const list=haLight.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Нет ламп</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickLightEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area)}')">
    <span class="dom-badge">light</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}

function renderLightFeatures(entity){
  const allFeats = ['light_brightness','light_colour','light_colour_temp','light_mode'];
  const supported = entity?new Set(entity.supported_features||[]):new Set();
  const selected  = new Set(wData.light_features||[]);
  return `<div style="margin-top:18px">
    <div class="fg"><label>Функции в Салюте:</label>
      <div style="font-size:11px;color:var(--muted);margin-top:3px">Отмечены функции, поддерживаемые лампой. Снимите галочку, чтобы отключить.</div>
    </div>
    <div style="display:flex;flex-direction:column;gap:8px;margin-top:10px">
      ${allFeats.map(f=>{
        const isSupported = supported.has(f);
        const isChecked   = selected.has(f);
        return `<label style="display:flex;align-items:center;gap:10px;cursor:pointer;padding:8px 12px;border:1px solid var(--border);border-radius:8px;background:${isChecked?'var(--primary-lt)':'#fff'};opacity:${isSupported?1:0.5}">
          <input type="checkbox" ${isChecked?'checked':''} ${!isSupported?'disabled':''} onchange="toggleLightFeature('${f}',this.checked)" style="width:16px;height:16px;accent-color:var(--primary)">
          <span style="font-size:13px">${LIGHT_FEATURE_LABELS[f]||f}</span>
          ${!isSupported?'<span style="font-size:10px;color:var(--muted);margin-left:auto">не поддерживается лампой</span>':''}
        </label>`;
      }).join('')}
    </div>
  </div>`;
}

function pickLightEntity(eid,name,area){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  // Автоматически выбираем поддерживаемые фичи
  const entity=haLight.find(e=>e.entity_id===eid);
  wData.light_features=entity?[...(entity.supported_features||[])]:[];
  document.getElementById('wizContent').innerHTML=renderStep2Light();
}
function toggleLightFeature(feat,checked){
  if(!wData.light_features)wData.light_features=[];
  if(checked){if(!wData.light_features.includes(feat))wData.light_features.push(feat);}
  else{wData.light_features=wData.light_features.filter(f=>f!==feat);}
  // Перерисовываем только блок фич без пересоздания всего шага
  const entity=haLight.find(e=>e.entity_id===wData.entity_id);
  const block=document.querySelector('#wizContent > div:last-child');
  if(block&&wData.entity_id){block.outerHTML=renderLightFeatures(entity);}
}


// ═══════════════════════════════════════════════════════════
// WIZARD: ШТОРЫ / ЖАЛЮЗИ
// ═══════════════════════════════════════════════════════════
// ── Шторы / Жалюзи ────────────────────────────────────────────────────────
let haCover=[];
async function fetchCover(){
  if(haCover.length)return;
  try{haCover=(await api('/api/sber_mqtt/ha_entities/cover')).entities||[];}
  catch(e){toast('Ошибка загрузки штор','err');}
}

function renderStep2Cover(){
  const sel=wData.entity_id;
  const batSel=wData.battery_entity;
  const batEntity=batSel?haSensors.find(x=>x.entity_id===batSel):null;
  const list=haCover.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите шторы / жалюзи (cover):</label></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('coverlist').innerHTML=coverItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('coverlist').innerHTML=coverItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" id="coverlist">${coverItems()}</div>
    </div>
    ${sel?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(sel)}</b></div>`:''}
    <div style="margin-top:18px">
      <div class="sf"><label>🔋 Датчик заряда батареи <span style="color:var(--muted);font-weight:400">(опционально)</span></label>
        <button class="sf-btn ${batSel?'filled':''}" onclick="openCoverBatteryPicker()">
          <span>${batSel?(batEntity?.friendly_name||batSel):'Выбрать сенсор…'}</span><span>${batSel?'✓':'▾'}</span>
        </button>
        ${batSel?`<div class="sf-sub">${esc(batSel)} <button class="sf-clr" onclick="clearCoverBattery()">✕</button></div>`:''}
        <div class="hint">Автоматически подтянется датчик батареи того же устройства. Если не задан — заряд не передаётся в Салют.</div>
      </div>
    </div>
    <div id="coverBatteryPicker" style="display:none;margin-top:10px">
      <div class="picker">
        <div class="psearch"><span style="color:var(--muted)">🔍</span>
          <input id="coverBatInput" type="text" placeholder="Поиск…" oninput="renderCoverBatList(this.value)"/>
          <button class="clr" onclick="coverBatInput.value='';renderCoverBatList('')">✕</button>
        </div>
        <div class="p-head"><div>Класс</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
        <div class="p-list" id="coverBatList"></div>
      </div>
    </div>`;
}

function coverItems(){
  const list=haCover.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Нет сущностей cover</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickCoverEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area)}','${esc(e.device_id||'')}')">
    <span class="dom-badge">cover</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickCoverEntity(eid,name,area,deviceId){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  if(deviceId){
    const batSensor=haSensors.find(s=>s.device_class==='battery'&&s.device_id===deviceId);
    if(batSensor){wData.battery_entity=batSensor.entity_id;wData.battery_entity_name=batSensor.friendly_name;}
  }
  document.getElementById('wizContent').innerHTML=renderStep2Cover();
}
function openCoverBatteryPicker(){
  const el=document.getElementById('coverBatteryPicker');
  el.style.display='';
  document.getElementById('coverBatInput').value='';
  renderCoverBatList('');
  el.scrollIntoView({behavior:'smooth'});
}
function renderCoverBatList(q){
  q=(q||'').toLowerCase();
  let list=haSensors.filter(s=>s.device_class==='battery');
  if(q)list=list.filter(s=>(s.area+s.entity_id+s.friendly_name).toLowerCase().includes(q));
  const el=document.getElementById('coverBatList');if(!el)return;
  el.innerHTML=list.length?list.map(s=>`<div class="p-item ${wData.battery_entity===s.entity_id?'sel':''} ${usedCls(s.entity_id)}" onclick="pickCoverBattery('${esc(s.entity_id)}','${esc(s.friendly_name)}')">
    <span class="dom-badge">${esc(s.device_class)}</span><span class="p-area">${esc(s.area||'—')}</span>
    <span class="p-name">${esc(s.friendly_name)}</span><span class="p-eid">${esc(s.entity_id)}</span></div>`).join(''):`<div class="p-empty">Нет датчиков батареи</div>`;
}
function pickCoverBattery(eid,name){wData.battery_entity=eid;wData.battery_entity_name=name;document.getElementById('wizContent').innerHTML=renderStep2Cover();}
function clearCoverBattery(){delete wData.battery_entity;delete wData.battery_entity_name;document.getElementById('wizContent').innerHTML=renderStep2Cover();}


// ═══════════════════════════════════════════════════════════
// WIZARD: ДАТЧИК ПРОТЕЧКИ
// ═══════════════════════════════════════════════════════════
// ── Датчик протечки ────────────────────────────────────────────────────────
let haWaterLeak=[];
async function fetchWaterLeak(){
  if(haWaterLeak.length)return;
  try{haWaterLeak=(await api('/api/sber_mqtt/ha_entities/water_leak')).entities||[];}
  catch(e){toast('Ошибка загрузки датчиков протечки','err');}
}

function renderStep2WaterLeak(){
  const sel=wData.entity_id;
  const batSel=wData.battery_entity;
  const batEntity=batSel?haSensors.find(x=>x.entity_id===batSel):null;
  const list=haWaterLeak.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите датчик протечки (binary_sensor, moisture):</label></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('wllist').innerHTML=wlItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('wllist').innerHTML=wlItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" style="max-height:160px" id="wllist">${wlItems()}</div>
    </div>
    ${sel?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(sel)}</b></div>`:''}
    <div style="margin-top:14px">
      <div class="sf"><label>🔋 Датчик заряда батареи <span style="color:var(--muted);font-weight:400">(опционально)</span></label>
        <button class="sf-btn ${batSel?'filled':''}" onclick="openWlBatteryPicker()">
          <span>${batSel?(batEntity?.friendly_name||batSel):'Выбрать сенсор…'}</span><span>${batSel?'✓':'▾'}</span>
        </button>
        ${batSel?`<div class="sf-sub">${esc(batSel)} <button class="sf-clr" onclick="clearWlBattery()">✕</button></div>`:''}
        <div class="hint">Автоматически подтягивается датчик батареи того же устройства.</div>
      </div>
    </div>
    <div id="wlBatteryPicker" style="display:none;margin-top:10px">
      <div class="picker">
        <div class="psearch"><span style="color:var(--muted)">🔍</span>
          <input id="wlBatInput" type="text" placeholder="Поиск…" oninput="renderWlBatList(this.value)"/>
          <button class="clr" onclick="wlBatInput.value='';renderWlBatList('')">✕</button>
        </div>
        <div class="p-head"><div>Класс</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
        <div class="p-list" style="max-height:160px" id="wlBatList"></div>
      </div>
    </div>`;
}
function wlItems(){
  const list=haWaterLeak.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Нет датчиков с device_class: moisture</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickWlEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area)}','${esc(e.device_id||'')}')">
    <span class="dom-badge">moisture</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickWlEntity(eid,name,area,deviceId){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  if(deviceId){
    const bat=haSensors.find(s=>s.device_class==='battery'&&s.device_id===deviceId);
    if(bat){wData.battery_entity=bat.entity_id;wData.battery_entity_name=bat.friendly_name;}
    else{delete wData.battery_entity;delete wData.battery_entity_name;}
  }
  document.getElementById('wizContent').innerHTML=renderStep2WaterLeak();
}
function openWlBatteryPicker(){
  const el=document.getElementById('wlBatteryPicker');
  el.style.display='';
  document.getElementById('wlBatInput').value='';
  renderWlBatList('');
  el.scrollIntoView({behavior:'smooth'});
}
function renderWlBatList(q){
  q=(q||'').toLowerCase();
  let list=haSensors.filter(s=>s.device_class==='battery');
  if(q)list=list.filter(s=>(s.area+s.entity_id+s.friendly_name).toLowerCase().includes(q));
  const el=document.getElementById('wlBatList');if(!el)return;
  el.innerHTML=list.length?list.map(s=>`<div class="p-item ${wData.battery_entity===s.entity_id?'sel':''} ${usedCls(s.entity_id)}" onclick="pickWlBattery('${esc(s.entity_id)}','${esc(s.friendly_name)}')">
    <span class="dom-badge">${esc(s.device_class)}</span><span class="p-area">${esc(s.area||'—')}</span>
    <span class="p-name">${esc(s.friendly_name)}</span><span class="p-eid">${esc(s.entity_id)}</span></div>`).join(''):`<div class="p-empty">Нет датчиков батареи</div>`;
}
function pickWlBattery(eid,name){wData.battery_entity=eid;wData.battery_entity_name=name;document.getElementById('wizContent').innerHTML=renderStep2WaterLeak();}
function clearWlBattery(){delete wData.battery_entity;delete wData.battery_entity_name;document.getElementById('wizContent').innerHTML=renderStep2WaterLeak();}


// ═══════════════════════════════════════════════════════════
// WIZARD: ДАТЧИК ДЫМА
// ═══════════════════════════════════════════════════════════
// ── Датчик дыма ───────────────────────────────────────────────────────────
let haSmoke=[];
async function fetchSmoke(){
  if(haSmoke.length)return;
  try{haSmoke=(await api('/api/sber_mqtt/ha_entities/smoke')).entities||[];}
  catch(e){toast('Ошибка загрузки датчиков дыма','err');}
}

function renderStep2Smoke(){
  const sel=wData.entity_id;
  const batSel=wData.battery_entity;
  const muteSel=wData.alarm_mute_entity;
  const batEntity=batSel?haSensors.find(x=>x.entity_id===batSel):null;
  const muteEntity=muteSel?haSocket.find(x=>x.entity_id===muteSel)||haSensors.find(x=>x.entity_id===muteSel):null;

  const optSlots=[
    {key:'battery_entity',    label:'🔋 Заряд батареи',   picker:'smokeBatPicker',  hint:'sensor (device_class: battery)'},
    {key:'alarm_mute_entity', label:'🔇 Отключение звука', picker:'smokeMutePicker', hint:'switch или input_boolean'},
  ];
  const optHtml=optSlots.map(slot=>{
    const eid=wData[slot.key]||'';
    const nm=wData[slot.key+'_name']||eid;
    return `<div class="sf" style="margin-top:10px">
      <label>${slot.label} <span style="color:var(--muted);font-weight:400">(опционально)</span></label>
      <button class="sf-btn ${eid?'filled':''}" onclick="document.getElementById('${slot.picker}').style.display='';document.getElementById('${slot.picker}').scrollIntoView({behavior:'smooth'})">
        <span>${eid?nm:'Выбрать…'}</span><span>${eid?'✓':'▾'}</span>
      </button>
      ${eid?`<div class="sf-sub">${esc(eid)} <button class="sf-clr" onclick="delete wData['${slot.key}'];delete wData['${slot.key}_name'];document.getElementById('wizContent').innerHTML=renderStep2Smoke()">✕</button></div>`:''}
      <div class="hint">${slot.hint}</div>
    </div>`;
  }).join('');

  return `<div class="fg" style="margin-bottom:10px"><label>Выберите датчик дыма (binary_sensor, smoke):</label></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('smokelist').innerHTML=smokeItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('smokelist').innerHTML=smokeItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" style="max-height:160px" id="smokelist">${smokeItems()}</div>
    </div>
    ${sel?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(sel)}</b></div>`:''}
    <div style="margin-top:14px">${optHtml}</div>
    <div id="smokeBatPicker" style="display:none;margin-top:10px"><div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input id="smokeBatInput" type="text" placeholder="Поиск…" oninput="renderSmokeBatList(this.value)"/>
        <button class="clr" onclick="smokeBatInput.value='';renderSmokeBatList('')">✕</button>
      </div>
      <div class="p-head"><div>Класс</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" style="max-height:160px" id="smokeBatList"></div>
    </div></div>
    <div id="smokeMutePicker" style="display:none;margin-top:10px"><div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input id="smokeMuteInput" type="text" placeholder="Поиск…" oninput="renderSmokeMuteList(this.value)"/>
        <button class="clr" onclick="smokeMuteInput.value='';renderSmokeMuteList('')">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" style="max-height:160px" id="smokeMuteList"></div>
    </div></div>`;
}
function smokeItems(){
  const list=haSmoke.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Нет датчиков с device_class: smoke</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickSmokeEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area)}','${esc(e.device_id||'')}')">
    <span class="dom-badge">smoke</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickSmokeEntity(eid,name,area,deviceId){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  if(deviceId){
    const bat=haSensors.find(s=>s.device_class==='battery'&&s.device_id===deviceId);
    if(bat){wData.battery_entity=bat.entity_id;wData.battery_entity_name=bat.friendly_name;}
    else{delete wData.battery_entity;delete wData.battery_entity_name;}
  }
  document.getElementById('wizContent').innerHTML=renderStep2Smoke();
}
function renderSmokeBatList(q){
  q=(q||'').toLowerCase();
  let list=haSensors.filter(s=>s.device_class==='battery');
  if(q)list=list.filter(s=>(s.area+s.entity_id+s.friendly_name).toLowerCase().includes(q));
  const el=document.getElementById('smokeBatList');if(!el)return;
  el.innerHTML=list.length?list.map(s=>`<div class="p-item ${wData.battery_entity===s.entity_id?'sel':''}" onclick="wData.battery_entity='${esc(s.entity_id)}';wData.battery_entity_name='${esc(s.friendly_name)}';document.getElementById('wizContent').innerHTML=renderStep2Smoke()">
    <span class="dom-badge">${esc(s.device_class)}</span><span class="p-area">${esc(s.area||'—')}</span>
    <span class="p-name">${esc(s.friendly_name)}</span><span class="p-eid">${esc(s.entity_id)}</span></div>`).join(''):`<div class="p-empty">Нет датчиков батареи</div>`;
}
function renderSmokeBatLowList(q){
  q=(q||'').toLowerCase();
  let list=haSensors.filter(s=>s.device_class==='battery'&&s.domain==='binary_sensor');
  if(!list.length)list=haSensors.filter(s=>s.device_class==='battery');
  if(q)list=list.filter(s=>(s.area+s.entity_id+s.friendly_name).toLowerCase().includes(q));
  const el=document.getElementById('smokeBatLowList');if(!el)return;
  el.innerHTML=list.length?list.map(s=>`<div class="p-item ${wData.battery_low_entity===s.entity_id?'sel':''}" onclick="wData.battery_low_entity='${esc(s.entity_id)}';wData.battery_low_entity_name='${esc(s.friendly_name)}';document.getElementById('wizContent').innerHTML=renderStep2Smoke()">
    <span class="dom-badge">${esc(s.device_class)}</span><span class="p-area">${esc(s.area||'—')}</span>
    <span class="p-name">${esc(s.friendly_name)}</span><span class="p-eid">${esc(s.entity_id)}</span></div>`).join(''):`<div class="p-empty">Нет binary_sensor с device_class: battery</div>`;
}
function renderSmokeSigList(q){
  q=(q||'').toLowerCase();
  let list=haSensors.filter(s=>s.device_class==='signal_strength'||s.device_class==='signal');
  if(!list.length)list=haSensors;
  if(q)list=list.filter(s=>(s.area+s.entity_id+s.friendly_name).toLowerCase().includes(q));
  const el=document.getElementById('smokeSigList');if(!el)return;
  el.innerHTML=list.length?list.map(s=>`<div class="p-item ${wData.signal_entity===s.entity_id?'sel':''}" onclick="wData.signal_entity='${esc(s.entity_id)}';wData.signal_entity_name='${esc(s.friendly_name)}';document.getElementById('wizContent').innerHTML=renderStep2Smoke()">
    <span class="dom-badge">${esc(s.device_class||'sensor')}</span><span class="p-area">${esc(s.area||'—')}</span>
    <span class="p-name">${esc(s.friendly_name)}</span><span class="p-eid">${esc(s.entity_id)}</span></div>`).join(''):`<div class="p-empty">Нет датчиков сигнала</div>`;
}
function renderSmokeMuteList(q){
  q=(q||'').toLowerCase();
  let list=haSocket.filter(e=>!q||(e.area+e.domain+e.entity_id+e.friendly_name).toLowerCase().includes(q));
  const el=document.getElementById('smokeMuteList');if(!el)return;
  el.innerHTML=list.length?list.map(e=>`<div class="p-item ${wData.alarm_mute_entity===e.entity_id?'sel':''}" onclick="wData.alarm_mute_entity='${esc(e.entity_id)}';wData.alarm_mute_entity_name='${esc(e.friendly_name)}';document.getElementById('wizContent').innerHTML=renderStep2Smoke()">
    <span class="dom-badge">${esc(e.domain)}</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join(''):`<div class="p-empty">Нет переключателей</div>`;
}
function openSmokeBatPicker(){const el=document.getElementById('smokeBatPicker');el.style.display='';document.getElementById('smokeBatInput').value='';renderSmokeBatList('');el.scrollIntoView({behavior:'smooth'});}
function pickSmokeBat(eid,name){wData.battery_entity=eid;wData.battery_entity_name=name;document.getElementById('wizContent').innerHTML=renderStep2Smoke();}
function clearSmokeBat(){delete wData.battery_entity;delete wData.battery_entity_name;document.getElementById('wizContent').innerHTML=renderStep2Smoke();}
function openSmokeMutePicker(){const el=document.getElementById('smokeMutePicker');el.style.display='';document.getElementById('smokeMuteInput').value='';renderSmokeMuteList('');el.scrollIntoView({behavior:'smooth'});}
function pickSmokeMute(eid,name){wData.alarm_mute_entity=eid;wData.alarm_mute_entity_name=name;document.getElementById('wizContent').innerHTML=renderStep2Smoke();}
function clearSmokeMute(){delete wData.alarm_mute_entity;delete wData.alarm_mute_entity_name;document.getElementById('wizContent').innerHTML=renderStep2Smoke();}


// ═══════════════════════════════════════════════════════════
// WIZARD: УВЛАЖНИТЕЛЬ ВОЗДУХА
// ═══════════════════════════════════════════════════════════
// ── Увлажнитель воздуха ───────────────────────────────────────────────────
let haHumidifier=[];
async function fetchHumidifier(){
  if(haHumidifier.length)return;
  try{haHumidifier=(await api('/api/sber_mqtt/ha_entities/humidifier')).entities||[];}
  catch(e){toast('Ошибка загрузки увлажнителей','err');}
}

const SBER_MODES=['auto','low','medium','high','turbo','quiet'];

function renderStep2Humidifier(){
  const sel=wData.entity_id;
  const entity=sel?haHumidifier.find(x=>x.entity_id===sel):null;
  const list=haHumidifier.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));

  // Опциональные сенсоры
  const optSlots=[
    {key:'water_percentage_entity', label:'💧 Уровень воды в баке', dc:null, hint:'sensor (% воды)'},
    {key:'replace_filter_entity',   label:'🔧 Замена фильтра',       dc:null, hint:'binary_sensor'},
  ];
  const optHtml=optSlots.map(slot=>{
    const eid=wData[slot.key]||'';
    return `<div class="sf">
      <label>${slot.label} <span style="color:var(--muted);font-weight:400">(опционально, ${slot.hint})</span></label>
      <button class="sf-btn ${eid?'filled':''}" onclick="openHumSensorPicker('${slot.key}')">
        <span>${eid||'Выбрать сущность…'}</span><span>${eid?'✓':'▾'}</span>
      </button>
      ${eid?`<div class="sf-sub">${esc(eid)} <button class="sf-clr" onclick="clearHumSensor('${slot.key}')">✕</button></div>`:''}
    </div>`;
  }).join('');

  return `<div class="fg" style="margin-bottom:10px"><label>Выберите увлажнитель воздуха:</label></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('humlist').innerHTML=humItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('humlist').innerHTML=humItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" style="max-height:160px" id="humlist">${humItems()}</div>
    </div>
    ${sel?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(sel)}</b></div>`:''}
    <div style="margin-top:14px;padding:12px 14px;border:1px solid var(--border);border-radius:8px;background:#fafafa">
      <div style="font-size:12px;font-weight:600;margin-bottom:8px;color:var(--fg)">Дополнительные сенсоры</div>
      ${optHtml}
    </div>
    <div id="humSensorPickerWrap" style="display:none;margin-top:10px">
      <div class="picker">
        <div class="psearch"><span style="color:var(--muted)">🔍</span>
          <input id="humSensorInput" type="text" placeholder="Поиск…" oninput="renderHumSensorList(this.value)"/>
          <button class="clr" onclick="humSensorInput.value='';renderHumSensorList('')">✕</button>
        </div>
        <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
        <div class="p-list" style="max-height:160px" id="humSensorList"></div>
      </div>
    </div>`;
}
function humItems(){
  const list=haHumidifier.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Нет увлажнителей (домен humidifier)</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickHumEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area)}')">
    <span class="dom-badge">humidifier</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickHumEntity(eid,name,area){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  document.getElementById('wizContent').innerHTML=renderStep2Humidifier();
}
let _humSensorPickerKey='';
function openHumSensorPicker(key){
  _humSensorPickerKey=key;
  const wrap=document.getElementById('humSensorPickerWrap');
  wrap.style.display='';
  document.getElementById('humSensorInput').value='';
  renderHumSensorList('');
  wrap.scrollIntoView({behavior:'smooth'});
}
function renderHumSensorList(q){
  q=(q||'').toLowerCase();
  let list=haSensors;
  if(q)list=list.filter(s=>(s.area+s.entity_id+s.friendly_name).toLowerCase().includes(q));
  const el=document.getElementById('humSensorList');if(!el)return;
  el.innerHTML=list.length?list.map(s=>`<div class="p-item ${wData[_humSensorPickerKey]===s.entity_id?'sel':''} ${usedCls(s.entity_id)}" onclick="pickHumSensor('${esc(s.entity_id)}')">
    <span class="dom-badge">${esc(s.device_class||'sensor')}</span><span class="p-area">${esc(s.area||'—')}</span>
    <span class="p-name">${esc(s.friendly_name)}</span><span class="p-eid">${esc(s.entity_id)}</span></div>`).join(''):`<div class="p-empty">Ничего не найдено</div>`;
}
function pickHumSensor(eid){
  wData[_humSensorPickerKey]=eid;
  document.getElementById('wizContent').innerHTML=renderStep2Humidifier();
}
function clearHumSensor(key){delete wData[key];document.getElementById('wizContent').innerHTML=renderStep2Humidifier();}


// ═══════════════════════════════════════════════════════════
// УТИЛИТЫ
// ═══════════════════════════════════════════════════════════
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
function slugify(t){const m={а:'a',б:'b',в:'v',г:'g',д:'d',е:'e',ё:'yo',ж:'zh',з:'z',и:'i',й:'j',к:'k',л:'l',м:'m',н:'n',о:'o',п:'p',р:'r',с:'s',т:'t',у:'u',ф:'f',х:'h',ц:'ts',ч:'ch',ш:'sh',щ:'sch',ъ:'',ы:'y',ь:'',э:'e',ю:'yu',я:'ya',' ':'_'};return t.toLowerCase().split('').map(c=>m[c]!==undefined?m[c]:(/[a-z0-9]/.test(c)?c:'_')).join('').replace(/_+/g,'_').replace(/^_|_$/g,'')||'device';}
let toastT=null;
function toast(msg,type=''){const el=document.getElementById('toast');el.textContent=msg;el.className='toast '+type+' show';clearTimeout(toastT);toastT=setTimeout(()=>el.classList.remove('show'),3200);}


// ═══════════════════════════════════════════════════════════
// ИНИЦИАЛИЗАЦИЯ
// ═══════════════════════════════════════════════════════════
async function init(){
  await Promise.all([loadStatus(), loadDevices(), checkDevTools()]);
  setInterval(loadStatus,30000);
}

async function checkDevTools(){
  try{
    const r = await api('/api/sber_mqtt/devtools/exists');
    if(r.exists) document.getElementById('btnDevTools').style.display='';
  } catch(e){}
}

window.addEventListener('load', init);
