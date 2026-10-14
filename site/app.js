(() => {
  'use strict';
  const D = window.LMB_DATA;
  const main = document.getElementById('main');
  const nav = document.getElementById('module-nav');
  const live = document.getElementById('live');
  const isPreview = D.build.mode === 'preview';

  const modules = D.modules.filter(m => m.lessons.some(id => D.lessons[id]));
  const lessonsOf = m => m.lessons.map(id => D.lessons[id]).filter(Boolean).sort((a, b) => a.order - b.order);
  const allLessons = modules.flatMap(lessonsOf);
  const moduleById = id => modules.find(m => m.id === id);
  const categories = ['Все', ...new Set(modules.map(m => m.category))];
  const variantLabel = v => (D.variants.find(x => x.id === v) || {}).label || v;

  let variant = 'doctors';
  let category = 'Все';
  let query = '';

  // ------------------------------------------------------------ утилиты
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const pad = n => String(n).padStart(2, '0');
  const fmtDate = iso => iso ? iso.split('-').reverse().join('.') : '';
  const href = (v, path) => '#' + (v === 'admins' ? 'admins' + (path ? '/' + path : '') : (path || ''));
  const plural = (n, one, few, many) => { const a = n % 10, b = n % 100; return a === 1 && b !== 11 ? one : a >= 2 && a <= 4 && (b < 10 || b >= 20) ? few : many; };

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
  const icon = name => '<svg viewBox="0 0 24 24" aria-hidden="true">' + (iconPaths[name] || iconPaths.cell) + '</svg>';

  // ------------------------------------------------------------ статусы
  const STATES = {
    approved: {label: 'Проверено', mark: '✓', cls: 'ok'},
    draft: {label: 'Черновик · не утверждён', mark: '✎', cls: 'draft'},
    outline: {label: 'Программа раздела', mark: '☰', cls: 'wait'},
    pending: {label: 'Материал готовится', mark: '◷', cls: 'wait'},
    withdrawn: {label: 'Снято с публикации', mark: '⊘', cls: 'off'}
  };
  const COVERAGE = {concept: 'концепция', safety: 'безопасность', clinical: 'клиническое применение', interpretation: 'интерпретация'};
  const vOf = (lesson, v = variant) => lesson.variants[v] || {state: 'pending', program: []};
  const hasText = st => st === 'approved' || st === 'draft' || st === 'outline';
  const isSummary = st => st === 'approved' || st === 'draft';
  const chip = st => { const s = STATES[st] || STATES.pending; return `<span class="status ${s.cls}"><span aria-hidden="true">${s.mark}</span>${s.label}</span>`; };

  function moduleStatus(m) {
    const ls = lessonsOf(m);
    if (ls.length === 1) return chip(vOf(ls[0]).state);
    const counts = {};
    ls.forEach(l => { const st = vOf(l).state; counts[st] = (counts[st] || 0) + 1; });
    const order = ['approved', 'draft', 'outline', 'pending', 'withdrawn'];
    const parts = order.filter(k => counts[k]).map(k => `${STATES[k].label.split(' ·')[0].toLowerCase()}: ${counts[k]}`);
    const top = order.find(k => counts[k]);
    return `<span class="status ${STATES[top].cls}"><span aria-hidden="true">${STATES[top].mark}</span>${ls.length} ${plural(ls.length, 'тема', 'темы', 'тем')} · ${parts.join(', ')}</span>`;
  }

  // ------------------------------------------------------------ отметки о прочтении (локально, по версии)
  const READ_KEY = 'lmb-academy-read-v2';
  let reads = {};
  let storageOk = true;
  try {
    const raw = localStorage.getItem(READ_KEY);
    if (raw) reads = JSON.parse(raw) || {};
    else {
      // Перенос отметок прототипа (по направлениям) на вводные темы версии 0.1.0, из которой перенесён текст.
      const old = JSON.parse(localStorage.getItem('lmb-academy-read-v1') || '[]');
      if (Array.isArray(old)) old.forEach(id => { if (D.lessons[id + '-intro']) reads[id + '-intro:doctors'] = '0.1.0'; });
      if (old.length) localStorage.setItem(READ_KEY, JSON.stringify(reads));
    }
  } catch { storageOk = false; }
  const majorMinor = v => String(v || '').split('.').slice(0, 2).join('.');
  function readState(lesson, v = variant) {
    const cur = vOf(lesson, v);
    const saved = reads[lesson.id + ':' + v];
    if (!saved || !isSummary(cur.state)) return 'unread';
    return majorMinor(saved) === majorMinor(cur.version) ? 'read' : 'outdated';
  }
  function toggleRead(lesson) {
    const key = lesson.id + ':' + variant;
    if (readState(lesson) === 'read') delete reads[key]; else reads[key] = vOf(lesson).version;
    try { localStorage.setItem(READ_KEY, JSON.stringify(reads)); } catch { storageOk = false; }
  }
  function readButton(lesson) {
    const st = readState(lesson);
    const label = st === 'read' ? '✓ Прочитано · отменить' : st === 'outdated' ? 'Материал обновлён · отметить снова' : 'Отметить как прочитанное';
    const note = !storageOk ? 'Сохранение в браузере недоступно. Отметка действует до перезагрузки.'
      : st === 'outdated' ? `Вы отмечали версию ${esc(reads[lesson.id + ':' + variant])}. Текущая — ${esc(vOf(lesson).version)}.`
      : 'Отметка хранится только в этом браузере. Это не аттестация.';
    return `<button class="progress-button ${st}" data-complete="${esc(lesson.id)}" aria-pressed="${st === 'read'}">${label}</button><p class="device-note">${note}</p>`;
  }
  function moduleReadMark(m) {
    const ls = lessonsOf(m).filter(l => isSummary(vOf(l).state));
    if (!ls.length) return '';
    const states = ls.map(l => readState(l));
    if (states.includes('outdated')) return '<span class="card-read outdated">Обновлено</span>';
    return states.every(s => s === 'read') ? '<span class="card-read">Прочитано ✓</span>' : '';
  }

  // ------------------------------------------------------------ поиск
  const norm = s => String(s || '').toLocaleLowerCase('ru').replace(/ё/g, 'е').replace(/[^a-zа-я0-9]+/gi, ' ').trim();
  const ENDINGS = /(иями|ями|ами|ого|его|ому|ему|ыми|ими|ий|ый|ой|ая|яя|ое|ее|ие|ые|ую|юю|ам|ям|ах|ях|ом|ем|ов|ев|ей|а|я|о|е|и|ы|у|ю|ь|й)$/;
  const stem = w => { if (w.length < 5) return w; const s = w.replace(ENDINGS, ''); return s.length >= 4 ? s : w; };
  const synGroups = (D.synonyms || []).map(g => g.map(norm).filter(Boolean));
  function parseQuery(q) {
    let rest = ' ' + norm(q) + ' ';
    const terms = [];
    const phrases = synGroups.flatMap((g, gi) => g.map(p => [p, gi])).sort((a, b) => b[0].length - a[0].length);
    phrases.forEach(([p, gi]) => {
      if (rest.includes(' ' + p + ' ')) { rest = rest.replace(' ' + p + ' ', ' '); terms.push(synGroups[gi]); }
    });
    rest.trim().split(/\s+/).filter(Boolean).forEach(w => {
      const g = synGroups.find(gr => gr.some(p => !p.includes(' ') && stem(p) === stem(w)));
      terms.push(g || [w]);
    });
    return terms;
  }
  const altMatches = (alt, text) => alt.split(' ').every(w => text.includes(stem(w)));
  const searchCache = {};
  function lessonSearchText(l) {
    const key = l.id + ':' + variant;
    if (!searchCache[key]) {
      const m = moduleById(l.moduleId), v = vOf(l);
      const parts = [m.title, m.keywords.join(' '), l.title, l.keywords.join(' '), (v.program || []).join(' ')];
      if (hasText(v.state)) parts.push(v.goal, v.takeaway, v.scope, v.text);
      searchCache[key] = {all: ' ' + norm(parts.join(' ')) + ' ', title: ' ' + norm(m.title + ' ' + l.title) + ' '};
    }
    return searchCache[key];
  }
  function search(q) {
    const terms = parseQuery(q);
    if (!terms.length) return [];
    return allLessons
      .filter(l => category === 'Все' || moduleById(l.moduleId).category === category)
      .map(l => {
        const t = lessonSearchText(l);
        if (!terms.every(alts => alts.some(a => altMatches(a, t.all)))) return null;
        const score = terms.filter(alts => alts.some(a => altMatches(a, t.title))).length;
        return {l, score};
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score)
      .map(x => x.l);
  }

  // ------------------------------------------------------------ общие блоки
  function rolebar() {
    return `<div class="rolebar"><div class="roles" role="group" aria-label="Вариант обучения">${D.variants.map(v =>
      `<button type="button" data-role="${v.id}" class="${v.id === variant ? 'selected' : ''}" aria-pressed="${v.id === variant}">${esc(v.label)}</button>`).join('')}</div>
      <span class="role-caption">Переключатель выбирает вариант обучения и не ограничивает доступ.</span></div>`
      + (isPreview ? '<div class="preview-banner" role="note"><strong>Предпросмотр.</strong> Показаны черновики, которые не утверждены и не попадают в рабочую сборку.</div>' : '');
  }
  function updateNav(activeModule) {
    document.getElementById('module-total').textContent = pad(modules.length);
    nav.innerHTML = modules.map(m => `<a href="${href(variant, 'module/' + m.id)}" class="${m.id === activeModule ? 'active' : ''}" ${m.id === activeModule ? 'aria-current="page"' : ''}><span>${esc(m.n)}</span><b>${esc(m.title)}</b></a>`).join('');
    const cat = document.getElementById('catalog-link');
    cat.href = href(variant, '');
    cat.classList.toggle('active', !activeModule);
  }

  // ------------------------------------------------------------ каталог
  function renderHome() {
    updateNav();
    document.title = (variant === 'admins' ? 'Для администраторов — ' : '') + 'LMB Академия — обучение команды';
    const published = allLessons.filter(l => isSummary(vOf(l).state));
    const approved = published.filter(l => vOf(l).state === 'approved').length;
    const drafts = published.length - approved;
    const intro = variant === 'admins'
      ? `<section class="admin-hero"><div class="eyebrow">ВАРИАНТ ДЛЯ АДМИНИСТРАТОРОВ</div><h1>Понятно объяснять.<br><em>Бережно сопровождать.</em></h1><p>Выжимка для администраторов создаётся из утверждённой врачебной версии каждой темы. Если выжимка ещё не готова, тема помечена «Материал готовится»; врачебный текст вместо неё не подставляется.</p></section>
        <div class="admin-grid"><section class="admin-box"><h2>Что войдёт в выжимку</h2><p>Суть метода простыми словами, цель обращения, подготовка по памятке клиники, организация визита, частые вопросы и ситуации, когда нужно подключить врача.</p></section><section class="admin-box"><h2>Те же направления</h2><p>Все ${modules.length} ${plural(modules.length, 'направление', 'направления', 'направлений')} остаются в программе. Глубина и формулировки адаптируются под задачи администратора и маршрут пациента.</p></section></div>`
      : `<section class="hero"><div><div class="eyebrow">КЛИНИЧЕСКОЕ МЫШЛЕНИЕ В ЛМБ</div><h1>Понимать глубже.<br><em>Применять точнее.</em></h1><p class="hero-text">Учебные саммари по инструментам клиники. Механизмы, клиническая логика и безопасность — в едином пространстве для команды.</p>
        <div class="hero-meta"><div><strong>${pad(modules.length)}</strong><span>${plural(modules.length, 'направление', 'направления', 'направлений')}</span></div><div><strong>${pad(allLessons.length)}</strong><span>${plural(allLessons.length, 'тема', 'темы', 'тем')}</span></div><div><strong>${pad(approved)}</strong><span>${plural(approved, 'проверенное саммари', 'проверенных саммари', 'проверенных саммари')}</span></div>${drafts ? `<div><strong>${pad(drafts)}</strong><span>черновиков в предпросмотре</span></div>` : ''}</div></div>
        <aside class="hero-panel"><div class="panel-label">ПЕРВЫЙ ЭТАП</div><h2>Общая основа<br>для врачей клиники</h2><div class="route-step"><span>01</span>Понять научную основу</div><div class="route-step"><span>02</span>Разобрать инструменты</div><div class="route-step"><span>03</span>Связать с клинической задачей</div><a href="${href(variant, 'module/aging')}">Начать с основ <span aria-hidden="true">↗</span></a></aside></section>`;
    main.innerHTML = rolebar() + intro + `<section aria-labelledby="catalog-title"><div class="catalog-head"><div class="catalog-title"><h2 id="catalog-title">Инструменты ЛМБ</h2><p>${modules.length} ${plural(modules.length, 'направление', 'направления', 'направлений')}, ${allLessons.length} ${plural(allLessons.length, 'тема', 'темы', 'тем')}. ${esc(variantLabel(variant))}.</p></div>
      <div class="search">${icon('search')}<label for="search" class="sr-only">Поиск по темам</label><input type="search" id="search" placeholder="Найти тему или инструмент" value="${esc(query)}" autocomplete="off"><button type="button" class="search-clear" id="clear-search" aria-label="Очистить поиск" ${query ? '' : 'hidden'}>×</button></div></div>
      <div class="filters" role="group" aria-label="Фильтр по категориям">${categories.map(c => `<button type="button" class="filter ${c === category ? 'selected' : ''}" data-category="${esc(c)}" aria-pressed="${c === category}">${esc(c)}</button>`).join('')}<span class="result-count" id="result-count"></span></div>
      <div id="cards"></div></section>
      <div class="content-note">${icon('info')}<p>${statusNote(approved, drafts)} Полные лекции и исходные файлы на сайте не размещаются.</p></div>`;
    renderCards();
    const input = document.getElementById('search');
    input.addEventListener('input', e => { query = e.target.value; document.getElementById('clear-search').hidden = !query; renderCards(); });
  }
  function statusNote(approved, drafts) {
    const outlines = allLessons.filter(l => vOf(l).state === 'outline').length;
    const pending = allLessons.filter(l => vOf(l).state === 'pending').length;
    return `${esc(variantLabel(variant))}: проверенных саммари — ${approved}${drafts ? `, черновиков в предпросмотре — ${drafts}` : ''}, программ разделов — ${outlines}, тем в подготовке — ${pending}. Отметка «Проверено» ставится только при записи о медицинском утверждении этой версии.`;
  }
  function renderCards() {
    const box = document.getElementById('cards');
    const count = document.getElementById('result-count');
    if (query.trim()) {
      const hits = search(query);
      box.className = 'results';
      box.innerHTML = hits.length ? `<ul class="result-list">${hits.map(l => { const m = moduleById(l.moduleId), v = vOf(l);
        return `<li><a href="${href(variant, 'lesson/' + l.id)}"><span class="result-module">${esc(m.n)} · ${esc(m.title)}</span><b>${esc(l.title)}</b>${chip(v.state)}${hasText(v.state) && v.goal ? `<span class="result-goal">${esc(v.goal)}</span>` : ''}</a></li>`; }).join('')}</ul>` : emptyState();
      count.textContent = `Найдено тем: ${hits.length}`;
      live.textContent = `Найдено тем: ${hits.length}`;
      return;
    }
    const list = modules.filter(m => category === 'Все' || m.category === category);
    box.className = 'cards';
    box.innerHTML = list.length ? list.map(m => `<a class="card" href="${href(variant, 'module/' + m.id)}">${moduleReadMark(m)}<div class="card-top"><span class="card-icon">${icon(m.icon)}</span><span class="card-number" aria-hidden="true">${esc(m.n)}</span></div><span class="card-category">${esc(m.category)}</span><h3>${esc(m.title)}</h3><p>${esc(m.lead)}</p><div class="card-bottom">${moduleStatus(m)}<span class="card-arrow" aria-hidden="true">↗</span></div></a>`).join('') : emptyState();
    count.textContent = `Показано ${list.length} из ${modules.length}`;
    live.textContent = `Показано направлений: ${list.length}`;
  }
  const emptyState = () => `<div class="empty"><strong>Ничего не найдено</strong>Попробуйте другое слово или выберите все направления.<br><button type="button" data-reset>Сбросить поиск и фильтр</button></div>`;

  // ------------------------------------------------------------ направление
  function renderModule(id) {
    const m = moduleById(id);
    if (!m) return renderNotFound();
    updateNav(m.id);
    document.title = m.title + ' — LMB Академия';
    const ls = lessonsOf(m);
    const linked = allLessons.filter(l => (l.alsoIn || []).includes(m.id));
    const idx = modules.indexOf(m), prev = modules[idx - 1], next = modules[idx + 1];
    const row = l => { const v = vOf(l), rs = readState(l);
      return `<li><a href="${href(variant, 'lesson/' + l.id)}"><b>${esc(l.title)}</b>${chip(v.state)}${rs === 'read' ? '<span class="tag">Прочитано ✓</span>' : rs === 'outdated' ? '<span class="tag">Обновлено после отметки</span>' : ''}${hasText(v.state) && v.goal ? `<span class="result-goal">${esc(v.goal)}</span>` : ''}${!hasText(v.state) && v.program && v.program.length ? `<span class="result-goal">Программа: ${esc(v.program.join(' · '))}</span>` : ''}</a></li>`; };
    main.innerHTML = rolebar() + `<nav class="breadcrumb" aria-label="Путь"><a href="${href(variant, '')}">Все направления</a><span aria-hidden="true">／</span><span>${esc(m.n)} · ${esc(m.category)}</span></nav>
      <header class="article-head"><div class="article-labels"><span>Направление ${esc(m.n)}</span><span>${esc(variantLabel(variant))}</span></div><h1>${esc(m.title)}</h1><p class="article-lead">${esc(m.lead)}</p></header>
      <section class="topics" aria-labelledby="topics-title"><h2 id="topics-title">${ls.length === 1 ? 'Тема направления' : 'Темы направления'}</h2><ul class="result-list">${ls.map(row).join('')}</ul></section>
      ${linked.length ? `<section class="topics"><h2>Связанные темы других направлений</h2><ul class="result-list">${linked.map(row).join('')}</ul></section>` : ''}
      <nav class="article-navigation" aria-label="Соседние направления">${prev ? `<a href="${href(variant, 'module/' + prev.id)}"><small>← ПРЕДЫДУЩЕЕ НАПРАВЛЕНИЕ</small><b>${esc(prev.title)}</b></a>` : `<a href="${href(variant, '')}"><small>← КАТАЛОГ</small><b>Все направления</b></a>`}${next ? `<a href="${href(variant, 'module/' + next.id)}"><small>СЛЕДУЮЩЕЕ НАПРАВЛЕНИЕ →</small><b>${esc(next.title)}</b></a>` : `<a href="${href(variant, '')}"><small>КАТАЛОГ →</small><b>Все направления</b></a>`}</nav>`;
  }

  // ------------------------------------------------------------ тема
  function renderLesson(id, anchor) {
    const l = D.lessons[id];
    if (!l || !moduleById(l.moduleId)) return renderNotFound();
    const m = moduleById(l.moduleId), v = vOf(l);
    updateNav(m.id);
    document.title = l.title + ' — ' + variantLabel(variant) + ' — LMB Академия';
    const i = allLessons.indexOf(l), prev = allLessons[i - 1], next = allLessons[i + 1];
    const crumbs = `<nav class="breadcrumb" aria-label="Путь"><a href="${href(variant, '')}">Все направления</a><span aria-hidden="true">／</span><a href="${href(variant, 'module/' + m.id)}">${esc(m.n)} · ${esc(m.title)}</a></nav>`;
    const neighbours = `<nav class="article-navigation" aria-label="Соседние темы">${prev ? `<a href="${href(variant, 'lesson/' + prev.id)}"><small>← ПРЕДЫДУЩАЯ ТЕМА</small><b>${esc(prev.title)}</b></a>` : `<a href="${href(variant, '')}"><small>← КАТАЛОГ</small><b>Все направления</b></a>`}${next ? `<a href="${href(variant, 'lesson/' + next.id)}"><small>СЛЕДУЮЩАЯ ТЕМА →</small><b>${esc(next.title)}</b></a>` : `<a href="${href(variant, '')}"><small>КАТАЛОГ →</small><b>Все направления</b></a>`}</nav>`;
    const other = D.variants.map(x => x.id).find(x => x !== variant);
    const otherNote = hasText(vOf(l, other).state) ? `<p>Доступен вариант «${esc(variantLabel(other))}»: <a href="${href(other, 'lesson/' + l.id)}">открыть</a>.</p>` : '';

    if (!hasText(v.state)) {
      const prog = v.program && v.program.length ? `<h2>Программа темы</h2><ul>${v.program.map(p => `<li>${esc(p)}</li>`).join('')}</ul>` : '';
      main.innerHTML = rolebar() + crumbs + `<article><header class="article-head"><div class="article-labels">${chip(v.state)}<span>${esc(variantLabel(variant))}</span></div><h1>${esc(l.title)}</h1><p class="article-lead">${esc(m.lead)}</p></header>
        <div class="pending-box"><p class="pending-title">${v.state === 'withdrawn' ? 'Материал снят с публикации' : 'Материал готовится'}</p>${v.state === 'withdrawn' ? `<p>${esc(v.withdrawnNote || 'Решение принято ответственным врачом.')}</p>` : `${v.programNote ? `<p>${esc(v.programNote)}</p>` : ''}${prog}`}${otherNote}</div>${neighbours}</article>`;
      return focusTop(anchor);
    }

    const kind = v.state === 'outline' ? 'outline' : 'summary';
    const meta = [v.scope, v.updatedAt ? 'Редакция ' + fmtDate(v.updatedAt) : '', 'Версия ' + v.version,
      (v.coverage || []).length ? 'Охват: ' + v.coverage.map(c => COVERAGE[c] || c).join(', ') : '',
      v.approval ? `Проверено: ${v.approval.reviewer}, ${fmtDate(v.approval.date)}` : '',
      v.nextReviewAt ? 'Пересмотр: ' + fmtDate(v.nextReviewAt) : ''].filter(Boolean);
    const notes = [
      v.state === 'draft' ? `<div class="draft-note" role="note"><strong>Черновик (${esc(v.editorialStatus)}).</strong> Текст не прошёл медицинское утверждение и виден только в предпросмотре.</div>` : '',
      kind === 'outline' ? '<div class="outline-note">Сейчас здесь программа будущего раздела. Полноценное саммари будет подготовлено после отбора профильных учебных материалов.</div>' : '',
      v.fallbackNote ? `<div class="outline-note">${esc(v.fallbackNote)}</div>` : '',
      v.needsSync ? '<div class="draft-note" role="note">Врачебная версия темы обновлена после подготовки этой выжимки. Выжимка ожидает сверки.</div>' : ''
    ].join('');
    const srcItems = (v.sources || []).map(s => { const src = D.sources[s.id] || {title: s.id};
      const head = [src.author, src.year].filter(Boolean).join(', ');
      return `<div class="source-item">${src.url ? `<a href="${esc(src.url)}" target="_blank" rel="noopener noreferrer">${esc(src.title)} ↗</a>` : `<strong>${esc(src.title)}</strong>`}<p>${esc([src.type, head, s.locator].filter(Boolean).join(' · '))}</p>${s.supports ? `<p>${esc(s.supports)}</p>` : ''}</div>`; }).join('');
    const related = (l.related || []).map(rid => D.lessons[rid]).filter(Boolean);
    const action = isSummary(v.state) ? `<div class="read-box">${readButton(l)}</div>` : '';
    main.innerHTML = rolebar() + crumbs + `<article><header class="article-head"><div class="article-labels">${chip(v.state)}<span>${esc(variantLabel(variant))}</span></div><h1>${esc(l.title)}</h1>${v.goal ? `<p class="article-lead">${esc(v.goal)}</p>` : ''}<div class="article-meta">${meta.map(x => `<span>${esc(x)}</span>`).join('')}</div></header>
      ${notes}${v.takeaway ? `<div class="takeaway"><span>${kind === 'outline' ? 'СЛЕДУЮЩИЙ ШАГ' : 'КЛЮЧЕВАЯ МЫСЛЬ'}</span><p>${esc(v.takeaway)}</p></div>` : ''}
      <div class="article-layout"><div class="article-body">${v.html}
      <details class="sources"><summary>Основа материала и источники · ${(v.sources || []).length}</summary><div class="sources-inner">${srcItems}<p class="source-caption">${(v.sources || []).length ? 'Это краткое учебное изложение выбранных материалов. Названия исходников указаны для прослеживаемости; полные файлы на сайте не размещены. Наличие СОП в учебной базе не означает, что его утверждение или актуальность нормативной части проверены в этой редакции.' : 'Профильные учебные материалы для саммари ещё не отобраны.'}</p></div></details>
      ${related.length ? `<section class="related"><h2>Связанные темы</h2><ul>${related.map(r => `<li><a href="${href(variant, 'lesson/' + r.id)}">${esc(r.title)}</a></li>`).join('')}</ul></section>` : ''}
      ${otherNote ? `<div class="other-variant">${otherNote}</div>` : ''}
      <div class="mobile-read">${action}</div>${neighbours}</div>
      <aside class="toc" aria-label="Содержание темы"><div class="toc-title">В ЭТОЙ ТЕМЕ</div>${(v.toc || []).map(t => `<a href="${href(variant, 'lesson/' + l.id + '/' + t.id)}" data-section="${t.id}">${esc(t.title)}</a>`).join('')}${action ? `<div class="toc-action">${action}</div>` : ''}<button type="button" class="print-button" data-print>Распечатать</button></aside></div></article>`;
    focusTop(anchor);
  }
  function focusTop(anchor) {
    const target = anchor && document.getElementById(anchor);
    if (target) target.scrollIntoView({block: 'start'}); else window.scrollTo(0, 0);
    main.focus({preventScroll: true});
  }
  function renderNotFound() {
    updateNav();
    document.title = 'Раздел не найден — LMB Академия';
    main.innerHTML = rolebar() + `<div class="empty"><strong>Раздел не найден</strong>Ссылка устарела или содержит ошибку.<br><a href="${href(variant, '')}">Вернуться к направлениям</a></div>`;
  }

  // ------------------------------------------------------------ маршруты
  // #, #admins, [#admins/]module/ID, [#admins/]lesson/ID[/section-N]. Старый маршрут #module/ID сохраняется.
  function route() {
    let h = decodeURIComponent(location.hash.slice(1));
    if (/^section-\d+$/.test(h)) return;
    variant = /^admins(\/|$)/.test(h) ? 'admins' : 'doctors';
    h = h.replace(/^admins\/?/, '');
    const parts = h.split('/');
    if (!h) { renderHome(); window.scrollTo(0, 0); }
    else if (parts[0] === 'module' && parts[1]) { renderModule(parts[1]); window.scrollTo(0, 0); }
    else if (parts[0] === 'lesson' && parts[1]) renderLesson(parts[1], parts[2]);
    else renderNotFound();
    document.getElementById('sidebar').classList.remove('open');
    const toggle = document.getElementById('menu-toggle');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Открыть меню');
  }

  document.addEventListener('click', e => {
    const role = e.target.closest('[data-role]');
    if (role) {
      const target = role.dataset.role;
      const rest = decodeURIComponent(location.hash.slice(1)).replace(/^admins\/?/, '');
      const dest = href(target, rest);
      if (dest === location.hash || (dest === '#' && !location.hash)) route(); else location.hash = dest;
      return;
    }
    const filter = e.target.closest('[data-category]');
    if (filter) {
      category = filter.dataset.category;
      document.querySelectorAll('[data-category]').forEach(el => { el.classList.toggle('selected', el.dataset.category === category); el.setAttribute('aria-pressed', String(el.dataset.category === category)); });
      renderCards();
      return;
    }
    if (e.target.closest('[data-reset]')) { category = 'Все'; query = ''; renderHome(); document.getElementById('search').focus(); return; }
    if (e.target.closest('#clear-search')) { query = ''; const s = document.getElementById('search'); s.value = ''; e.target.closest('#clear-search').hidden = true; renderCards(); s.focus(); return; }
    if (e.target.closest('[data-print]')) { window.print(); return; }
    const section = e.target.closest('[data-section]');
    if (section) {
      e.preventDefault();
      const el = document.getElementById(section.dataset.section);
      if (el) {
        el.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'});
        history.replaceState(null, '', section.getAttribute('href'));
        el.setAttribute('tabindex', '-1'); el.focus({preventScroll: true});
      }
      return;
    }
    const complete = e.target.closest('[data-complete]');
    if (complete) {
      const l = D.lessons[complete.dataset.complete];
      toggleRead(l);
      document.querySelectorAll('.read-box').forEach(box => { box.innerHTML = readButton(l); });
      live.textContent = readState(l) === 'read' ? 'Тема отмечена как прочитанная' : 'Отметка о прочтении снята';
    }
  });
  document.getElementById('menu-toggle').addEventListener('click', e => {
    const open = document.getElementById('sidebar').classList.toggle('open');
    e.currentTarget.setAttribute('aria-expanded', String(open));
    e.currentTarget.setAttribute('aria-label', open ? 'Закрыть меню' : 'Открыть меню');
  });
  document.querySelector('.skip-link').addEventListener('click', e => { e.preventDefault(); main.focus(); main.scrollIntoView({block: 'start'}); });
  document.getElementById('edition').lastChild.textContent = isPreview ? ' Предпросмотр черновиков' : ' Рабочая редакция';
  document.getElementById('build-date').textContent = 'Сборка ' + fmtDate(D.build.builtAt);
  window.addEventListener('beforeprint', () => document.querySelectorAll('details.sources').forEach(d => { d.open = true; }));
  window.addEventListener('hashchange', route);
  route();
})();
