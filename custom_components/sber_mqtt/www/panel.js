// Sber MQTT Bridge — панель управления
// Токен вшивается сервером: window.HA_ACCESS_TOKEN

// ── Настройки ─────────────────────────────────────────────────────────
async function openSettings(){
  try{
    const r=await api('/api/sber_mqtt/settings');
    const sel=document.getElementById('settingsUser');
    sel.innerHTML='<option value="">— без указания —</option>'+(r.users||[]).map(u=>`<option value="${esc(u.id)}" ${u.id===r.user_id?'selected':''}>${esc(u.name)}</option>`).join('');
    document.getElementById('settingsOverlay').style.display='flex';
  }catch(e){toast('Ошибка: '+e.message,'err');}
}
function closeSettings(){document.getElementById('settingsOverlay').style.display='none';}
async function saveSettings(){
  const user_id=document.getElementById('settingsUser').value;
  try{
    await api('/api/sber_mqtt/settings',{method:'POST',body:JSON.stringify({user_id})});
    closeSettings();
    toast('Сохранено','ok');
  }catch(e){toast('Ошибка: '+e.message,'err');}
}

// Floating Action Button — показывать когда кнопка «Добавить» ушла за скролл
window.addEventListener('scroll',()=>{
  const fabTop=document.querySelector('.fab-top');
  const show=window.scrollY>120;
  if(fabTop)fabTop.classList.toggle('visible',show);
});


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
const TYPE_LABELS = { relay:'Реле', sensor_temp:'Датчик температуры/влажности', scenario_button:'Сценарная кнопка', hvac_ac:'Кондиционер', vacuum_cleaner:'Пылесос', valve:'Кран', light:'Лампа', cover:'Рулонные шторы / жалюзи', water_leak:'Датчик протечки', humidifier:'Увлажнитель воздуха', socket:'Розетка', smoke:'Датчик дыма', kettle:'Чайник', tv:'Телевизор', air_purifier:'Очиститель воздуха' };
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
  kettle:          ['Тип устройства','Источник в HA','Параметры'],
  tv:              ['Тип устройства','Источник в HA','Параметры'],
  air_purifier:    ['Тип устройства','Функции и сущности HA','Параметры'],
  humidifier:      ['Тип устройства','Источник в HA','Параметры'],
  socket:          ['Тип устройства','Источник в HA','Параметры'],
  sensor_door:     ['Тип устройства','Датчик в HA','Параметры'],
  sensor_air:      ['Тип устройства','Датчики в HA','Параметры'],
  sensor_pir:      ['Тип устройства','Датчик в HA','Параметры'],
  hvac_radiator:   ['Тип устройства','Источник в HA','Параметры'],
  hvac_fan:        ['Тип устройства','Источник в HA','Параметры'],
  tv:              ['Тип устройства','Источник в HA','Параметры'],
  intercom:        ['Тип устройства','Источник в HA','Параметры'],
  automation_relay:['Тип устройства','Автоматизация в HA','Параметры'],
  script_relay:    ['Тип устройства','Сценарий / скрипт в HA','Параметры'],
  event_button:    ['Тип устройства','Настройка события','Параметры'],
};

let devices=[], sortField='name', sortAsc=true, delId=null;
let wStep=1, wType=null, wData={}, haRelay=[], haSensors=[], haSocket=[], sFilter='', spField=null;

