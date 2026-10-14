(() => {
  'use strict';
  const modules = window.LMB_MODULES;
  const main = document.getElementById('main');
  const nav = document.getElementById('module-nav');
  const categories = ['Все', 'Диагностика', 'Терапия', 'Научная база', 'Здоровье'];
  const summaryCount = modules.filter(m => m.type === 'summary').length;
  const outlineCount = modules.length - summaryCount;
  const storageKey = 'lmb-academy-read-v1';
  let completed = new Set();
  try {const parsed=JSON.parse(localStorage.getItem(storageKey)||'[]');if(Array.isArray(parsed))completed=new Set(parsed.filter(id=>modules.some(m=>m.id===id&&m.type==='summary')));} catch {}
  let category = 'Все';
  let query = '';
  let currentRole = 'doctors';
  const esc = s => String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const iconPaths = {
    pellet:'<rect x="3" y="8" width="18" height="8" rx="4"/><path d="M12 8v8"/>',
    cell:'<ellipse cx="12" cy="12" rx="8.5" ry="6.5" transform="rotate(-30 12 12)"/><path d="M7 12c0-3 3-3 3 0s3 3 3 0 3-3 3 0"/>',
    drop:'<path d="M12 3C9 7 5 11 5 15a7 7 0 0 0 14 0c0-4-4-8-7-12Z"/><path d="M8 15a4 4 0 0 0 4 4"/>',
    chain:'<path d="M8 3c0 6 8 12 8 18M16 3c0 6-8 12-8 18M8.5 5h7M9.5 9h5M9.5 15h5M8.5 19h7"/>',
    balance:'<path d="M12 3v17M7 20h10M4 7h16M6 7l-3 6h6L6 7ZM18 7l-3 6h6l-3-6Z"/>',
    oxygen:'<circle cx="9" cy="13" r="5.5"/><circle cx="17" cy="6" r="3"/><path d="m13 9 2-1"/><path d="M17 15h4m-2-2v4"/>',
    branch:'<path d="M12 21V9M12 15l-6-4V6M12 12l6-4V3M12 9 8 5V2M12 18l6-4v-3"/><circle cx="6" cy="5" r="1"/><circle cx="18" cy="3" r="1"/>',
    orbit:'<circle cx="12" cy="12" r="3"/><ellipse cx="12" cy="12" rx="10" ry="5" transform="rotate(-40 12 12)"/><ellipse cx="12" cy="12" rx="10" ry="5" transform="rotate(40 12 12)"/>',
    male:'<circle cx="9" cy="15" r="6"/><path d="m13 11 8-8M15 3h6v6"/>',
    female:'<circle cx="12" cy="8" r="5"/><path d="M12 13v9M8 18h8"/>',
    search:'<circle cx="10" cy="10" r="6"/><path d="m15 15 5 5"/>',
    info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.1"/>'
  };
  const icon = name => '<svg viewBox="0 0 24 24" aria-hidden="true">'+(iconPaths[name]||iconPaths.cell)+'</svg>';
  const roles = active => `<div class="rolebar"><div class="roles" aria-label="Варианты обучения"><button data-role="doctors" class="${active==='doctors'?'selected':''}" aria-pressed="${active==='doctors'}">Для врачей</button><button data-role="admins" class="${active==='admins'?'selected':''}" aria-pressed="${active==='admins'}">Для администраторов <span class="role-next">следующий этап</span></button></div><span class="role-caption">Учимся понимать. Применяем осознанно.</span></div>`;
  const status = m => `<span class="status ${m.type==='outline'?'wait':''}">${m.type==='outline'?'Ожидает материалов':'Предварительное саммари'}</span>`;
  function updateNav(id) {
    document.getElementById('module-total').textContent = String(modules.length).padStart(2, '0');
    nav.innerHTML=modules.map(m=>`<a href="#module/${m.id}" class="${m.id===id?'active':''}" ${m.id===id?'aria-current="page"':''}><span>${m.n}</span><b>${esc(m.title)}</b></a>`).join('');
    document.getElementById('catalog-link').classList.toggle('active',!id);
  }
  function renderHome() {
    currentRole='doctors';updateNav();document.title='LMB Академия — обучение команды';
    main.innerHTML=roles('doctors')+`<section class="hero"><div><div class="eyebrow">КЛИНИЧЕСКОЕ МЫШЛЕНИЕ В ЛМБ</div><h1>Понимать глубже.<br><em>Применять точнее.</em></h1><p class="hero-text">Учебные саммари по инструментам клиники. Механизмы, клиническая логика и безопасность — в едином пространстве для команды.</p><div class="hero-meta"><div><strong>${String(modules.length).padStart(2,'0')}</strong><span>направлений</span></div><div><strong>${String(summaryCount).padStart(2,'0')}</strong><span>первых саммари</span></div><div><strong>02</strong><span>варианта обучения</span></div></div></div><aside class="hero-panel"><div class="panel-label">ПЕРВЫЙ ЭТАП</div><h2>Общая основа<br>для врачей клиники</h2><div class="route-step"><span>01</span>Понять научную основу</div><div class="route-step"><span>02</span>Разобрать инструменты</div><div class="route-step"><span>03</span>Связать с клинической задачей</div><a href="#module/aging">Начать с основ <span>↗</span></a></aside></section><section aria-labelledby="catalog-title"><div class="catalog-head"><div class="catalog-title"><h2 id="catalog-title">Инструменты ЛМБ</h2><p>${modules.length} направлений. Единая логика обучения.</p></div><div class="search">${icon('search')}<input type="search" id="search" aria-label="Поиск по направлениям и саммари" placeholder="Найти тему или инструмент" value="${esc(query)}"><button class="search-clear" id="clear-search" aria-label="Очистить поиск" ${query?'':'hidden'}>×</button></div></div><div class="filters" aria-label="Фильтр направлений">${categories.map(c=>`<button class="filter ${c===category?'selected':''}" data-category="${c}" aria-pressed="${c===category}">${c}</button>`).join('')}<span class="result-count" id="result-count"></span></div><div class="cards" id="cards"></div></section><div class="content-note">${icon('info')}<p>Первая редакция учебной базы: ${summaryCount} предварительных саммари и ${outlineCount} разделов со структурой будущего обучения. Объём каждого саммари зависит от найденных материалов и указан внутри. Полные лекции и исходные файлы на сайте не размещены.</p></div>`;
    renderCards();
    document.getElementById('search').addEventListener('input',e=>{query=e.target.value;renderCards();document.getElementById('clear-search').hidden=!query;});
    document.getElementById('clear-search').addEventListener('click',()=>{query='';document.getElementById('search').value='';document.getElementById('clear-search').hidden=true;renderCards();document.getElementById('search').focus();});
  }
  function renderCards() {
    const words=query.toLocaleLowerCase('ru').trim().split(/\s+/).filter(Boolean);
    const matches=modules.filter(m=>(category==='Все'||m.category===category)&&words.every(w=>(m.title+' '+m.lead+' '+m.keywords+' '+m.sections.flat().join(' ')).toLocaleLowerCase('ru').includes(w)));
    document.getElementById('cards').innerHTML=matches.length?matches.map(m=>`<a class="card" href="#module/${m.id}" aria-label="${esc(m.title)}. ${m.type==='summary'?'Читать предварительное саммари':'Посмотреть структуру раздела'}">${completed.has(m.id)?'<span class="card-read">Прочитано ✓</span>':''}<div class="card-top"><span class="card-icon">${icon(m.icon)}</span><span class="card-number">${m.n}</span></div><span class="card-category">${esc(m.category)}</span><h3>${esc(m.title)}</h3><p>${esc(m.lead)}</p><div class="card-bottom">${status(m)}<span class="card-arrow">↗</span></div></a>`).join(''):'<div class="empty"><strong>Тема не найдена</strong>Попробуйте другое слово или выберите все направления.<br><button data-reset>Сбросить поиск и фильтр</button></div>';
    document.getElementById('result-count').textContent=`Показано ${matches.length} из ${modules.length}`;
    document.getElementById('live').textContent=`Найдено направлений: ${matches.length}`;
  }
  function renderAdmins() {
    currentRole='admins';updateNav();document.title='Для администраторов — LMB Академия';
    main.innerHTML=roles('admins')+`<section class="admin-hero"><div class="eyebrow">ВТОРОЙ ЭТАП ОБУЧЕНИЯ</div><h1>Понятно объяснять.<br><em>Бережно сопровождать.</em></h1><p>Версия для администраторов будет создана как выжимка из врачебных саммари. Сначала формируем и уточняем основную учебную базу, затем адаптируем её для общения с пациентами.</p><div class="stage"><span class="now">01 · Врачебные саммари</span><b aria-hidden="true">→</b><span>02 · Выжимка для администраторов</span></div></section><div class="admin-grid"><section class="admin-box"><h2>Что войдёт в выжимку</h2><p>Суть метода простыми словами, цель обращения, подготовка по памятке клиники, организация визита, частые вопросы и ситуации, когда нужно подключить врача.</p></section><section class="admin-box"><h2>Одинаковые направления</h2><p>Все ${modules.length} направлений останутся в программе. Глубина материала и формулировки будут адаптированы под задачи администратора и маршрут пациента.</p></section></div><div class="admin-topics">${modules.map(m=>`<span>${esc(m.title)}</span>`).join('')}</div><div class="content-note">${icon('info')}<p>Материалы для администраторов пока не опубликованы. Доступные предварительные саммари находятся во вкладке «Для врачей».</p></div>`;
  }
  function readButton(m) {return `<button class="progress-button ${completed.has(m.id)?'done':''}" data-complete="${m.id}" aria-pressed="${completed.has(m.id)}">${completed.has(m.id)?'✓ Прочитано · отменить':'Отметить как прочитанное'}</button><p class="device-note">Отметка хранится в этом браузере. Это не аттестация.</p>`;}
  function renderModule(id) {
    const m=modules.find(x=>x.id===id);if(!m){renderNotFound();return;}
    currentRole='doctors';updateNav(id);document.title=m.title+' — LMB Академия';
    const idx=modules.indexOf(m),prev=modules[idx-1],next=modules[idx+1];
    main.innerHTML=roles('doctors')+`<div class="breadcrumb"><a href="#">Все направления</a><span>／</span><span>${m.n} · ${esc(m.category)}</span></div><article><header class="article-head"><div class="article-labels">${status(m)}<span>Для врачей</span></div><h1>${esc(m.title)}</h1><p class="article-lead">${esc(m.lead)}</p><div class="article-meta"><span>${esc(m.scope)}</span><span>Редакция 14.10.2026</span><span>${m.sections.length} смысловых блоков</span></div></header>${m.type==='outline'?'<div class="outline-note">Сейчас здесь программа будущего раздела. Полноценное саммари будет подготовлено после отбора профильных учебных материалов.</div>':''}<div class="takeaway"><span>${m.type==='outline'?'СЛЕДУЮЩИЙ ШАГ':'КЛЮЧЕВАЯ МЫСЛЬ'}</span><p>${esc(m.takeaway)}</p></div><div class="article-layout"><div class="article-body">${m.sections.map(([title,body],i)=>`<section class="text-section" id="section-${i}"><h2><span>${String(i+1).padStart(2,'0')}</span>${esc(title)}</h2><p>${esc(body)}</p></section>`).join('')}<details class="sources"><summary>Основа материала и источники · ${m.sources.length+m.links.length}</summary><div class="sources-inner">${m.sources.map(([name,description])=>`<div class="source-item"><strong>${esc(name)}</strong><p>${esc(description)}</p></div>`).join('')}${m.links.map(([label,url])=>`<div class="source-item"><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a></div>`).join('')}<p class="source-caption">${m.sources.length?'Это краткое учебное изложение выбранных материалов. Названия исходников указаны для прослеживаемости; полные файлы на сайте не размещены. Наличие СОП в учебной базе не означает, что его утверждение или актуальность нормативной части проверены в этой редакции.':'Профильные учебные материалы для саммари ещё не отобраны.'}</p></div></details>${m.type==='summary'?'<div class="mobile-read">'+readButton(m)+'</div>':''}<nav class="article-navigation" aria-label="Соседние направления">${prev?`<a href="#module/${prev.id}"><small>← ПРЕДЫДУЩИЙ РАЗДЕЛ</small><b>${esc(prev.title)}</b></a>`:'<a href="#"><small>← КАТАЛОГ</small><b>Все направления</b></a>'}${next?`<a href="#module/${next.id}"><small>СЛЕДУЮЩИЙ РАЗДЕЛ →</small><b>${esc(next.title)}</b></a>`:'<a href="#"><small>КАТАЛОГ →</small><b>Все направления</b></a>'}</nav></div><aside class="toc" aria-label="Содержание раздела"><div class="toc-title">В ЭТОМ РАЗДЕЛЕ</div>${m.sections.map(([title],i)=>`<a href="#section-${i}" data-section="section-${i}">${esc(title)}</a>`).join('')}${m.type==='summary'?'<div class="toc-action">'+readButton(m)+'</div>':''}</aside></div></article>`;
  }
  function renderNotFound(){updateNav();main.innerHTML='<div class="empty"><strong>Раздел не найден</strong><a href="#">Вернуться к направлениям</a></div>';document.title='Раздел не найден — LMB Академия';}
  function route(){const hash=location.hash.slice(1);if(hash.startsWith('section-'))return;if(hash==='admins')renderAdmins();else if(hash.startsWith('module/'))renderModule(hash.slice(7));else renderHome();document.getElementById('sidebar').classList.remove('open');document.getElementById('menu-toggle').setAttribute('aria-expanded','false');window.scrollTo(0,0);}
  document.addEventListener('click',e=>{
    if(e.target.closest('.skip-link')){e.preventDefault();main.focus();main.scrollIntoView({block:'start'});return;}
    const role=e.target.closest('[data-role]');if(role){const dest=role.dataset.role==='admins'?'#admins':'#';if(location.hash===dest||(!location.hash&&dest==='#')){dest==='#'?renderHome():renderAdmins();}else location.hash=dest;return;}
    const filter=e.target.closest('[data-category]');if(filter){category=filter.dataset.category;document.querySelectorAll('[data-category]').forEach(el=>{el.classList.toggle('selected',el.dataset.category===category);el.setAttribute('aria-pressed',String(el.dataset.category===category));});renderCards();return;}
    if(e.target.closest('[data-reset]')){category='Все';query='';renderHome();return;}
    const section=e.target.closest('[data-section]');if(section){e.preventDefault();document.getElementById(section.dataset.section)?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});return;}
    const complete=e.target.closest('[data-complete]');if(complete){const id=complete.dataset.complete;completed.has(id)?completed.delete(id):completed.add(id);let saved=true;try{localStorage.setItem(storageKey,JSON.stringify([...completed]));}catch{saved=false;}document.querySelectorAll('[data-complete]').forEach(el=>{if(el.dataset.complete!==id)return;el.classList.toggle('done',completed.has(id));el.setAttribute('aria-pressed',String(completed.has(id)));el.textContent=completed.has(id)?'✓ Прочитано · отменить':'Отметить как прочитанное';});if(!saved)document.querySelectorAll('.device-note').forEach(el=>el.textContent='Сохранение в браузере недоступно. Отметка действует до перезагрузки.');document.getElementById('live').textContent=completed.has(id)?'Саммари отмечено как прочитанное':'Отметка о прочтении снята';}
  });
  document.getElementById('menu-toggle').addEventListener('click',e=>{const open=document.getElementById('sidebar').classList.toggle('open');e.currentTarget.setAttribute('aria-expanded',String(open));e.currentTarget.setAttribute('aria-label',open?'Закрыть меню':'Открыть меню');});
  window.addEventListener('hashchange',route);route();
})();