// Множество entity_id, уже используемых в добавленных устройствах
let usedEntities=new Set();
let devFilter='';
function refreshUsedEntities(){
  usedEntities=new Set();
  const attrKeys=['entity_id','power_entity','current_entity','voltage_entity',
    'temperature_entity','humidity_entity','battery_entity',
    'water_percentage_entity','replace_filter_entity','alarm_mute_entity',
    'speed_entity','night_mode_entity','ionization_entity','aromatization_entity',
    'decontaminate_entity','replace_ionizator_entity','online_entity'];
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

function autoBadge(eid){
  const used=devices.filter(d=>d.attributes&&d.attributes.entity_id===eid);
  if(!used.length)return'';
  return used.map(d=>'<span class="p-used-badge">уже добавлено'+(d.attributes.trigger_id?': '+d.attributes.trigger_id:'')+'</span>').join(' ');
}


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
  let filtered = devFilter
    ? devices.filter(d => (d.name||'').toLowerCase().includes(devFilter))
    : [...devices];
  const rows=filtered.sort((a,b)=>{
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
      <td class="del-col"><button class="btn btn-ghost btn-sm" onclick="editDevice('${esc(d.id)}')">✏️</button><button class="btn btn-ghost btn-sm" onclick="askDel('${esc(d.id)}','${esc(d.name)}')">🗑</button></td>
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

function editDevice(id){
  const d=devices.find(x=>x.id===id);if(!d)return;
  wType=d.device_type;
  wData={id:d.id,name:d.name,room:d.room||'',_edit:true};
  const a=d.attributes||{};
  for(const [k,v] of Object.entries(a)){wData[k]=v;wData[k+'_name']=v;wData[k+'_area']='';}
  wStep=1;
  document.getElementById('wiz').style.display='';
  renderWiz();
  // Программно жмём «Далее» чтобы попасть на шаг 2 с загрузкой данных
  setTimeout(()=>document.getElementById('btnNext')?.click(),100);
}
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
  wStep=1;wType=null;wData={};sFilter='';spField=null;haRelay=[];haSensors=[];haClimate=[];haVacuum=[];haValve=[];haLight=[];haCover=[];haWaterLeak=[];haHumidifier=[];haSmoke=[];haKettle=[];haNumber=[];haDoor=[];haAir=[];haRadiator=[];haFan=[];haTV=[];haAP={power:[],controls:[],sensors:[]};haIntercom=[];haPir=[];haEventBtns=[];
  const btn=document.getElementById('btnNext');
  if(btn){btn.disabled=false;btn.textContent='Далее →';}
}

async function wizNext(){
  if(!await wizValidate())return;
  const total=(STEPS[wType]||['','','']).length;
  if(wStep<total){
    wStep++;
    // Загружаем список сущностей при переходе на шаг 2 (если ещё не загружены)
    if(wStep===2){if(wType==='relay')await Promise.all([fetchRelay(),fetchSensors()]);if(wType==='sensor_temp')await fetchSensors();if(wType==='scenario_button')await fetchRelay();if(wType==='hvac_ac')await Promise.all([fetchClimate(),fetchSensors(),fetchSocket()]);if(wType==='vacuum_cleaner')await Promise.all([fetchVacuum(),fetchSensors()]);if(wType==='valve')await fetchValve();if(wType==='light')await fetchLight();if(wType==='cover')await Promise.all([fetchCover(),fetchSensors()]);if(wType==='water_leak')await Promise.all([fetchWaterLeak(),fetchSensors()]);if(wType==='humidifier')await Promise.all([fetchHumidifier(),fetchSensors()]);if(wType==='socket')await Promise.all([fetchSocket(),fetchSensors()]);if(wType==='smoke')await Promise.all([fetchSmoke(),fetchSensors()]);if(wType==='kettle')await Promise.all([fetchKettle(),fetchWaterSensors()]);if(wType==='sensor_door')await Promise.all([fetchDoor(),fetchSensors()]);if(wType==='sensor_air')await fetchSensors();if(wType==='hvac_radiator')await Promise.all([fetchRadiator(),fetchSensors()]);if(wType==='hvac_fan')await Promise.all([fetchFan(),fetchSensors()]);if(wType==='tv')await fetchTV();if(wType==='intercom')await fetchIntercom();if(wType==='sensor_pir')await fetchPir();if(wType==='automation_relay')await fetchRelay();if(wType==='script_relay')await fetchRelay();if(wType==='event_button')await Promise.all([fetchEventBtns(),fetchSensors()]);if(wType==='air_purifier')await fetchAP();}
    renderWiz();
    setTimeout(()=>document.getElementById('wizContent')?.scrollIntoView({behavior:'smooth',block:'start'}),50);
  }else{
    await submitDevice();
  }
}
function wizBack(){if(wStep>1){wStep--;renderWiz();setTimeout(()=>document.getElementById('wizContent')?.scrollIntoView({behavior:'smooth',block:'start'}),50);}}

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
    if(wType==='kettle'){
      if(!wData.entity_id){toast('Выберите сущность чайника','err');return false;}
      if(!wData.off_mode){toast('Укажите режим для команды «Выключить»','err');return false;}
      if(!wData.boil_mode){toast('Укажите режим для команды «Вскипятить»','err');return false;}
    }
    if(wType==='tv'&&!wData.entity_id){toast('Выберите телевизор (media_player)','err');return false;}
    if(wType==='air_purifier'){const e=apValidate();if(e){toast(e,'err');return false;}}
    if(wType==='humidifier'&&!wData.entity_id){toast('Выберите увлажнитель','err');return false;}
    if(wType==='sensor_temp'&&!wData.temperature_entity&&!wData.humidity_entity){toast('Выберите температуру или влажность','err');return false;}
    if(wType==='sensor_door'&&!wData.entity_id){toast('Выберите датчик открытия','err');return false;}
    if(wType==='hvac_radiator'&&!wData.entity_id){toast('Выберите климатическую сущность','err');return false;}
    if(wType==='hvac_fan'&&!wData.entity_id){toast('Выберите вентилятор','err');return false;}
    if(wType==='tv'&&!wData.entity_id){toast('Выберите телевизор','err');return false;}
    if(wType==='intercom'&&!wData.entity_id){toast('Выберите домофон','err');return false;}
    if(wType==='sensor_pir'&&!wData.entity_id){toast('Выберите датчик движения','err');return false;}
    if(wType==='automation_relay'&&!wData.entity_id){toast('Выберите автоматизацию','err');return false;}
    if(wType==='script_relay'&&!wData.entity_id){toast('Выберите скрипт','err');return false;}
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
    if(!wData._edit && devices.find(d=>d.id===id)){toast(`ID «${id}» уже занят`,'err');return false;}
    wData.name=name;if(!wData._edit)wData.id=id;wData.room=document.getElementById('dRoom')?.value?.trim()||'';
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
  else if(wStep===2){if(wType==='relay')c.innerHTML=renderStep2Relay();else if(wType==='scenario_button')c.innerHTML=renderStep2ScenarioButton();else if(wType==='hvac_ac')c.innerHTML=renderStep2HvacAc();else if(wType==='vacuum_cleaner')c.innerHTML=renderStep2Vacuum();else if(wType==='valve')c.innerHTML=renderStep2Valve();else if(wType==='light')c.innerHTML=renderStep2Light();else if(wType==='cover')c.innerHTML=renderStep2Cover();else if(wType==='water_leak')c.innerHTML=renderStep2WaterLeak();else if(wType==='humidifier')c.innerHTML=renderStep2Humidifier();else if(wType==='socket')c.innerHTML=renderStep2Socket();else if(wType==='smoke')c.innerHTML=renderStep2Smoke();else if(wType==='kettle')c.innerHTML=renderStep2Kettle();else if(wType==='sensor_door')c.innerHTML=renderStep2SensorDoor();else if(wType==='sensor_air')c.innerHTML=renderStep2SensorAir();else if(wType==='hvac_radiator')c.innerHTML=renderStep2Radiator();else if(wType==='hvac_fan')c.innerHTML=renderStep2Fan();else if(wType==='tv')c.innerHTML=renderStep2TV();else if(wType==='intercom')c.innerHTML=renderStep2Intercom();else if(wType==='sensor_pir')c.innerHTML=renderStep2Pir();else if(wType==='automation_relay')c.innerHTML=renderStep2Automation();else if(wType==='script_relay')c.innerHTML=renderStep2Script();else if(wType==='event_button')c.innerHTML=renderStep2EventButton();else if(wType==='air_purifier')c.innerHTML=renderStep2AirPurifier();else c.innerHTML=renderStep2Sensor();}
  else c.innerHTML=renderStep3();
  if(wStep===3){setTimeout(updateNameCount,0);setTimeout(loadTriggerChips,100);}
}

function renderStep1(){
  const groups=[
    {label:'Управление', items:[
      {id:'relay',          icon:'🔌', name:'Реле',                    desc:'switch, light, input_boolean, media_player, script, button — включение и выключение'},
      {id:'socket',         icon:'🔋', name:'Розетка',                 desc:'switch, input_boolean — включение/выключение + энергомониторинг (мощность, ток, напряжение)'},
      {id:'light',          icon:'💡', name:'Лампа',                   desc:'light — яркость, цвет, цветовая температура'},
      {id:'hvac_ac',        icon:'❄️', name:'Кондиционер',             desc:'climate — температура и режимы работы'},
      {id:'humidifier',     icon:'💧', name:'Увлажнитель воздуха',     desc:'humidifier — влажность, режим, скорость вентилятора'},
      {id:'kettle',         icon:'☕', name:'Чайник',                  desc:'water_heater — включение, целевая и текущая температура воды'},
      {id:'tv',             icon:'📺', name:'Телевизор',               desc:'media_player — включение, громкость и отключение звука (mute)'},
      {id:'air_purifier',   icon:'🌬️', name:'Очиститель воздуха',      desc:'switch + select + sensor — вкл/выкл, скорость, режимы, замена фильтра'},
      {id:'vacuum_cleaner', icon:'🤖', name:'Пылесос',                 desc:'vacuum — управление уборкой'},
      {id:'valve',          icon:'🚰', name:'Кран',                    desc:'valve, switch — открытие и закрытие'},
      {id:'cover',          icon:'🔲', name:'Рулонные шторы / жалюзи', desc:'cover — открытие, закрытие, позиционирование'},
      {id:'hvac_fan',       icon:'🌀', name:'Бризер / вентилятор',       desc:'fan, switch — вкл/выкл + скорость'},
      {id:'hvac_radiator',  icon:'🌡️', name:'Термоголовка радиатора',     desc:'climate — вкл/выкл + целевая температура'},
      {id:'tv',             icon:'📺', name:'Телевизор',                   desc:'media_player — вкл/выкл, громкость, каналы'},
      {id:'intercom',       icon:'📞', name:'Домофон',                     desc:'switch/button/lock — открытие двери + датчик вызова'},
    ]},
    {label:'Датчики', items:[
      {id:'sensor_temp',    icon:'🌡️', name:'Датчик температуры/влажности', desc:'sensor — температура и влажность'},
      {id:'sensor_door',    icon:'🚪', name:'Датчик открытия',              desc:'binary_sensor (door/window) — открыто/закрыто'},
      {id:'sensor_air',     icon:'🍃', name:'Датчик качества воздуха',     desc:'sensor — CO2, PM2.5, TVOC, температура, влажность'},
      {id:'water_leak',     icon:'🌊', name:'Датчик протечки',              desc:'binary_sensor (moisture) — обнаружение воды'},
      {id:'smoke',          icon:'🔥', name:'Датчик дыма',                  desc:'binary_sensor (smoke) — обнаружение дыма'},
      {id:'sensor_pir',     icon:'🏃', name:'Датчик движения',             desc:'binary_sensor (motion) — обнаружение движения'},
    ]},
    {label:'Автоматизации', items:[
      {id:'scenario_button',icon:'🔔', name:'Сценарная кнопка', desc:'Прокидывает события из HA в Салют: вкл → click, выкл → double_click'},
      {id:'automation_relay',icon:'⚡', name:'Автоматизация',   desc:'automation — запуск автоматизации HA по команде из Салюта'},
      {id:'script_relay',     icon:'📜', name:'Сценарий / скрипт', desc:'script — запуск скрипта HA по команде из Салюта'},
      {id:'event_button',    icon:'🔘', name:'Кнопка событий',   desc:'HA event → button_event в Сбер (click/double_click)'},
    ]},
  ];
  return groups.map(g=>`
    <div style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.6px;color:var(--muted);margin:14px 0 6px;padding-left:2px">${g.label}</div>
    <div class="type-grid">${g.items.map(t=>`<div class="type-card ${wType===t.id?'sel':''}" onclick="pickType('${t.id}')">
      <div class="type-icon" style="font-size:22px">${t.icon}</div>
      <div style="min-width:0"><div class="type-name" style="font-size:12px;margin-bottom:2px">${t.name}</div><div class="type-desc" style="font-size:10px">${t.desc}</div></div></div>`).join('')}</div>
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
  const list=haRelay.filter(e=>e.domain!=='automation'&&e.domain!=='script'&&(!sFilter||(e.area+e.domain+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase())));
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
    <div style="margin-top:14px;padding:12px 14px;border:1px solid var(--border);border-radius:8px;background:var(--bg)">
      <div style="font-size:12px;font-weight:600;margin-bottom:6px;color:var(--text)">⚡ Энергомониторинг</div>
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
  const clsMap={temperature_entity:'temperature',battery_entity:'battery',co2_entity:'carbon_dioxide',pm25_entity:'pm25',tvoc_entity:'volatile_organic_compounds',signal_entity:'signal_strength'};
  let list=spField==='humidity_entity'
    ? haSensors.filter(s=>s.device_class==='humidity'||s.device_class==='moisture')
    : (clsMap[spField]?haSensors.filter(s=>s.device_class===clsMap[spField]):haSensors);
  // Если фильтр ничего не дал — показываем все (template-сенсоры и т.п.)
  if(!list.length) list=haSensors;
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
  if(wType==='relay'||wType==='socket'||wType==='scenario_button'||wType==='hvac_ac'||wType==='vacuum_cleaner'||wType==='valve'||wType==='light'||wType==='cover'||wType==='water_leak'||wType==='humidifier'||wType==='smoke'||wType==='kettle'||wType==='sensor_door'||wType==='hvac_radiator'||wType==='hvac_fan'||wType==='tv'||wType==='intercom'||wType==='sensor_pir'||wType==='automation_relay'||wType==='script_relay'||wType==='air_purifier'){defName=wData.entity_name||'';defRoom=wData.entity_area||'';}
  else{defName=wData.temperature_entity_name||wData.humidity_entity_name||'';defRoom=wData.temperature_entity_area||wData.humidity_entity_area||'';}
  return `<div class="fg"><label>Имя <span style="color:var(--danger)">*</span></label>
    <input type="text" id="dName" value="${esc(wData.name||defName)}" oninput="autoId();updateNameCount()" placeholder="Свет в гостиной"/>
    <div style="font-size:11px;color:var(--text-muted,#888);margin-top:4px">Только русские буквы, цифры и пробелы · от 3 до 33 символов · <span id="nameCount">0/33</span></div></div>
    <div class="fg"><label>ID <span style="color:var(--danger)">*</span></label>
    <input type="text" id="dId" value="${esc(wData.id||slugify(wData.name||defName))}" placeholder="relay_living_room"/>
    <div class="hint">Только a–z, 0–9, _ . Уникальный идентификатор в Сбере.</div></div>
    <div class="fg"><label>Комната</label>
    <input type="text" id="dRoom" value="${esc(wData.room!==undefined?wData.room:defRoom)}" placeholder="Гостиная" oninput="autoId()"/>
    <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">${[...new Set(devices.map(d=>d.room).filter(Boolean))].sort().map(r=>`<span class="room-chip" onclick="document.getElementById('dRoom').value='${esc(r)}';autoId()" style="cursor:pointer;background:var(--primary-lt);color:var(--primary-dk);padding:2px 8px;border-radius:12px;font-size:11px;white-space:nowrap">${esc(r)}</span>`).join('')}</div></div>
    ${(wType==='automation_relay'||(wType==='relay'&&wData.entity_id&&wData.entity_id.startsWith('automation.')))?`<div class="fg"><label>ID триггера (опционально)</label><input type="text" id="triggerIdInput" value="${esc(wData.trigger_id||'')}" oninput="wData.trigger_id=this.value;autoId()" placeholder="manual_trigger_id"/><div class="hint">Для автоматизаций с несколькими триггерами</div><div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px" id="triggerChips"></div></div>`:''}
    ${wType==='event_button'?renderEventButtonStep3():''}`;
}
function autoId(){if(wData._edit)return;const n=document.getElementById('dName')?.value||'';const f=document.getElementById('dId');const r=document.getElementById('dRoom')?.value||'';if(f&&(!wData.id||f.value===slugify(wData.name||''))){var id=slugify(n);if(r)id+='_'+slugify(r);if(wType==='automation_relay'&&wData.trigger_id)id+='_'+slugify(wData.trigger_id);f.value=id;}}

async function loadTriggerChips(){
  const c=document.getElementById('triggerChips');if(!c)return;
  const eid=wData.entity_id;if(!eid)return;
  try{
    const r1=await api('/api/sber_mqtt/ha_entities/automation_triggers?entity_id='+encodeURIComponent(eid));
    if(r1.automation_id){
      const r2=await api('/api/config/automation/config/'+r1.automation_id);
      const ids=(r2.triggers||[]).map(t=>t.id).filter(Boolean);
      c.innerHTML=ids.map(t=>{
        const used=devices.some(d=>d.attributes&&d.attributes.entity_id===eid&&d.attributes.trigger_id===t);
        const bg=used?'var(--primary-lt)':'var(--bg)';
        const clr=used?'var(--primary-dk)':'var(--muted)';
        const brd=used?'':'border:1px solid var(--border)';
        return'<span class="room-chip" onclick="var inp=document.getElementById(\'triggerIdInput\');if(inp){inp.value=\''+esc(t)+'\';wData.trigger_id=\''+esc(t)+'\';autoId();}" style="cursor:pointer;background:'+bg+';color:'+clr+';padding:2px 8px;border-radius:12px;font-size:11px;white-space:nowrap;'+brd+'">'+esc(t)+'</span>';
      }).join('');
    }
  }catch(e){}}function updateNameCount(){const i=document.getElementById('dName');const c=document.getElementById('nameCount');if(i&&c){const len=(i.value||'').length;c.textContent=len+'/33';c.style.color=len>33?'var(--danger)':'';}}

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
    if(wData.hvac_modes)attrs.hvac_modes=wData.hvac_modes;
    if(wData.fan_modes)attrs.fan_modes=wData.fan_modes;
    if(wData.preset_modes)attrs.preset_modes=wData.preset_modes;
    if(wData.swing_modes)attrs.swing_modes=wData.swing_modes;
    if(wData.min_temp!==undefined)attrs.min_temp=wData.min_temp;
    if(wData.max_temp!==undefined)attrs.max_temp=wData.max_temp;
    if(wData.target_temp_step!==undefined)attrs.target_temp_step=wData.target_temp_step;
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
  else if(wType==='kettle'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    if(wData.water_entity) attrs.water_entity=wData.water_entity;
    if(wData.water_low_entity) attrs.water_low_entity=wData.water_low_entity;
    if(wData.off_mode) attrs.off_mode=wData.off_mode;
    if(wData.boil_mode)attrs.boil_mode=wData.boil_mode;
    if(wData.heat_mode)attrs.heat_mode=wData.heat_mode;
  }
  else if(wType==='tv'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    // Возможности сущности — по ним на сервере формируется набор функций ТВ в Сбере
    const f=wData.tv_features||{};
    for(const k of ['supports_volume_set','supports_mute','supports_volume_step']){
      if(k in f)attrs[k]=!!f[k];
    }
  }
  else if(wType==='air_purifier'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    for(const k of AP_ATTR_KEYS){
      const v=wData[k];
      if(v===undefined||v===null||v==='')continue;
      attrs[k]=(k.endsWith('_threshold'))?Number(v):v;
    }
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
    for(const f of ['light_brightness','light_colour','light_colour_temp','light_mode']){
      attrs[f]=!!(wData.light_features&&wData.light_features.includes(f));
    }
  }
  else if(wType==='sensor_door'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    if(wData.battery_entity)attrs.battery_entity=wData.battery_entity;
    if(wData.tamper_entity) attrs.tamper_entity=wData.tamper_entity;
  }
  else if(wType==='hvac_radiator'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    if(wData.temperature_entity)attrs.temperature_entity=wData.temperature_entity;
  }
  else if(wType==='hvac_fan'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
  }
  else if(wType==='tv'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
  }
  else if(wType==='intercom'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    if(wData.incoming_call_entity) attrs.incoming_call_entity=wData.incoming_call_entity;
  }
  else if(wType==='sensor_pir'){
    attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';
    if(wData.battery_entity) attrs.battery_entity=wData.battery_entity;
  }
  else if(wType==='automation_relay'){attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';if(wData.trigger_id)attrs.trigger_id=wData.trigger_id;}
  else if(wType==='script_relay'){attrs.entity_id=wData.entity_id;attrs.entity_name=wData.entity_name||'';}
  else if(wType==='event_button'){attrs.event_type=wData.event_type||'';attrs.action_map=wData.action_map||{};}
  else if(wType==='sensor_air'){['temperature_entity','humidity_entity','co2_entity','pm25_entity','tvoc_entity','battery_entity','signal_entity'].forEach(k=>{if(wData[k])attrs[k]=wData[k];});}
  else{['temperature_entity','humidity_entity','battery_entity'].forEach(k=>{if(wData[k])attrs[k]=wData[k];});}
  const body={id:wData.id,name:wData.name,room:wData.room||'',device_type:(wType==='automation_relay'||wType==='script_relay')?'relay':wType,attributes:attrs};
  const btn=document.getElementById('btnNext');btn.disabled=true;btn.innerHTML='<div class="spin"></div>';
  try{
    const exists=wData._edit || devices.some(d=>d.id===wData.id);
    const method=exists?'PUT':'POST';
    const url=exists?`/api/sber_mqtt/devices/${wData.id}`:'/api/sber_mqtt/devices';
    const res = await api(url,{method,body:JSON.stringify(body)});
    closeWizard();
    toast(exists?'Устройство обновлено':'Устройство добавлено','ok');
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
async function fetchSensors(){if(haSensors.length)return;try{haSensors=(await api('/api/sber_mqtt/ha_entities/sensors?classes=temperature,humidity,moisture,battery,signal_strength,power,current,voltage,carbon_dioxide,pm25,volatile_organic_compounds')).entities||[];}catch(e){toast('Ошибка загрузки сенсоров','err');}}

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
function pickHvacEntity(eid,name,area){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  var ce=haClimate.find(function(x){return x.entity_id===eid;});
  if(ce){
    wData.hvac_modes=ce.hvac_modes||[];
    wData.fan_modes=ce.fan_modes||[];
    wData.preset_modes=ce.preset_modes||[];
    wData.swing_modes=ce.swing_modes||[];
    wData.min_temp=ce.min_temp;
    wData.max_temp=ce.max_temp;
    wData.target_temp_step=ce.target_temp_step;
  }
  document.getElementById('wizContent').innerHTML=renderStep2HvacAc();
}
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
    <div style="margin-top:14px;padding:12px 14px;border:1px solid var(--border);border-radius:8px;background:var(--bg)">
      <div style="font-size:12px;font-weight:600;margin-bottom:8px;color:var(--text)">Дополнительные сенсоры</div>
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


// ═══════════════════════════════════════════════════════════
// WIZARD: ЧАЙНИК
// ═══════════════════════════════════════════════════════════

let haKettle=[], haNumber=[], haDoor=[], haAir=[], haRadiator=[], haFan=[], haWaterSensors=[], haIntercom=[], haPir=[], haEventBtns=[];

async function fetchKettle(){
  if(haKettle.length)return;
  try{haKettle=(await api('/api/sber_mqtt/ha_entities/water_heater')).entities||[];}
  catch(e){toast('Ошибка загрузки сущностей','err');}
}

async function fetchNumber(){
  if(haNumber.length)return;
  try{haNumber=(await api('/api/sber_mqtt/ha_entities/number')).entities||[];}
  catch(e){toast('Ошибка загрузки number-сущностей','err');}
}

async function fetchWaterSensors(){
  if(haWaterSensors.length)return;
  try{haWaterSensors=(await api('/api/sber_mqtt/ha_entities/water_sensors')).entities||[];}
  catch(e){toast('Ошибка загрузки сенсоров','err');}
}

async function fetchEventBtns(){
  if(haEventBtns.length)return;
  try{haEventBtns=(await api('/api/sber_mqtt/ha_entities/event_buttons')).entities||[];}
  catch(e){toast('Ошибка загрузки кнопок','err');}
}

function renderStep2Kettle(){
  const sel = wData.entity_id;
  const selEntity = haKettle.find(e=>e.entity_id===sel);
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите чайник (water_heater):</label></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('kettlelist').innerHTML=kettleItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('kettlelist').innerHTML=kettleItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" style="max-height:200px" id="kettlelist">${kettleItems()}</div>
    </div>
    ${sel?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(sel)}</b></div>`:''}
    ${sel?renderKettleModes(selEntity):''}
    <div style="margin-top:12px;font-size:11px;color:var(--muted)">
      Текущая и целевая температура воды подтягиваются автоматически из атрибутов сущности.
    </div>
    ${sel?`<div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border,#e0e0e0)">
      <div class="sf"><label>💧 Уровень воды (опционально)</label>
        <button class="sf-btn ${wData.water_entity?'filled':''}" onclick="openKettleWater()">
          <span>${wData.water_entity?(wData.water_entity_name||wData.water_entity):'Выбрать сенсор…'}</span><span>${wData.water_entity?'✓':'▾'}</span></button>
        ${wData.water_entity?`<div class="sf-sub">${esc(wData.water_entity)} <button class="sf-clr" onclick="delete wData.water_entity;delete wData.water_entity_name;document.getElementById('wizContent').innerHTML=renderStep2Kettle()">✕</button></div>`:''}
      </div>
      <div class="sf"><label>🔴 Мало воды (опционально)</label>
        <button class="sf-btn ${wData.water_low_entity?'filled':''}" onclick="openKettleWaterLow()">
          <span>${wData.water_low_entity?(wData.water_low_entity_name||wData.water_low_entity):'Выбрать binary_sensor…'}</span><span>${wData.water_low_entity?'✓':'▾'}</span></button>
        ${wData.water_low_entity?`<div class="sf-sub">${esc(wData.water_low_entity)} <button class="sf-clr" onclick="delete wData.water_low_entity;delete wData.water_low_entity_name;document.getElementById('wizContent').innerHTML=renderStep2Kettle()">✕</button></div>`:''}
      </div>
      <div id="kettleWaterPicker" style="display:none;margin-top:6px">
        <div class="picker">
          <div class="psearch"><span style="color:var(--muted)">🔍</span>
            <input type="text" placeholder="Поиск…" oninput="renderKettleWaterList(this.value)"/></div>
          <div class="p-list" style="max-height:140px" id="kettleWaterList"></div></div></div>
      <div id="kettleWaterLowPicker" style="display:none;margin-top:6px">
        <div class="picker">
          <div class="p-list" style="max-height:140px" id="kettleWaterLowList"></div></div></div>
    </div>`:''}`;
}

function kettleItems(){
  const list=haKettle.filter(e=>!sFilter||(e.area+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Нет water_heater сущностей</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickKettleEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area)}')">
    <span class="dom-badge">${esc(e.domain)}</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}

// Сопоставление команд Сбера (вскипятить/нагреть/выключить) с реальными
// значениями operation_list устройства — у разных чайников свой набор
// и свои названия режимов, поэтому пользователь выбирает их вручную.
const ICON_POWER  = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M13 3h-2v10h2V3zm4.83 2.17-1.42 1.42A6.92 6.92 0 0 1 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-2.24 1.06-4.23 2.71-5.5L6.29 5.08A8.94 8.94 0 0 0 3 12c0 4.97 4.03 9 9 9s9-4.03 9-9a8.94 8.94 0 0 0-3.17-6.83z"/></svg>';
const ICON_BOIL   = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M13.5.67s.74 2.65.74 4.8c0 2.06-1.35 3.73-3.41 3.73-2.07 0-3.63-1.67-3.63-3.73l.03-.36C5.21 7.51 4 10.62 4 14c0 4.42 3.58 8 8 8s8-3.58 8-8C20 8.61 17.41 3.8 13.5.67zM11.71 19c-1.78 0-3.22-1.4-3.22-3.14 0-1.62 1.05-2.76 2.81-3.12 1.77-.36 3.6-1.21 4.62-2.58.39 1.29.59 2.65.59 4.04 0 2.65-2.15 4.8-4.8 4.8z"/></svg>';
const ICON_HEAT   = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M15 13V5c0-1.66-1.34-3-3-3S9 3.34 9 5v8c-1.21.91-2 2.37-2 4 0 2.76 2.24 5 5 5s5-2.24 5-5c0-1.63-.79-3.09-2-4zm-4-8c0-.55.45-1 1-1s1 .45 1 1h-1v1h1v2h-1v1h1v2h-2V5z"/></svg>';

const KETTLE_COMMANDS = [
  {field:'off_mode',  icon:ICON_POWER, label:'Выключить',  hint:'Команда «выключи» из Сбера',   required:true,  guesses:['off','выкл','stop','standby']},
  {field:'boil_mode', icon:ICON_BOIL,  label:'Вскипятить', hint:'Команда «вскипяти» из Сбера', required:true,  guesses:['boil','кипят','вскип']},
  {field:'heat_mode', icon:ICON_HEAT,  label:'Нагреть',    hint:'Команда «нагрей» из Сбера (до заданной температуры). Если у чайника нет отдельного режима нагрева — оставьте «Не поддерживается», будет использован режим кипячения.', required:false, guesses:['heat','warm','нагрев','подогрев']},
];

function guessKettleMode(opList, guesses){
  if(!opList||!opList.length)return'';
  for(const g of guesses){
    const hit=opList.find(v=>String(v).toLowerCase().includes(g));
    if(hit)return hit;
  }
  return'';
}

function renderKettleModes(entity){
  const opList = entity?(entity.operation_list||[]):[];
  if(!opList.length){
    return `<div style="margin-top:16px;padding:10px 12px;background:color-mix(in srgb, var(--bg) 85%, var(--danger) 15%);border:1px solid var(--danger);border-radius:7px;font-size:12px;color:var(--text)">
      ⚠️ У выбранной сущности не найден атрибут <b>operation_list</b> — сопоставить команды невозможно.
      Проверьте, что сущность поддерживает режимы работы (water_heater.operation_list).
    </div>`;
  }
  // Автоматически подставляем первое совпадение по эвристике при первом рендере
  KETTLE_COMMANDS.forEach(cmd=>{
    if(wData[cmd.field]===undefined){
      wData[cmd.field]=guessKettleMode(opList,cmd.guesses);
    }
  });
  return `<div style="margin-top:18px">
    <div class="fg"><label>Соответствие команд Сбера режимам чайника:</label>
      <div style="font-size:11px;color:var(--muted);margin-top:3px">
        Из Сбера может прийти только три команды: вскипятить, нагреть и выключить.
        Укажите, каким значениям operation_list вашего чайника они соответствуют.
      </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:10px;margin-top:10px">
      ${KETTLE_COMMANDS.map(cmd=>{
        const val = wData[cmd.field]||'';
        const options = [`<option value="">${cmd.required?'— выберите —':'— не поддерживается —'}</option>`]
          .concat(opList.map(v=>`<option value="${esc(v)}" ${val===v?'selected':''}>${esc(v)}</option>`)).join('');
        return `<div style="padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:var(--card)">
          <div style="font-size:13px;font-weight:600;color:var(--text);display:flex;align-items:center;gap:6px">${cmd.icon}${cmd.label}${cmd.required?' <span style=\"color:var(--danger)\">*</span>':''}</div>
          <select style="width:100%;box-sizing:border-box;margin-top:6px;padding:7px 8px;border:1px solid var(--border);border-radius:6px;font-size:12px;background:var(--card);color:var(--text)"
            onchange="setKettleMode('${cmd.field}',this.value)">${options}</select>
          <div style="font-size:11px;color:var(--muted);margin-top:5px">${cmd.hint}</div>
        </div>`;
      }).join('')}
    </div>
  </div>`;
}

function setKettleMode(field,val){
  wData[field]=val;
}

function pickKettleEntity(eid,name,area){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  // Сбрасываем сопоставление команд — оно зависит от конкретной сущности
  delete wData.off_mode;delete wData.boil_mode;delete wData.heat_mode;
  document.getElementById('wizContent').innerHTML=renderStep2Kettle();
}

function openKettleWater(){
  const el=document.getElementById('kettleWaterPicker');
  el.style.display=el.style.display==='none'?'':'none';
  renderKettleWaterList('');
}
function renderKettleWaterList(q){
  q=(q||'').toLowerCase();
  const list=haWaterSensors.filter(s=>!q||(s.entity_id+s.friendly_name+s.device_class).toLowerCase().includes(q));
  const el=document.getElementById('kettleWaterList');if(!el)return;
  el.innerHTML=list.length
    ?list.map(s=>`<div class="p-item ${wData.water_entity===s.entity_id?'sel':''}" onclick="pickKettleWater('${esc(s.entity_id)}','${esc(s.friendly_name)}')">
      <span class="dom-badge">${esc(s.device_class||'—')}</span><span class="p-area">${esc(s.area||'—')}</span>
      <span class="p-name">${esc(s.friendly_name)}</span><span class="p-eid">${esc(s.entity_id)}</span></div>`).join('')
    :'<div class="p-empty">Нет сенсоров</div>';
}
function pickKettleWater(eid,name){
  wData.water_entity=eid;wData.water_entity_name=name;
  document.getElementById('kettleWaterPicker').style.display='none';
  document.getElementById('wizContent').innerHTML=renderStep2Kettle();
}
function openKettleWaterLow(){
  // Используем haSensors с device_class moisture или все binary_sensor
  const list=haWaterSensors.filter(s=>s.domain==='binary_sensor'||s.device_class==='moisture');
  const el=document.getElementById('kettleWaterLowList');
  const wrap=document.getElementById('kettleWaterLowPicker');
  if(!el){wrap.style.display='none';return;}
  wrap.style.display=wrap.style.display==='none'?'':'none';
  el.innerHTML=list.length
    ?list.map(s=>`<div class="p-item ${wData.water_low_entity===s.entity_id?'sel':''}" onclick="pickKettleWaterLow('${esc(s.entity_id)}','${esc(s.friendly_name)}')">
      <span class="dom-badge">${esc(s.device_class||'—')}</span><span class="p-name">${esc(s.friendly_name)}</span><span class="p-eid">${esc(s.entity_id)}</span></div>`).join('')
    :'<div class="p-empty">Нет binary_sensor</div>';
}
function pickKettleWaterLow(eid,name){
  wData.water_low_entity=eid;wData.water_low_entity_name=name;
  document.getElementById('kettleWaterLowPicker').style.display='none';
  document.getElementById('wizContent').innerHTML=renderStep2Kettle();
}


// ═══════════════════════════════════════════════════════════
// WIZARD: ДАТЧИК ОТКРЫТИЯ (sensor_door)
// ═══════════════════════════════════════════════════════════

async function fetchDoor(){
  if(haDoor.length)return;
  try{haDoor=(await api('/api/sber_mqtt/ha_entities/sensor_door')).entities||[];}catch(e){}
}

function renderStep2SensorDoor(){
  if(!haDoor.length)return renderLoading();
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите датчик открытия:</label></div>
    <div class="picker" id="doorItems"><div class="psearch"><span style="color:var(--muted)">🔍</span>
      <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
        oninput="sFilter=this.value;document.getElementById('doorItems').querySelector('.plist').innerHTML=doorItems()"/></div>
      <div class="plist">${doorItems()}</div></div>`;
}
function doorItems(){
  const q=(sFilter||'').toLowerCase();
  const list=haDoor.filter(e=>(e.friendly_name||'').toLowerCase().includes(q)||e.entity_id.includes(q));
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''}" onclick="pickDoorEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area||'')}')">
    <span class="p-name">${esc(e.friendly_name)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickDoorEntity(eid,name,area){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  // Автоподбор battery
  if(!wData.battery_entity){const bat=haSensors.find(s=>s.device_class==='battery'&&s.entity_id.includes(eid.split('.')[1]));if(bat){wData.battery_entity=bat.entity_id;wData.battery_entity_name=bat.friendly_name;}}
  document.getElementById('wizContent').innerHTML=renderStep2SensorDoor();
}

// ═══════════════════════════════════════════════════════════
// WIZARD: ДАТЧИК КАЧЕСТВА ВОЗДУХА (sensor_air)
// ═══════════════════════════════════════════════════════════

function renderStep2SensorAir(){
  if(!haSensors.length)return'<div class="p-empty">Сенсоры не загружены. Перезагрузите HA и страницу.</div>';
  const slots=[{k:'temperature_entity',l:'🌡️ Температура',c:'temperature'},
              {k:'humidity_entity',l:'💧 Влажность',c:'humidity'},
              {k:'co2_entity',l:'🫧 CO₂',c:'carbon_dioxide'},
              {k:'pm25_entity',l:'🔴 PM2.5',c:'pm25'},
              {k:'tvoc_entity',l:'🧪 TVOC',c:'volatile_organic_compounds'},
              {k:'battery_entity',l:'🔋 Заряд батареи',c:'battery'},
              {k:'signal_entity',l:'📶 Сила сигнала',c:'signal_strength'}];
  const html=slots.map(f=>{
    const val=wData[f.k];const entity=val?haSensors.find(x=>x.entity_id===val):null;
    return `<div class="sf"><label>${f.l}</label>
      <button class="sf-btn ${val?'filled':''}" onclick="openSP('${f.k}')">
        <span>${val?(entity?.friendly_name||val):'Выбрать сенсор…'}</span><span>${val?'✓':'▾'}</span></button>
      ${val?`<div class="sf-sub">${esc(val)} <button class="sf-clr" onclick="clearSP('${f.k}')">✕</button></div>`:''}</div>`;
  }).join('');
  return `<div style="margin-bottom:12px;font-size:12px;color:var(--muted)">Все поля опциональны.</div>
    <div class="sg">${html}</div>
    <div id="spWrap" class="sp-wrap" style="display:none">
      <div class="picker">
        <div class="psearch"><span style="color:var(--muted)">🔍</span>
          <input id="spInput" type="text" placeholder="Поиск…" oninput="renderSPList(this.value)"/>
          <button class="clr" onclick="spInput.value='';renderSPList('')">✕</button></div>
        <div class="p-head"><div>Класс</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
        <div class="p-list" id="spList"></div></div></div>`;
}

// ═══════════════════════════════════════════════════════════
// WIZARD: ТЕРМОГОЛОВКА (hvac_radiator)
// ═══════════════════════════════════════════════════════════

async function fetchRadiator(){
  if(haRadiator.length)return;
  try{haRadiator=(await api('/api/sber_mqtt/ha_entities/hvac_radiator')).entities||[];}catch(e){}
}

function renderStep2Radiator(){
  if(!haRadiator.length)return renderLoading();
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите климатическую сущность:</label></div>
    <div class="picker" id="radItems"><div class="psearch"><span style="color:var(--muted)">🔍</span>
      <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
        oninput="sFilter=this.value;document.getElementById('radItems').querySelector('.plist').innerHTML=radiatorItems()"/></div>
      <div class="plist">${radiatorItems()}</div></div>`;
}
function radiatorItems(){
  const q=(sFilter||'').toLowerCase();
  const list=haRadiator.filter(e=>(e.friendly_name||'').toLowerCase().includes(q)||e.entity_id.includes(q));
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''}" onclick="pickRadiatorEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area||'')}')">
    <span class="p-name">${esc(e.friendly_name)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickRadiatorEntity(eid,name,area){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  document.getElementById('wizContent').innerHTML=renderStep2Radiator();
}

// ═══════════════════════════════════════════════════════════
// WIZARD: БРИЗЕР (hvac_fan)
// ═══════════════════════════════════════════════════════════

async function fetchFan(){
  if(haFan.length)return;
  try{haFan=(await api('/api/sber_mqtt/ha_entities/hvac_fan')).entities||[];}catch(e){}
}

function renderStep2Fan(){
  if(!haFan.length)return renderLoading();
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите вентилятор:</label></div>
    <div class="picker" id="fanItems"><div class="psearch"><span style="color:var(--muted)">🔍</span>
      <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
        oninput="sFilter=this.value;document.getElementById('fanItems').querySelector('.plist').innerHTML=fanItems()"/></div>
      <div class="plist">${fanItems()}</div></div>`;
}
function fanItems(){
  const q=(sFilter||'').toLowerCase();
  const list=haFan.filter(e=>(e.friendly_name||'').toLowerCase().includes(q)||e.entity_id.includes(q));
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''}" onclick="pickFanEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area||'')}')">
    <span class="dom-badge">${esc(e.domain)}</span><span class="p-name">${esc(e.friendly_name)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickFanEntity(eid,name,area){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  document.getElementById('wizContent').innerHTML=renderStep2Fan();
}

// ═══════════════════════════════════════════════════════════
// WIZARD: ДОМОФОН (intercom)
// ═══════════════════════════════════════════════════════════

async function fetchIntercom(){
  if(haIntercom.length)return;
  try{haIntercom=(await api('/api/sber_mqtt/ha_entities/intercom')).entities||[];}catch(e){}
}

function renderStep2Intercom(){
  if(!haIntercom.length)return renderLoading();
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите кнопку открытия двери:</label></div>
    <div class="picker" id="intercomItems"><div class="psearch"><span style="color:var(--muted)">🔍</span>
      <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
        oninput="sFilter=this.value;document.getElementById('intercomItems').querySelector('.plist').innerHTML=intercomItems()"/></div>
      <div class="plist">${intercomItems()}</div></div>
    ${wData.entity_id?`<div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border,#e0e0e0)">
      ${(()=>{const val=wData.incoming_call_entity;const e=val?haSensors.find(x=>x.entity_id===val):null;
        return `<div class="sf"><label>📞 Датчик вызова (опционально)</label>
          <button class="sf-btn ${val?'filled':''}" onclick="openSP('incoming_call_entity')">
            <span>${val?(e?.friendly_name||val):'Выбрать binary_sensor…'}</span><span>${val?'✓':'▾'}</span></button>
          ${val?`<div class="sf-sub">${esc(val)} <button class="sf-clr" onclick="delete wData.incoming_call_entity;delete wData.incoming_call_entity_name;document.getElementById('wizContent').innerHTML=renderStep2Intercom()">✕</button></div>`:''}</div>`;
      })()}
      <div id="spWrap" class="sp-wrap" style="display:none">
        <div class="picker"><div class="psearch"><span style="color:var(--muted)">🔍</span>
          <input id="spInput" type="text" placeholder="Поиск…" oninput="renderSPList(this.value)"/>
          <button class="clr" onclick="spInput.value='';renderSPList('')">✕</button></div>
        <div class="p-head"><div>Класс</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
        <div class="p-list" id="spList"></div></div></div>
    </div>`:''}`;
}
function intercomItems(){
  const q=(sFilter||'').toLowerCase();
  const list=haIntercom.filter(e=>(e.friendly_name||'').toLowerCase().includes(q)||e.entity_id.includes(q));
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''}" onclick="pickIntercomEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area||'')}')">
    <span class="dom-badge">${esc(e.domain)}</span><span class="p-name">${esc(e.friendly_name)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickIntercomEntity(eid,name,area){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  document.getElementById('wizContent').innerHTML=renderStep2Intercom();
}


// ═══════════════════════════════════════════════════════════
// WIZARD: ДАТЧИК ДВИЖЕНИЯ (sensor_pir)
// ═══════════════════════════════════════════════════════════

async function fetchPir(){
  if(haPir.length)return;
  try{haPir=(await api('/api/sber_mqtt/ha_entities/sensor_pir')).entities||[];}catch(e){}
}

function renderStep2Pir(){
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите датчик движения:</label></div>
    <div class="picker"><div class="psearch"><span style="color:var(--muted)">🔍</span>
      <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
        oninput="sFilter=this.value;document.getElementById('pirlist').innerHTML=pirItems()"/></div>
      <div class="plist" id="pirlist">${pirItems()}</div></div>`;
}
function pirItems(){
  const q=(sFilter||'').toLowerCase();
  const list=haPir.filter(e=>(e.friendly_name||'').toLowerCase().includes(q)||e.entity_id.includes(q));
  if(!list.length)return'<div class="p-empty">Датчики не найдены</div>';
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''}" onclick="pickPirEntity('${esc(e.entity_id)}','${esc(e.friendly_name)}','${esc(e.area||'')}')">
    <span class="p-name">${esc(e.friendly_name)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickPirEntity(eid,name,area){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  document.getElementById('wizContent').innerHTML=renderStep2Pir();
}


// ═══════════════════════════════════════════════════════════
// WIZARD: ТЕЛЕВИЗОР
// ═══════════════════════════════════════════════════════════
let haTV=[];
async function fetchTV(){
  if(haTV.length)return;
  try{haTV=(await api('/api/sber_mqtt/ha_entities/tv')).entities||[];}
  catch(e){toast('Ошибка загрузки телевизоров','err');}
}

function tvFeatureBadges(f){
  f=f||{};
  const parts=[];
  if(f.supports_mute)parts.push('🔇 mute');
  if(f.supports_volume_set)parts.push('🔊 громкость');
  if(f.supports_volume_step)parts.push('➕➖ громче/тише');
  return parts.length?parts.join(' · '):'только вкл/выкл';
}

function renderStep2TV(){
  const sel=wData.entity_id;
  return `<div class="fg" style="margin-bottom:10px"><label>Выберите телевизор (media_player):</label>
    <div style="font-size:11px;color:var(--muted);margin-top:3px">Доступны включение/выключение; громкость и mute — если их поддерживает сущность</div></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('tvlist').innerHTML=tvItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('tvlist').innerHTML=tvItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" id="tvlist">${tvItems()}</div>
    </div>
    ${sel?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(sel)}</b><br>Функции в Салюте: вкл/выкл · ${esc(tvFeatureBadges(wData.tv_features))}</div>`:''}`;
}
function tvItems(){
  const list=haTV.filter(e=>!sFilter||(e.area+e.domain+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Нет подходящих сущностей</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickTVEntity('${esc(e.entity_id)}')">
    <span class="dom-badge">${esc(e.domain)}</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickTVEntity(eid){
  const e=haTV.find(x=>x.entity_id===eid);
  if(!e)return;
  wData.entity_id=e.entity_id;wData.entity_name=e.friendly_name;wData.entity_area=e.area;
  wData.tv_features=e.tv_features||{};
  document.getElementById('wizContent').innerHTML=renderStep2TV();
}


// ═══════════════════════════════════════════════════════════
// WIZARD: АВТОМАТИЗАЦИЯ (показывается как relay)
// ═══════════════════════════════════════════════════════════

function renderStep2Automation(){
  const automations=haRelay.filter(e=>e.domain==='automation');
  if(!automations.length)return'<div class="p-empty">Нет automation сущностей</div>';
  return '<div class="fg" style="margin-bottom:10px"><label>Выберите автоматизацию:</label></div><div class="picker"><div class="psearch"><span style="color:var(--muted)">🔍</span><input type="text" placeholder="Поиск…" value="'+esc(sFilter)+'" oninput="sFilter=this.value;document.getElementById(\'autolist\').innerHTML=autoItems()"/></div><div class="p-head" style="grid-template-columns:250px minmax(100px,150px) 1fr"><div>Имя</div><div>Добавлено</div><div>Entity ID</div></div><div class="plist" id="autolist">'+autoItems()+'</div></div>';
}
function autoItems(){
  var q=(sFilter||'').toLowerCase();
  var list=haRelay.filter(function(e){return e.domain==='automation'&&(e.friendly_name||'').toLowerCase().indexOf(q)>=0;});
  return list.map(function(e){return'<div class="p-item '+(wData.entity_id===e.entity_id?'sel':'')+' '+usedCls(e.entity_id)+'" onclick="pickAutoEntity(\''+esc(e.entity_id)+'\',\''+esc(e.friendly_name)+'\',\''+esc(e.area||'')+'\')" style="grid-template-columns:250px minmax(100px,150px) 1fr"><span class="p-name">'+esc(e.friendly_name)+'</span><span style="display:flex;flex-direction:column;gap:2px;align-items:flex-start">'+autoBadge(e.entity_id)+'</span><span class="p-eid" title="'+esc(e.entity_id)+'">'+esc(e.entity_id)+'</span></div>';}).join('');
}
function pickAutoEntity(eid,name,area){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  document.getElementById('wizContent').innerHTML=renderStep2Automation();
}


// ═══════════════════════════════════════════════════════════
// WIZARD: СЦЕНАРИЙ / СКРИПТ (script → relay)
// ═══════════════════════════════════════════════════════════

function renderStep2Script(){
  var scripts=haRelay.filter(function(e){return e.domain==='script';});
  if(!scripts.length)return'<div class="p-empty">Нет script сущностей</div>';
  return '<div class="fg" style="margin-bottom:10px"><label>Выберите скрипт:</label></div><div class="picker"><div class="psearch"><span style="color:var(--muted)">🔍</span><input type="text" placeholder="Поиск…" value="'+esc(sFilter)+'" oninput="sFilter=this.value;document.getElementById(\'scriptlist\').innerHTML=scriptItems()"/></div><div class="p-head" style="grid-template-columns:1fr 1fr"><div>Имя</div><div>Entity ID</div></div><div class="plist" id="scriptlist">'+scriptItems()+'</div></div>';
}
function scriptItems(){
  var q=(sFilter||'').toLowerCase();
  var list=haRelay.filter(function(e){return e.domain==='script'&&(e.friendly_name||'').toLowerCase().indexOf(q)>=0;});
  return list.map(function(e){return'<div class="p-item '+(wData.entity_id===e.entity_id?'sel':'')+' '+usedCls(e.entity_id)+'" onclick="pickScriptEntity(\''+esc(e.entity_id)+'\',\''+esc(e.friendly_name)+'\',\''+esc(e.area||'')+'\')" style="grid-template-columns:1fr 1fr"><span class="p-name">'+esc(e.friendly_name)+usedBadge(e.entity_id)+'</span><span class="p-eid" title="'+esc(e.entity_id)+'">'+esc(e.entity_id)+'</span></div>';}).join('');
}
function pickScriptEntity(eid,name,area){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  document.getElementById('wizContent').innerHTML=renderStep2Script();
}


// ═══════════════════════════════════════════════════════════
// WIZARD: КНОПКА СОБЫТИЙ (event → button_event)
// ═══════════════════════════════════════════════════════════

function renderStep2EventButton(){
  if(!haEventBtns.length)return renderLoading();
  return '<div class="fg" style="margin-bottom:10px"><label>Выберите кнопку:</label></div><div class="picker"><div class="psearch"><span style="color:var(--muted)">🔍</span><input type="text" placeholder="Поиск…" value="'+esc(sFilter)+'" oninput="sFilter=this.value;document.getElementById(\'eventbtnlist\').innerHTML=eventBtnItems()"/></div><div class="plist" id="eventbtnlist">'+eventBtnItems()+'</div></div>';
}
function eventBtnItems(){
  var q=(sFilter||'').toLowerCase();
  var list=haEventBtns.filter(function(e){return(e.friendly_name||'').toLowerCase().indexOf(q)>=0||e.entity_id.indexOf(q)>=0;});
  return list.map(function(e){return'<div class="p-item '+(wData.entity_id===e.entity_id?'sel':'')+'" onclick="pickEventBtn(\''+esc(e.entity_id)+'\',\''+esc(e.friendly_name)+'\',\''+esc(e.area||'')+'\')"><span class="dom-badge">'+esc(e.domain)+'</span><span class="p-name">'+esc(e.friendly_name)+'</span><span class="p-eid">'+esc(e.entity_id)+'</span></div>';}).join('');
}
function pickEventBtn(eid,name,area){
  wData.entity_id=eid;wData.entity_name=name;wData.entity_area=area;
  if(!wData.event_type)wData.event_type=eid.split('.')[1]+'_action';
  document.getElementById('wizContent').innerHTML=renderStep2EventButton();
}

function renderEventButtonStep3(){
  var am=wData.action_map||{};
  return '<div class="fg"><label>Тип события HA</label><input type="text" value="'+esc(wData.event_type||'')+'" oninput="wData.event_type=this.value"/><div class="hint">Обычно: имя_кнопки_action</div></div>'+
    '<div class="fg"><label>Маппинг action → button_event</label><div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:4px"><div style="font-size:10px;color:var(--muted)">action в HA</div><div style="font-size:10px;color:var(--muted)">button_event в Сбер</div></div>'+
    ['single','double','triple','long'].map(function(a){
      return '<div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:4px"><span style="font-size:12px">'+a+'</span><select onchange="var m=wData.action_map||{};wData.action_map=m;m[\''+a+'\']=this.value||undefined" style="font-size:12px"><option value="">—</option><option value="click"'+((am[a]||'')==='click'?' selected':'')+'>click</option><option value="double_click"'+((am[a]||'')==='double_click'?' selected':'')+'>double_click</option><option value="long_press"'+((am[a]||'')==='long_press'?' selected':'')+'>single + long</option></select></div>';
    }).join('')+'</div>';
}
// WIZARD: ОЧИСТИТЕЛЬ ВОЗДУХА
// ═══════════════════════════════════════════════════════════
// В HA очиститель — набор отдельных сущностей (switch, select, sensor).
// Пользователь выбирает сущность питания, остальные функции Сбера
// сопоставляются сущностями того же устройства (подбираются автоматически).
let haAP={power:[],controls:[],sensors:[]};
async function fetchAP(){
  if(haAP.power.length)return;
  try{haAP=await api('/api/sber_mqtt/ha_entities/air_purifier');}
  catch(e){toast('Ошибка загрузки сущностей очистителя','err');}
}

const AP_SELECT_DOMAINS=['select','input_select'];
const AP_SPEEDS=[
  {key:'auto',  label:'Авто',    guess:['auto','авто']},
  {key:'quiet', label:'Тихая',   guess:['quiet','silent','тих','бесшум']},
  {key:'low',   label:'Низкая',  guess:['low','низк','min']},
  {key:'medium',label:'Средняя', guess:['medium','mid','средн']},
  {key:'high',  label:'Высокая', guess:['high','выс','max']},
  {key:'turbo', label:'Турбо',   guess:['turbo','турбо','boost']},
];
const AP_BOOL_SLOTS=[
  {key:'night_mode',    icon:'🌙', label:'Ночной режим',    re:/night|sleep|ноч|сон/,
    onG:['sleep','night','сон','ноч'], offG:['auto','авто','normal','standard','off','выкл']},
  {key:'ionization',    icon:'⚡', label:'Ионизация',       re:/ioniz|иониз|(^|[_\s.])ion($|[_\s])/,
    onG:['on','вкл','enable'], offG:['off','выкл','disable']},
  {key:'aromatization', icon:'🌸', label:'Ароматизация',    re:/aroma|fragran|ароматиз/,
    onG:['on','вкл','enable'], offG:['off','выкл','disable']},
  {key:'decontaminate', icon:'🧪', label:'Обеззараживание', re:/(^|[_\s.])uv($|[_\s])|ultraviolet|steril|disinfect|decontam|germ|обеззараж|(^|[_\s.])уф($|[_\s])/,
    onG:['on','вкл','enable'], offG:['off','выкл','disable']},
];
const AP_REPLACE_SLOTS=[
  {key:'replace_filter',    icon:'🔧', label:'Замена фильтра',    re:/filter|фильтр/},
  {key:'replace_ionizator', icon:'🔧', label:'Замена ионизатора', re:/ioniz|иониз/},
];
// Все атрибуты устройства, которые мастер отправляет на сервер
const AP_ATTR_KEYS=['speed_entity','speed_map','online_entity',
  ...AP_BOOL_SLOTS.flatMap(s=>[s.key+'_entity',s.key+'_on_option',s.key+'_off_option']),
  ...AP_REPLACE_SLOTS.flatMap(s=>[s.key+'_entity',s.key+'_threshold',s.key+'_cmp']),
];

const AP_CARD_STYLE='padding:10px 12px;border:1px solid var(--border);border-radius:8px;background:var(--card)';
const AP_SEL_STYLE='width:100%;box-sizing:border-box;margin-top:6px;padding:7px 8px;border:1px solid var(--border);border-radius:6px;font-size:12px;background:var(--card);color:var(--text)';
const AP_SEL_INLINE='width:100%;box-sizing:border-box;padding:6px 8px;border:1px solid var(--border);border-radius:6px;font-size:12px;background:var(--card);color:var(--text)';

// ── Поиск и подбор ──────────────────────────────────────────
function apFind(eid){
  return haAP.power.find(e=>e.entity_id===eid)||haAP.controls.find(e=>e.entity_id===eid)||haAP.sensors.find(e=>e.entity_id===eid)||null;
}
function apDevId(){const e=apFind(wData.entity_id);return e?e.device_id:'';}

// Первое подходящее значение из options: сначала точное совпадение, затем по вхождению
function apPick(options,guesses,taken){
  const free=(options||[]).filter(o=>!(taken||[]).includes(o));
  for(const g of guesses){const h=free.find(o=>String(o).toLowerCase()===g);if(h!==undefined)return h;}
  for(const g of guesses){const h=free.find(o=>String(o).toLowerCase().includes(g));if(h!==undefined)return h;}
  return '';
}
function apGuessSpeedMap(options){
  const map={},taken=[];
  for(const s of AP_SPEEDS){const o=apPick(options,s.guess,taken);map[s.key]=o;if(o)taken.push(o);}
  return map;
}
function apGuessBoolOptions(options,slot){
  const on=apPick(options,slot.onG,[]);
  let off=apPick(options,slot.offG,[on]);
  if(on&&!off)off=(options||[]).find(o=>o!==on)||'';
  return {on,off};
}
function apDefaultThreshold(e){
  const u=String(e.unit||'').toLowerCase();
  if(u==='%')return 10;
  if(['h','hr','hrs','ч','час','hours'].includes(u))return 100;
  if(['d','д','days','дн'].includes(u))return 5;
  return '';
}
function apInitBool(slot,eid){
  const k=slot.key;
  wData[k+'_entity']=eid;delete wData[k+'_on_option'];delete wData[k+'_off_option'];
  const e=apFind(eid);
  if(e&&AP_SELECT_DOMAINS.includes(e.domain)){
    const g=apGuessBoolOptions(e.options||[],slot);
    wData[k+'_on_option']=g.on;wData[k+'_off_option']=g.off;
  }
}
function apInitReplace(slot,eid){
  const k=slot.key;
  wData[k+'_entity']=eid;delete wData[k+'_threshold'];delete wData[k+'_cmp'];
  const e=apFind(eid);
  if(e&&e.domain==='sensor'){
    wData[k+'_cmp']='le';
    const t=apDefaultThreshold(e);if(t!=='')wData[k+'_threshold']=t;
  }
}

// Автоподбор остальных функций среди сущностей того же устройства HA
function apAutofill(){
  AP_ATTR_KEYS.forEach(k=>delete wData[k]);
  const dev=apDevId();if(!dev)return;
  const txt=e=>(e.entity_id+' '+e.friendly_name).toLowerCase();
  const sameC=haAP.controls.filter(e=>e.device_id===dev&&e.entity_id!==wData.entity_id);
  const sameS=haAP.sensors.filter(e=>e.device_id===dev);
  const taken=new Set();

  // Скорость: select, у которого опции похожи на скорости (минимум два совпадения)
  let best=null,bestN=1;
  for(const e of sameC.filter(x=>AP_SELECT_DOMAINS.includes(x.domain))){
    const n=Object.values(apGuessSpeedMap(e.options||[])).filter(Boolean).length;
    if(n>bestN){best=e;bestN=n;}
  }
  if(best){wData.speed_entity=best.entity_id;wData.speed_map=apGuessSpeedMap(best.options||[]);taken.add(best.entity_id);}

  // Булевые режимы
  for(const slot of AP_BOOL_SLOTS){
    let found=null;
    if(slot.key==='night_mode'){  // select с опцией «Sleep / Night / Сон»
      found=sameC.find(e=>!taken.has(e.entity_id)&&AP_SELECT_DOMAINS.includes(e.domain)&&apPick(e.options||[],slot.onG,[]));
    }
    if(!found)found=sameC.find(e=>!taken.has(e.entity_id)&&slot.re.test(txt(e)));
    if(found){apInitBool(slot,found.entity_id);taken.add(found.entity_id);}
  }
  // Замена фильтра / ионизатора
  for(const slot of AP_REPLACE_SLOTS){
    const found=sameS.find(e=>!taken.has(e.entity_id)&&slot.re.test(txt(e)));
    if(found){apInitReplace(slot,found.entity_id);taken.add(found.entity_id);}
  }
  // Доступность
  const online=sameS.find(e=>e.domain==='binary_sensor'&&(e.dc==='connectivity'||/online|connect|available|в сети/.test(txt(e))));
  if(online)wData.online_entity=online.entity_id;
}

// ── Выбор сущности питания ──────────────────────────────────
function apPowerItems(){
  const list=haAP.power.filter(e=>!sFilter||(e.area+e.domain+e.entity_id+e.friendly_name).toLowerCase().includes(sFilter.toLowerCase()));
  if(!list.length)return`<div class="p-empty">Нет подходящих сущностей (switch, input_boolean, fan)</div>`;
  return list.map(e=>`<div class="p-item ${wData.entity_id===e.entity_id?'sel':''} ${usedCls(e.entity_id)}" onclick="pickAPPower('${esc(e.entity_id)}')">
    <span class="dom-badge">${esc(e.domain)}</span><span class="p-area">${esc(e.area||'—')}</span>
    <span class="p-name">${esc(e.friendly_name)}${usedBadge(e.entity_id)}</span><span class="p-eid">${esc(e.entity_id)}</span></div>`).join('');
}
function pickAPPower(eid){
  const e=haAP.power.find(x=>x.entity_id===eid);if(!e)return;
  wData.entity_id=e.entity_id;wData.entity_name=e.friendly_name;wData.entity_area=e.area;
  apAutofill();
  document.getElementById('wizContent').innerHTML=renderStep2AirPurifier();
}

// ── Карточки функций ────────────────────────────────────────
function apTitle(icon,label,hint,req){
  return `<div style="font-size:13px;font-weight:600;color:var(--text)">${icon} ${label}${req?' <span style="color:var(--danger)">*</span>':''}</div>
    <div style="font-size:11px;color:var(--muted);margin-top:2px">${hint}</div>`;
}
function apEntitySelect(list,sel,onchange){
  const dev=apDevId();
  const mk=e=>`<option value="${esc(e.entity_id)}" ${sel===e.entity_id?'selected':''}>${esc(e.friendly_name)} — ${esc(e.entity_id)}</option>`;
  const same=list.filter(e=>dev&&e.device_id===dev),other=list.filter(e=>!(dev&&e.device_id===dev));
  return `<select style="${AP_SEL_STYLE}" onchange="${onchange}"><option value="">— не использовать —</option>`
    +(same.length?`<optgroup label="Это же устройство">${same.map(mk).join('')}</optgroup>`:'')
    +(other.length?`<optgroup label="Остальные сущности">${other.map(mk).join('')}</optgroup>`:'')+`</select>`;
}
function apOptSelect(options,val,onchange,emptyLabel,style){
  return `<select style="${style||AP_SEL_INLINE}" onchange="${onchange}"><option value="">${emptyLabel}</option>`
    +(options||[]).map(o=>`<option value="${esc(o)}" ${val===o?'selected':''}>${esc(o)}</option>`).join('')+`</select>`;
}

function apSpeedInner(){
  const eid=wData.speed_entity||'';const e=eid?apFind(eid):null;
  const list=haAP.controls.filter(x=>AP_SELECT_DOMAINS.includes(x.domain));
  let map='';
  if(e){
    const opts=e.options||[];
    map=opts.length?`<div style="font-size:11px;color:var(--muted);margin-top:8px">Какая опция выбирается для каждой скорости в Салюте:</div>`
      +AP_SPEEDS.map(s=>`<div style="display:flex;align-items:center;gap:8px;margin-top:5px">
        <span style="width:84px;font-size:12px;flex-shrink:0">${s.label}</span>
        <div style="flex:1">${apOptSelect(opts,(wData.speed_map||{})[s.key]||'',`apSetSpeed('${s.key}',this.value)`,'— не поддерживается —')}</div></div>`).join('')
      :`<div style="font-size:11px;color:var(--danger);margin-top:8px">⚠️ У сущности нет списка options — сопоставить скорости невозможно.</div>`;
  }
  return apTitle('🌀','Скорость вентилятора','select / input_select · в Салюте: авто, тихая, низкая, средняя, высокая, турбо')
    +apEntitySelect(list,eid,`apSetSlot('speed','speed',this.value)`)+map;
}
function apBoolInner(slot){
  const k=slot.key,eid=wData[k+'_entity']||'';const e=eid?apFind(eid):null;
  let extra='';
  if(e&&AP_SELECT_DOMAINS.includes(e.domain)){
    const opts=e.options||[];
    extra=`<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px">
      <div><div style="font-size:11px;color:var(--muted);margin-bottom:3px">Включено = опция</div>${apOptSelect(opts,wData[k+'_on_option']||'',`wData.${k}_on_option=this.value`,'— выберите —')}</div>
      <div><div style="font-size:11px;color:var(--muted);margin-bottom:3px">Выключено = опция</div>${apOptSelect(opts,wData[k+'_off_option']||'',`wData.${k}_off_option=this.value`,'— выберите —')}</div></div>`;
  }
  return apTitle(slot.icon,slot.label,'switch / input_boolean, либо select — тогда укажите, какие опции означают «вкл» и «выкл»')
    +apEntitySelect(haAP.controls,eid,`apSetSlot('bool','${k}',this.value)`)+extra;
}
function apReplaceInner(slot){
  const k=slot.key,eid=wData[k+'_entity']||'';const e=eid?apFind(eid):null;
  let extra='';
  if(e&&e.domain==='sensor'){
    const cmp=wData[k+'_cmp']==='ge'?'ge':'le';
    const thr=wData[k+'_threshold']===undefined?'':wData[k+'_threshold'];
    extra=`<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px">
      <span style="font-size:12px">Менять, когда значение</span>
      <select style="${AP_SEL_INLINE};width:auto" onchange="wData.${k}_cmp=this.value">
        <option value="le" ${cmp==='le'?'selected':''}>≤ порога (остаток ресурса)</option>
        <option value="ge" ${cmp==='ge'?'selected':''}>≥ порога (наработка)</option></select>
      <input type="number" step="any" placeholder="порог" value="${esc(thr)}" oninput="wData.${k}_threshold=this.value"
        style="${AP_SEL_INLINE};width:90px"/>
      <span style="font-size:12px;color:var(--muted)">${esc(e.unit||'')}</span></div>
      <div style="font-size:11px;color:var(--muted);margin-top:5px">Сейчас: <b>${esc(e.state||'—')}</b> ${esc(e.unit||'')}</div>`;
  }
  return apTitle(slot.icon,slot.label,'binary_sensor (on = менять) либо числовой sensor с порогом · только отображение в Салюте')
    +apEntitySelect(haAP.sensors.filter(x=>x.domain==='binary_sensor'||x.domain==='sensor'),eid,`apSetSlot('replace','${k}',this.value)`)+extra;
}
function apOnlineInner(){
  return apTitle('📶','Доступность','binary_sensor · если выключен — в Салюте очиститель «не в сети». Без него всегда «в сети»')
    +apEntitySelect(haAP.sensors.filter(x=>x.domain==='binary_sensor'),wData.online_entity||'',`apSetSlot('online','online',this.value)`);
}
function apCardInner(id){
  if(id==='speed')return apSpeedInner();
  const b=AP_BOOL_SLOTS.find(s=>s.key===id);if(b)return apBoolInner(b);
  const r=AP_REPLACE_SLOTS.find(s=>s.key===id);if(r)return apReplaceInner(r);
  if(id==='online')return apOnlineInner();
  return '';
}
function apSummary(){
  const f=['вкл/выкл'];
  if(wData.speed_entity)f.push('скорость');
  for(const s of AP_BOOL_SLOTS)if(wData[s.key+'_entity'])f.push(s.label.toLowerCase());
  for(const s of AP_REPLACE_SLOTS)if(wData[s.key+'_entity'])f.push(s.label.toLowerCase());
  if(wData.online_entity)f.push('доступность');
  return f.join(' · ');
}
function apRefresh(id){
  const el=document.getElementById('apc_'+id);if(el)el.innerHTML=apCardInner(id);
  const sm=document.getElementById('apSum');if(sm)sm.innerHTML=`Функции в Салюте: <b>${esc(apSummary())}</b>`;
}
function apSetSpeed(key,val){wData.speed_map=wData.speed_map||{};wData.speed_map[key]=val;}
function apSetSlot(kind,key,eid){
  if(kind==='speed'){
    delete wData.speed_entity;delete wData.speed_map;
    if(eid){const e=apFind(eid);wData.speed_entity=eid;wData.speed_map=apGuessSpeedMap(e?e.options||[]:[]);}
  }else if(kind==='bool'){
    const slot=AP_BOOL_SLOTS.find(s=>s.key===key);
    ['_entity','_on_option','_off_option'].forEach(sf=>delete wData[key+sf]);
    if(eid)apInitBool(slot,eid);
  }else if(kind==='replace'){
    const slot=AP_REPLACE_SLOTS.find(s=>s.key===key);
    ['_entity','_threshold','_cmp'].forEach(sf=>delete wData[key+sf]);
    if(eid)apInitReplace(slot,eid);
  }else if(kind==='online'){
    if(eid)wData.online_entity=eid;else delete wData.online_entity;
  }
  apRefresh(key);
}

function apValidate(){
  if(!wData.entity_id)return 'Выберите сущность включения очистителя';
  if(wData.speed_entity&&!Object.values(wData.speed_map||{}).some(Boolean))
    return 'Скорость: сопоставьте хотя бы одно значение с опцией';
  for(const s of AP_BOOL_SLOTS){
    const eid=wData[s.key+'_entity'];const e=eid?apFind(eid):null;
    if(e&&AP_SELECT_DOMAINS.includes(e.domain)){
      const on=wData[s.key+'_on_option'],off=wData[s.key+'_off_option'];
      if(!on||!off)return s.label+': выберите опции «включено» и «выключено»';
      if(on===off)return s.label+': опции «включено» и «выключено» должны различаться';
    }
  }
  for(const s of AP_REPLACE_SLOTS){
    const eid=wData[s.key+'_entity'];const e=eid?apFind(eid):null;
    const t=wData[s.key+'_threshold'];
    if(e&&e.domain==='sensor'&&(t===undefined||t===''||isNaN(Number(t))))return s.label+': укажите пороговое значение';
  }
  return '';
}

function renderStep2AirPurifier(){
  const sel=wData.entity_id;
  const ids=['speed',...AP_BOOL_SLOTS.map(s=>s.key),...AP_REPLACE_SLOTS.map(s=>s.key),'online'];
  return `<div class="fg" style="margin-bottom:10px"><label>1. Включение и выключение очистителя:</label>
    <div style="font-size:11px;color:var(--muted);margin-top:3px">switch, input_boolean или fan. После выбора остальные функции подбираются из сущностей этого же устройства.</div></div>
    <div class="picker">
      <div class="psearch"><span style="color:var(--muted)">🔍</span>
        <input type="text" placeholder="Поиск…" value="${esc(sFilter)}"
          oninput="sFilter=this.value;document.getElementById('aplist').innerHTML=apPowerItems()"/>
        <button class="clr" onclick="sFilter='';document.getElementById('aplist').innerHTML=apPowerItems()">✕</button>
      </div>
      <div class="p-head"><div>Домен</div><div>Комната</div><div>Имя</div><div>Entity ID</div></div>
      <div class="p-list" style="max-height:170px" id="aplist">${apPowerItems()}</div>
    </div>
    ${sel?`<div style="margin-top:10px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">✓ Выбрано: <b>${esc(sel)}</b></div>
    <div style="margin-top:18px">
      <div class="fg"><label>2. Сопоставление функций Сбера и сущностей HA:</label>
        <div style="font-size:11px;color:var(--muted);margin-top:3px">Всё, кроме включения, необязательно: функцию, для которой сущность не выбрана, Салют не покажет. Подобранное автоматически можно изменить.</div></div>
      <div style="display:flex;flex-direction:column;gap:10px;margin-top:10px">
        ${ids.map(id=>`<div id="apc_${id}" style="${AP_CARD_STYLE}">${apCardInner(id)}</div>`).join('')}
      </div>
      <div id="apSum" style="margin-top:12px;padding:8px 12px;background:var(--primary-lt);border-radius:7px;font-size:12px;color:var(--primary-dk)">Функции в Салюте: <b>${esc(apSummary())}</b></div>
    </div>`:''}`;
}
