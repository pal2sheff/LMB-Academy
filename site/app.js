(() => {
  'use strict';
  const D = window.LMB_DATA;
  const main = document.getElementById('main');
  const nav = document.getElementById('module-nav');
  const live = document.getElementById('live');
  const embedded = !!window.LMB_EMBEDDED;

  const groups = D.groups;
  const groupOf = m => groups.find(g => g.title === m.category) || groups[groups.length - 1];
  const modules = D.modules.filter(m => m.lessons.some(id => D.lessons[id]));
  const lessonsOf = m => m.lessons.map(id => D.lessons[id]).filter(Boolean).sort((a, b) => a.order - b.order);
  const moduleById = id => modules.find(m => m.id === id);
  // Единая группировка и порядок для каталога, меню, поиска и соседних материалов.
  const modulesIn = g => modules.filter(m => groupOf(m) === g).sort((a, b) => (a.displayOrder || 0) - (b.displayOrder || 0));
  const grouped = list => groups.map(g => ({g, items: list.filter(x => groupOf(x.module || x) === g)})).filter(x => x.items.length);
  const orderedModules = groups.flatMap(modulesIn);
  const allLessons = orderedModules.flatMap(lessonsOf);
  const variantIds = D.variants.map(v => v.id);
  const OPEN_OTHER = {doctors: 'Открыть врачебный материал', admins: 'Открыть материал для администраторов'};

  let variant = 'doctors';
  let group = null; // null — все группы
  let query = '';

  // ------------------------------------------------------------ утилиты
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmtDate = iso => iso ? iso.split('-').reverse().join('.') : '';
  const href = (v, path) => '#' + (v === 'admins' ? 'admins' + (path ? '/' + path : '') : (path || ''));
  const groupHref = g => href(variant, g ? 'group/' + g.id : '');

  // ------------------------------------------------------------ иконки: только встроенный набор по ключу icon
  const iconPaths = {
    mitochondrion: '<g transform="rotate(-25 12 12)"><ellipse cx="12" cy="12" rx="9" ry="5.5"/><path d="M5.6 12c.9-2.3 1.8-2.3 2.5 0s1.6 2.3 2.5 0 1.6-2.3 2.5 0 1.6 2.3 2.5 0 1.3-2 2.2 0"/></g>',
    dna: '<path d="M7 3c0 4.5 10 6.5 10 9s-10 4.5-10 9"/><path d="M17 3c0 4.5-10 6.5-10 9s10 4.5 10 9"/><path d="M8.6 6.5h6.8M10 9.6h4M10 14.4h4M8.6 17.5h6.8"/>',
    'saliva-tube': '<path d="M7.5 3h7M9 3v13.5a2 2 0 0 0 4 0V3"/><path d="M9 11h4"/><path d="M18 6c-1.1 1.5-1.7 2.5-1.7 3.2a1.7 1.7 0 0 0 3.4 0c0-.7-.6-1.7-1.7-3.2Z"/>',
    'urine-molecule': '<path d="M3.5 5h10v3h-10z"/><path d="M4.5 8h8v11a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2V8Z"/><path d="M4.5 13h8"/><path d="M18.5 6.2l2.4 1.4v2.8l-2.4 1.4-2.4-1.4V7.6Z"/>',
    chromatogram: '<path d="M3 3v18h18"/><path d="M5 18c1.4 0 1.8-8 2.8-8s1.4 8 2.8 8 1.3-4.5 2.2-4.5 1.3 4.5 2.2 4.5 1.4-11 2.4-11 1.1 11 2.4 11"/>',
    'urine-cycle': '<path d="M3.5 5h10v3h-10z"/><path d="M4.5 8h8v11a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2V8Z"/><path d="M4.5 13h8"/><path d="M21 12a3 3 0 1 1-1.1-2.3"/><path d="M20.3 7.4v2.4h-2.4"/>',
    'infusion-bag': '<path d="M7 3h10v9.5a3.5 3.5 0 0 1-3.5 3.5h-3A3.5 3.5 0 0 1 7 12.5V3Z"/><path d="M7 7.5h10"/><path d="M12 16v2"/><path d="M12 18c0 2 1.4 3 3.5 3H19"/>',
    'peptide-chain': '<circle cx="4.8" cy="15.5" r="2"/><circle cx="10" cy="8.5" r="2"/><circle cx="14" cy="16" r="2"/><circle cx="19.2" cy="9" r="2"/><path d="M6 13.9l2.8-3.8M10.9 10.3l2.2 3.9M15.2 14.4l2.8-3.8"/>',
    'hormone-receptor': '<circle cx="12" cy="7" r="3"/><path d="M4 21v-7h5a3 3 0 0 0 6 0h5v7"/>',
    'pellet-implant': '<path d="M3 8c2-1.3 4-1.3 6 0s4 1.3 6 0 4-1.3 6 0"/><rect x="5" y="12.5" width="6" height="2.8" rx="1.4"/><rect x="13" y="15.5" width="6" height="2.8" rx="1.4"/>',
    'ozone-molecule': '<circle cx="5.5" cy="15.5" r="2.5"/><circle cx="12" cy="7.5" r="2.5"/><circle cx="18.5" cy="15.5" r="2.5"/><path d="M7.1 13.6l3.3-4.2M13.6 9.4l3.3 4.2"/>',
    'lymph-vessel': '<path d="M3.5 20.5l4.6-4.6M12.6 11.4l2.6-2.6M19.3 4.7l1.2-1.2"/><ellipse cx="10.4" cy="13.6" rx="3" ry="2" transform="rotate(-45 10.4 13.6)"/><ellipse cx="17.2" cy="6.8" rx="2.5" ry="1.7" transform="rotate(-45 17.2 6.8)"/>',
    'cell-clock': '<circle cx="9.5" cy="10" r="6.5"/><circle cx="8.5" cy="10" r="2"/><circle cx="17.5" cy="17.5" r="3.5"/><path d="M17.5 15.8v1.9l1.3.9"/>',
    male: '<circle cx="9.5" cy="14.5" r="5.5"/><path d="M13.5 10.5 20 4M15 4h5v5"/>',
    female: '<circle cx="12" cy="8.5" r="5"/><path d="M12 13.5V21M8.5 17.5h7"/>',
    doc: '<path d="M7 3h7l4 4v14H7Z"/><path d="M14 3v4h4M9.5 12h6M9.5 16h6"/>'
  };
  const icon = (key, cls = 'ico') => `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${Object.prototype.hasOwnProperty.call(iconPaths, key) ? iconPaths[key] : iconPaths.doc}</svg>`;

  // ------------------------------------------------------------ статусы (внутренние значения не меняются)
  const STATES = {
    approved: {label: 'Проверено', cls: 'ok'},
    draft: {label: 'Черновик', cls: 'draft'},
    outline: {label: 'Готовится', cls: 'wait'},
    pending: {label: 'Готовится', cls: 'wait'},
    withdrawn: {label: 'Недоступно', cls: 'off'}
  };
  const COVERAGE = {concept: 'концепция', safety: 'безопасность', clinical: 'клиническое применение', interpretation: 'интерпретация'};
  const vOf = (lesson, v = variant) => lesson.variants[v] || {state: 'pending', program: []};
  const hasText = st => st === 'approved' || st === 'draft' || st === 'outline';
  const isSummary = st => st === 'approved' || st === 'draft';
  const chip = st => { const s = STATES[st] || STATES.pending; return `<span class="status ${s.cls}">${s.label}</span>`; };

  // Направление с одной собственной темой и без связанных тем открывается сразу темой.
  function directLesson(m) {
    const own = lessonsOf(m);
    const linked = allLessons.some(l => (l.alsoIn || []).includes(m.id));
    return own.length === 1 && !linked ? own[0] : null;
  }
  const moduleHref = m => { const l = directLesson(m); return href(variant, l ? 'lesson/' + l.id : 'module/' + m.id); };

  function moduleStatus(m) {
    const l = directLesson(m);
    if (l) return chip(vOf(l).state);
    const states = lessonsOf(m).map(x => vOf(x).state);
    const approved = states.includes('approved'), draft = states.includes('draft');
    if (approved && draft) return '<span class="status ok">Материалы и черновики</span>';
    if (approved) return '<span class="status ok">Есть материалы</span>';
    if (draft) return chip('draft');
    return chip('pending');
  }

  // ------------------------------------------------------------ отметки о прочтении (локально, по версии и аудитории)
  const READ_KEY = 'lmb-academy-read-v2';
  let reads = {};
  let storageOk = true;
  try {
    const raw = localStorage.getItem(READ_KEY);
    if (raw) reads = JSON.parse(raw) || {};
    else {
      // Отметки прототипа (по направлениям) переносятся на вводные темы версии 0.1.0, из которой перенесён текст.
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
  function readBlock(lesson) {
    const st = readState(lesson);
    const hint = storageOk ? 'На этом устройстве' : 'Отметка не сохранится после перезагрузки';
    if (st === 'read') return `<p class="read-state">Прочитано ✓ <span class="hint">${hint}</span></p><button type="button" class="link-button" data-complete="${esc(lesson.id)}">Снять отметку</button>`;
    const outdated = st === 'outdated'
      ? `<p class="read-state updated">Обновлено</p><details class="more"><summary>Подробнее</summary><p>Вы отмечали версию ${esc(reads[lesson.id + ':' + variant])}, текущая версия ${esc(vOf(lesson).version)}.</p></details>` : '';
    return `${outdated}<button type="button" class="button" data-complete="${esc(lesson.id)}">Отметить прочитанным</button> <span class="hint">${hint}</span>`;
  }
  function readMark(m) {
    const ls = lessonsOf(m).filter(l => isSummary(vOf(l).state));
    if (!ls.length) return '';
    const states = ls.map(l => readState(l));
    if (states.includes('outdated')) return '<span class="read-mark updated">Обновлено</span>';
    return states.every(s => s === 'read') ? '<span class="read-mark">Прочитано</span>' : '';
  }

  // ------------------------------------------------------------ тесты: результат на этом устройстве, отдельно по аудитории и версии теста
  const QUIZ_KEY = 'lmb-academy-quiz-v1';
  let quizzes = {};
  let quizStorageOk = true;
  try { quizzes = JSON.parse(localStorage.getItem(QUIZ_KEY) || '{}') || {}; } catch { quizStorageOk = false; }
  const passMark = n => Math.ceil(n * 0.8);
  const today = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
  const quizRec = (lesson, v = variant) => { const q = vOf(lesson, v).quiz; return q ? (quizzes[lesson.id + ':' + v] || {})[q.version] : null; };
  function quizState(lesson, v = variant) {
    const cur = vOf(lesson, v);
    if (!cur.quiz || !isSummary(cur.state)) return 'none';
    const rec = quizRec(lesson, v);
    if (rec && rec.passedAt) return 'passed';
    return Object.values(quizzes[lesson.id + ':' + v] || {}).some(x => x && x.passedAt) ? 'updated' : 'open';
  }
  function saveAttempt(lesson, score, total) {
    const q = vOf(lesson).quiz, key = lesson.id + ':' + variant;
    const rec = quizzes[key] = quizzes[key] || {};
    const e = rec[q.version] = rec[q.version] || {best: 0};
    // Лучший результат и дата первого прохождения не стираются последующей неудачной попыткой.
    e.best = Math.max(e.best || 0, score); e.total = total; e.lastScore = score; e.lastAt = today();
    if (score >= passMark(total) && !e.passedAt) e.passedAt = today();
    try { localStorage.setItem(QUIZ_KEY, JSON.stringify(quizzes)); return true; } catch { quizStorageOk = false; return false; }
  }
  const passBadge = lesson => { const st = quizState(lesson); return st === 'passed' ? '<span class="pass-mark">Пройдено</span>' : st === 'updated' ? '<span class="read-mark updated">Тест обновлён</span>' : ''; };
  function modulePassMark(m) {
    const ls = lessonsOf(m).filter(l => quizState(l) !== 'none');
    return ls.length && ls.every(l => quizState(l) === 'passed') ? '<span class="pass-mark">Пройдено</span>' : '';
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
      if (hasText(v.state)) parts.push(v.goal, v.takeaway, v.subtitle, v.text);
      searchCache[key] = {all: ' ' + norm(parts.join(' ')) + ' ', title: ' ' + norm(m.title + ' ' + l.title) + ' '};
    }
    return searchCache[key];
  }
  function search(q) {
    const terms = parseQuery(q);
    if (!terms.length) return [];
    return allLessons
      .filter(l => !group || groupOf(moduleById(l.moduleId)) === group)
      .map(l => {
        const t = lessonSearchText(l);
        if (!terms.every(alts => alts.some(a => altMatches(a, t.all)))) return null;
        return {l, module: moduleById(l.moduleId), score: terms.filter(alts => alts.some(a => altMatches(a, t.title))).length};
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score);
  }

  // ------------------------------------------------------------ общие блоки
  function rolebar() {
    return `<div class="roles" role="group" aria-label="Вариант обучения">${D.variants.map(v =>
      `<button type="button" data-role="${v.id}" class="${v.id === variant ? 'selected' : ''}" aria-pressed="${v.id === variant}">${esc(v.label)}</button>`).join('')}</div>`;
  }
  function updateNav(activeModule) {
    nav.innerHTML = groups.map(g => `<p class="nav-group">${esc(g.title)}</p>${modulesIn(g).map(m =>
      `<a href="${moduleHref(m)}" class="${m.id === activeModule ? 'active' : ''}" ${m.id === activeModule ? 'aria-current="page"' : ''}>${icon(m.icon)}<span>${esc(m.title)}</span></a>`).join('')}`).join('');
    const cat = document.getElementById('catalog-link');
    cat.href = href(variant, '');
    cat.classList.toggle('active', !activeModule);
    if (!activeModule) cat.setAttribute('aria-current', 'page'); else cat.removeAttribute('aria-current');
    document.getElementById('brand').href = href(variant, '');
  }
  const lessonRow = l => {
    const v = vOf(l), rs = readState(l);
    return `<li><a href="${href(variant, 'lesson/' + l.id)}"><span class="item-body"><span class="item-title">${esc(l.title)}</span><span class="item-meta">${chip(v.state)}${rs === 'read' ? '<span class="read-mark">Прочитано</span>' : rs === 'outdated' ? '<span class="read-mark updated">Обновлено</span>' : ''}${passBadge(l)}</span></span></a></li>`;
  };

  // ------------------------------------------------------------ каталог
  function renderHome() {
    updateNav();
    document.title = group ? group.title + ' — ЛМБ Академия' : 'ЛМБ Академия';
    main.innerHTML = rolebar() + `<h1 class="page-title">Направления</h1>
      <div class="search"><label for="search">Поиск по темам</label><div class="search-field"><input type="search" id="search" value="${esc(query)}" autocomplete="off"><button type="button" class="search-clear" id="clear-search" aria-label="Очистить поиск" ${query ? '' : 'hidden'}>×</button></div></div>
      <div class="filters" role="group" aria-label="Группы">${[null, ...groups].map(g => `<button type="button" class="filter ${g === group ? 'selected' : ''}" data-group="${g ? g.id : ''}" aria-pressed="${g === group}">${g ? esc(g.title) : 'Все'}</button>`).join('')}</div>
      ${progressLine()}
      <p class="result-count" id="result-count"></p>
      <div id="cards"></div>`;
    renderCards();
    document.getElementById('search').addEventListener('input', e => { query = e.target.value; document.getElementById('clear-search').hidden = !query; renderCards(); });
  }
  // «Пройдено X из Y тем»: Y — опубликованные темы выбранной аудитории, у которых есть тест.
  function progressLine() {
    const withQuiz = allLessons.filter(l => quizState(l) !== 'none');
    if (!withQuiz.length) return '';
    const passed = withQuiz.filter(l => quizState(l) === 'passed').length;
    return `<p class="progress-line">Пройдено ${passed} из ${withQuiz.length} тем <span class="hint">${quizStorageOk ? 'Прогресс сохраняется на этом устройстве' : 'Прогресс не сохраняется: хранилище браузера недоступно'}</span></p>`;
  }
  const section = (g, body) => `<section class="group" aria-labelledby="g-${g.id}"><h2 class="group-title" id="g-${g.id}">${esc(g.title)}</h2>${body}</section>`;
  function renderCards() {
    const box = document.getElementById('cards');
    const count = document.getElementById('result-count');
    if (query.trim()) {
      const hits = search(query);
      box.innerHTML = hits.length ? grouped(hits).map(({g, items}) => section(g, `<ul class="list catalog">${items.map(({l, module: m}) =>
        `<li><a href="${href(variant, 'lesson/' + l.id)}">${icon(m.icon)}<span class="item-body"><span class="item-title">${esc(l.title)}</span>${m.title !== l.title ? `<span class="item-sub">${esc(m.title)}</span>` : ''}<span class="item-meta">${chip(vOf(l).state)}</span></span></a></li>`).join('')}</ul>`)).join('') : emptyState();
      count.textContent = `Найдено тем: ${hits.length}`;
      count.hidden = false;
      live.textContent = `Найдено тем: ${hits.length}`;
      return;
    }
    count.hidden = true;
    const shown = group ? [group] : groups;
    box.innerHTML = shown.map(g => section(g, `<ul class="list catalog">${modulesIn(g).map(m =>
      `<li><a href="${moduleHref(m)}">${icon(m.icon)}<span class="item-body"><span class="item-title">${esc(m.title)}</span><span class="item-meta">${moduleStatus(m)}${readMark(m)}${modulePassMark(m)}</span></span></a></li>`).join('')}</ul>`)).join('');
    live.textContent = `Направлений: ${shown.reduce((n, g) => n + modulesIn(g).length, 0)}`;
  }
  const emptyState = () => `<div class="empty"><p>Ничего не найдено.</p><button type="button" class="button" data-reset>Сбросить поиск и фильтр</button></div>`;
  function setGroup(g, updateUrl) {
    group = g;
    document.querySelectorAll('[data-group]').forEach(el => { const on = el.dataset.group === (g ? g.id : ''); el.classList.toggle('selected', on); el.setAttribute('aria-pressed', String(on)); });
    document.title = group ? group.title + ' — ЛМБ Академия' : 'ЛМБ Академия';
    if (updateUrl) history.replaceState(null, '', groupHref(g));
    renderCards();
  }

  // ------------------------------------------------------------ путь к материалу
  function crumbs(m, withModule) {
    const g = groupOf(m);
    return `<nav class="breadcrumb" aria-label="Путь"><a href="${href(variant, '')}">Направления</a><span aria-hidden="true">/</span><a href="${groupHref(g)}">${esc(g.title)}</a>${withModule ? `<span aria-hidden="true">/</span><a href="${href(variant, 'module/' + m.id)}">${esc(m.title)}</a>` : ''}</nav>`;
  }
  const titleWithIcon = (m, text) => `<h1 class="page-title with-icon">${icon(m.icon, 'ico ico-title')}<span>${esc(text)}</span></h1>`;

  // ------------------------------------------------------------ направление с несколькими темами
  function renderModule(id) {
    const m = moduleById(id);
    if (!m) return renderNotFound();
    const direct = directLesson(m);
    if (direct) {
      // Старые ссылки #module/<id> ведут прямо в единственную тему.
      history.replaceState(null, '', href(variant, 'lesson/' + direct.id));
      return renderLesson(direct.id);
    }
    updateNav(m.id);
    document.title = m.title + ' — ЛМБ Академия';
    const linked = allLessons.filter(l => (l.alsoIn || []).includes(m.id));
    main.innerHTML = rolebar() + crumbs(m, false) + titleWithIcon(m, m.title) + `<p class="lead">${esc(m.lead)}</p>
      <h2 class="list-title">Темы</h2><ul class="list">${lessonsOf(m).map(lessonRow).join('')}</ul>
      ${linked.length ? `<h2 class="list-title">Связанные темы</h2><ul class="list">${linked.map(lessonRow).join('')}</ul>` : ''}`;
    window.scrollTo(0, 0);
    main.focus({preventScroll: true});
  }

  // ------------------------------------------------------------ тема
  // Соседние материалы: темы своего направления, затем направления своей группы. Между группами не переходим.
  function neighbours(l) {
    const g = groupOf(moduleById(l.moduleId));
    const seq = modulesIn(g).flatMap(lessonsOf);
    const i = seq.indexOf(l), prev = seq[i - 1], next = seq[i + 1];
    const back = `<a href="${groupHref(g)}"><small>Назад</small>К направлениям</a>`;
    const fwd = `<a class="next" href="${groupHref(g)}"><small>Далее</small>К направлениям</a>`;
    return `<nav class="pager" aria-label="Соседние материалы">${prev ? `<a href="${href(variant, 'lesson/' + prev.id)}"><small>Назад</small>${esc(prev.title)}</a>` : back}${next ? `<a class="next" href="${href(variant, 'lesson/' + next.id)}"><small>Далее</small>${esc(next.title)}</a>` : fwd}</nav>`;
  }
  let currentLessonId = null;
  function infographicBlock(v) {
    const g = v.infographic;
    if (!g || !g.src) return '';
    return `<section class="infographic" id="block-infographic" aria-labelledby="info-title"><h2 id="info-title">Инфографика</h2>
      <figure class="figure main-figure"><button type="button" class="zoom" data-zoom="${esc(g.src)}" aria-label="Увеличить: ${esc(g.alt)}"><img src="${esc(g.src)}" alt="${esc(g.alt)}" loading="lazy"></button>${g.caption ? `<figcaption>${esc(g.caption)}</figcaption>` : ''}</figure>
      ${g.description ? `<details class="more"><summary>Текстовое описание</summary><p>${esc(g.description)}</p></details>` : ''}</section>`;
  }
  const YT_ID = /^[A-Za-z0-9_-]{11}$/;
  function mediaBlock(v) {
    const items = (v.media || []).filter(x => /^https:\/\//.test(x.url));
    if (!items.length) return '';
    return `<section class="media" id="block-media" aria-labelledby="media-title"><h2 id="media-title">Видео и ссылки</h2><ul class="media-list">${items.map((x, i) => {
      const info = [x.note, x.duration].filter(Boolean).join(' · ');
      let host = ''; try { host = new URL(x.url).hostname.replace(/^www\./, ''); } catch { /* адрес проверен при сборке */ }
      const yt = x.youtubeId && YT_ID.test(x.youtubeId);
      const open = `<a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${yt ? 'Открыть на YouTube' : 'Открыть'}</a>`;
      return `<li><p class="media-title">${esc(x.title)}</p>${info ? `<p class="media-info">${esc(info)}</p>` : ''}
        <p class="media-actions">${yt ? `<button type="button" class="button" data-play="${i}">Смотреть</button>${open}` : `${open}<span class="hint">${esc(host)}</span>`}</p>${yt ? `<div class="video-slot" id="video-${i}"></div>` : ''}</li>`;
    }).join('')}</ul></section>`;
  }
  function quizStatus(l) {
    const st = quizState(l), rec = quizRec(l), n = vOf(l).quiz.questions.length;
    if (st === 'passed') return `<span class="pass-mark">Пройдено</span> Лучший результат: ${rec.best} из ${rec.total}, ${fmtDate(rec.passedAt)}.`;
    if (st === 'updated') return '<span class="read-mark updated">Тест обновлён</span> Пройдите его заново.';
    return `${n} вопросов для самопроверки. Для отметки «Пройдено» нужно ${passMark(n)} правильных ответа из ${n}.`;
  }
  function quizBlock(l) {
    const q = vOf(l).quiz;
    if (!q) return '';
    return `<section class="quiz" id="block-quiz" aria-labelledby="quiz-title"><h2 id="quiz-title">Проверка знаний</h2>
      <p class="quiz-status" id="quiz-status">${quizStatus(l)}</p>
      <form id="quiz-form" data-lesson="${esc(l.id)}" novalidate>${q.questions.map((x, i) => `<fieldset class="question" id="q-${i}"><legend>${i + 1}. ${esc(x.question)}</legend>
        ${x.options.map((o, j) => `<label class="option"><input type="radio" name="q${i}" value="${j}"><span>${esc(o)}</span></label>`).join('')}<p class="feedback" id="fb-${i}" hidden></p></fieldset>`).join('')}
      <div class="quiz-actions"><button type="submit" class="button">Проверить</button></div>
      <div class="quiz-result" id="quiz-result" role="status" aria-live="polite"></div></form></section>`;
  }
  function checkQuiz(form) {
    const l = D.lessons[form.dataset.lesson], q = vOf(l).quiz, n = q.questions.length;
    const answers = q.questions.map((_, i) => { const c = form.querySelector(`input[name="q${i}"]:checked`); return c ? +c.value : null; });
    const missing = answers.map((a, i) => a === null ? i : -1).filter(i => i >= 0);
    const result = document.getElementById('quiz-result');
    if (missing.length) {
      // Неполная попытка не засчитывается.
      result.innerHTML = `<p>Ответьте на все вопросы, чтобы завершить тест. Осталось: ${missing.length}.</p>`;
      form.querySelector(`#q-${missing[0]} input`).focus();
      return;
    }
    let score = 0;
    q.questions.forEach((x, i) => {
      const ok = answers[i] === x.answer;
      if (ok) score++;
      const fb = document.getElementById('fb-' + i);
      fb.hidden = false;
      fb.className = 'feedback ' + (ok ? 'ok' : 'wrong');
      fb.innerHTML = `<strong>${ok ? 'Верно.' : 'Неверно.'}</strong> ${ok ? '' : `Правильный ответ: ${esc(x.options[x.answer])}. `}${esc(x.explanation)}`;
      form.querySelectorAll(`input[name="q${i}"]`).forEach(inp => { inp.disabled = true; inp.closest('.option').classList.toggle('correct', +inp.value === x.answer); });
    });
    const saved = saveAttempt(l, score, n);
    const passed = score >= passMark(n);
    form.querySelector('button[type="submit"]').hidden = true;
    result.innerHTML = `<p class="score"><strong>Правильных ответов: ${score} из ${n}.</strong> ${passed ? 'Тема пройдена.' : `Для прохождения нужно ${passMark(n)}.`}</p>
      ${saved ? '' : '<p class="hint">Результат не сохранится: хранилище браузера недоступно.</p>'}
      <p class="actions"><button type="button" class="button" data-quiz-retry>${passed ? 'Пройти ещё раз' : 'Повторить тест'}</button>${passed ? '' : `<a href="${href(variant, 'lesson/' + l.id + '/block-material')}" data-section="block-material">К материалу</a>`}</p>`;
    document.getElementById('quiz-status').innerHTML = quizStatus(l);
    const slot = document.querySelector('.pass-slot'); if (slot) slot.innerHTML = passBadge(l);
  }
  function renderLesson(id, anchor) {
    const l = D.lessons[id];
    if (!l || !moduleById(l.moduleId)) return renderNotFound();
    const m = moduleById(l.moduleId), v = vOf(l);
    const direct = directLesson(m) === l;
    updateNav(m.id);
    document.title = l.title + ' — ЛМБ Академия';
    const path = crumbs(m, !direct);
    const other = variantIds.find(x => x !== variant);
    const otherAction = hasText(vOf(l, other).state) ? `<a href="${href(other, 'lesson/' + l.id)}">${OPEN_OTHER[other]}</a>` : '';
    const related = (l.related || []).map(rid => D.lessons[rid]).filter(Boolean);
    const relatedBlock = related.length ? `<section class="related"><h2>Связанные темы</h2><ul>${related.map(r => `<li><a href="${href(variant, 'lesson/' + r.id)}">${esc(r.title)}</a></li>`).join('')}</ul></section>` : '';

    if (!isSummary(v.state)) {
      // Программа готовящейся темы, пустая или снятая тема: компактное представление без длинного текста.
      const withdrawn = v.state === 'withdrawn';
      const program = !withdrawn && v.program && v.program.length ? `<h2 class="list-title">Программа</h2><ul class="program">${v.program.map(p => `<li>${esc(p)}</li>`).join('')}</ul>` : '';
      main.innerHTML = rolebar() + `<article class="lesson">${path}${titleWithIcon(m, l.title)}
        <p class="lesson-meta">${chip(v.state)}</p>
        ${withdrawn ? (v.withdrawnNote ? `<p>${esc(v.withdrawnNote)}</p>` : '') : `<p class="lead">${esc(m.lead)}</p>`}
        ${program}${relatedBlock}
        <p class="actions"><a href="${groupHref(groupOf(m))}">К направлениям</a>${otherAction}</p>${neighbours(l)}</article>`;
      return focusTop(anchor);
    }

    const toc = v.toc || [];
    const tocLinks = toc.map(t => `<a href="${href(variant, 'lesson/' + l.id + '/' + t.id)}" data-section="${t.id}">${esc(t.title)}</a>`).join('');
    const about = [
      ['Версия', v.version],
      v.scope && ['Основа', v.scope],
      (v.coverage || []).length && ['Охват', v.coverage.map(c => COVERAGE[c] || c).join(', ')],
      v.approval && ['Проверено', `${v.approval.reviewer}, ${fmtDate(v.approval.date)}`],
      v.nextReviewAt && ['Плановый пересмотр', fmtDate(v.nextReviewAt)],
      v.derivedFrom && v.derivedFrom.version && ['Основа выжимки', 'врачебная версия ' + v.derivedFrom.version],
      v.needsSync && ['Сверка', 'Врачебная версия обновлена, выжимка ожидает сверки'],
      v.fallbackNote && ['Редакция', v.fallbackNote]
    ].filter(Boolean);
    const sources = (v.sources || []).map(s => { const src = D.sources[s.id] || {title: s.id};
      const info = [src.type, src.author, src.year, s.locator].filter(Boolean).join(' · ');
      return `<li>${src.url ? `<a href="${esc(src.url)}" target="_blank" rel="noopener noreferrer">${esc(src.title)}</a>` : esc(src.title)}${info ? `<span class="source-info">${esc(info)}</span>` : ''}${s.supports ? `<span class="source-info">${esc(s.supports)}</span>` : ''}</li>`; }).join('');

    // Блоки учебного пакета показываются, только если заполнены; ссылки-якоря — только на них.
    const jumps = [['block-material', 'Материал'], v.briefHtml && ['block-brief', 'За 2 минуты'], v.infographic && ['block-infographic', 'Инфографика'],
      v.media && v.media.length && ['block-media', 'Видео'], v.quiz && ['block-quiz', 'Тест']].filter(Boolean);
    const jumpNav = jumps.length > 1 ? `<nav class="jump-nav" aria-label="Блоки темы">${jumps.map(([bid, t]) => `<a href="${href(variant, 'lesson/' + l.id + '/' + bid)}" data-section="${bid}">${t}</a>`).join('')}</nav>` : '';
    currentLessonId = l.id;

    main.innerHTML = rolebar() + `<article class="lesson">${path}
      <header class="lesson-head">${titleWithIcon(m, l.title)}
      <p class="lesson-meta">${chip(v.state)}<span class="pass-slot">${passBadge(l)}</span>${v.subtitle ? `<span>${esc(v.subtitle)}</span>` : ''}${v.updatedAt ? `<span>Обновлено ${fmtDate(v.updatedAt)}</span>` : ''}</p></header>
      ${jumpNav}
      <div class="lesson-layout"><div class="lesson-body">
      ${v.takeaway ? `<p class="takeaway"><strong>Главное.</strong> ${esc(v.takeaway)}</p>` : ''}
      <div class="material" id="block-material">
      ${v.introHtml ? `<div class="text intro">${v.introHtml}</div>` : ''}
      ${toc.length > 1 ? `<details class="toc-mobile"><summary>Содержание</summary><nav aria-label="Содержание">${tocLinks}</nav></details>` : ''}
      <div class="text">${v.html}</div></div>
      ${v.briefHtml ? `<section class="brief" id="block-brief" aria-labelledby="brief-title"><h2 id="brief-title">За 2 минуты</h2><div class="text">${v.briefHtml}</div></section>` : ''}
      ${infographicBlock(v)}${mediaBlock(v)}${quizBlock(l)}
      ${sources ?`<details class="block"><summary>Источники</summary><ul class="sources">${sources}</ul></details>` : ''}
      ${relatedBlock}
      <div class="lesson-actions"><div class="read-box">${readBlock(l)}</div>${embedded ? '' : '<button type="button" class="link-button" data-print>Печать</button>'}${otherAction}</div>
      <details class="block about"><summary>О материале</summary><dl>${about.map(([k, val]) => `<dt>${esc(k)}</dt><dd>${esc(val)}</dd>`).join('')}</dl></details>
      ${neighbours(l)}</div>
      ${toc.length > 1 ? `<aside class="toc"><h2>Содержание</h2><nav aria-label="Содержание">${tocLinks}</nav></aside>` : ''}</div></article>`;
    focusTop(anchor);
  }
  function focusTop(anchor) {
    const target = anchor && document.getElementById(anchor);
    if (target) target.scrollIntoView({block: 'start'}); else window.scrollTo(0, 0);
    main.focus({preventScroll: true});
  }
  function renderNotFound() {
    updateNav();
    document.title = 'Раздел не найден — ЛМБ Академия';
    main.innerHTML = rolebar() + `<h1 class="page-title">Раздел не найден</h1><p class="actions"><a href="${href(variant, '')}">К направлениям</a></p>`;
  }

  // ------------------------------------------------------------ маршруты
  // #, #admins, [#admins/]group/ID, [#admins/]module/ID, [#admins/]lesson/ID[/section-N]. Старые маршруты сохраняются.
  function route() {
    let h = decodeURIComponent(location.hash.slice(1));
    if (/^section-\d+$/.test(h)) return;
    variant = /^admins(\/|$)/.test(h) ? 'admins' : 'doctors';
    h = h.replace(/^admins\/?/, '');
    const parts = h.split('/');
    if (!h) { group = null; renderHome(); window.scrollTo(0, 0); }
    else if (parts[0] === 'group' && groups.some(g => g.id === parts[1])) { group = groups.find(g => g.id === parts[1]); renderHome(); window.scrollTo(0, 0); }
    else if (parts[0] === 'module' && parts[1]) renderModule(parts[1]);
    else if (parts[0] === 'lesson' && parts[1]) renderLesson(parts[1], parts[2]);
    else renderNotFound();
    closeMenu();
  }
  function closeMenu() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('menu-toggle').setAttribute('aria-expanded', 'false');
  }

  document.addEventListener('click', e => {
    const role = e.target.closest('[data-role]');
    if (role) {
      const rest = decodeURIComponent(location.hash.slice(1)).replace(/^admins\/?/, '');
      const dest = href(role.dataset.role, rest);
      if (dest === location.hash || (dest === '#' && !location.hash)) route(); else location.hash = dest;
      return;
    }
    const filter = e.target.closest('[data-group]');
    if (filter) { setGroup(groups.find(g => g.id === filter.dataset.group) || null, true); return; }
    if (e.target.closest('[data-reset]')) { query = ''; group = null; history.replaceState(null, '', href(variant, '')); renderHome(); document.getElementById('search').focus(); return; }
    if (e.target.closest('#clear-search')) { query = ''; const s = document.getElementById('search'); s.value = ''; e.target.closest('#clear-search').hidden = true; renderCards(); s.focus(); return; }
    if (e.target.closest('[data-print]')) { window.print(); return; }
    const sec = e.target.closest('[data-section]');
    if (sec) {
      e.preventDefault();
      const el = document.getElementById(sec.dataset.section);
      if (el) {
        el.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start'});
        history.pushState(null, '', sec.getAttribute('href'));
        el.setAttribute('tabindex', '-1'); el.focus({preventScroll: true});
        const mob = sec.closest('.toc-mobile'); if (mob) mob.open = false;
      }
      return;
    }
    const zoomBtn = e.target.closest('[data-zoom]');
    if (zoomBtn) { openZoom(zoomBtn); return; }
    if (e.target.closest('#zoom-close') || e.target === zoomDialog) { zoomDialog.close(); return; }
    const play = e.target.closest('[data-play]');
    if (play) {
      const x = (vOf(D.lessons[currentLessonId]).media || []).filter(y => /^https:\/\//.test(y.url))[+play.dataset.play];
      const slot = document.getElementById('video-' + play.dataset.play);
      if (x && slot && YT_ID.test(x.youtubeId || '')) {
        const src = `https://www.youtube-nocookie.com/embed/${x.youtubeId}?rel=0${x.start ? '&start=' + Number(x.start) : ''}`;
        slot.innerHTML = `<div class="video"><iframe src="${src}" title="${esc(x.title)}" allow="encrypted-media; picture-in-picture; fullscreen" allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe></div>`;
        play.hidden = true;
        slot.querySelector('iframe').focus();
      }
      return;
    }
    if (e.target.closest('[data-quiz-retry]')) {
      const sec = document.getElementById('block-quiz');
      sec.outerHTML = quizBlock(D.lessons[currentLessonId]);
      const first = document.querySelector('#quiz-form input'); if (first) { first.focus(); document.getElementById('block-quiz').scrollIntoView({block: 'start'}); }
      return;
    }
    const complete = e.target.closest('[data-complete]');
    if (complete) {
      const l = D.lessons[complete.dataset.complete];
      toggleRead(l);
      document.querySelectorAll('.read-box').forEach(box => { box.innerHTML = readBlock(l); });
      live.textContent = readState(l) === 'read' ? 'Отмечено как прочитанное' : 'Отметка снята';
      const btn = document.querySelector('.read-box [data-complete]'); if (btn) btn.focus();
    }
  });
  document.addEventListener('submit', e => {
    const form = e.target.closest('#quiz-form');
    if (form) { e.preventDefault(); checkQuiz(form); }
  });
  // Увеличенное изображение: системный диалог, закрывается кнопкой, Esc и щелчком по фону; фокус возвращается.
  const zoomDialog = document.getElementById('zoom');
  let zoomTrigger = null;
  function openZoom(btn) {
    const img = btn.querySelector('img');
    const big = document.getElementById('zoom-img');
    big.src = btn.dataset.zoom; big.alt = img ? img.alt : '';
    const open = document.getElementById('zoom-open');
    open.href = btn.dataset.zoom; open.hidden = embedded;
    zoomTrigger = btn;
    if (typeof zoomDialog.showModal === 'function') { zoomDialog.showModal(); document.getElementById('zoom-close').focus(); }
    else window.open(btn.dataset.zoom, '_blank', 'noopener');
  }
  zoomDialog.addEventListener('close', () => { if (zoomTrigger) zoomTrigger.focus(); zoomTrigger = null; });
  document.getElementById('menu-toggle').addEventListener('click', e => {
    const open = document.getElementById('sidebar').classList.toggle('open');
    e.currentTarget.setAttribute('aria-expanded', String(open));
  });
  document.querySelector('.skip-link').addEventListener('click', e => { e.preventDefault(); main.focus(); main.scrollIntoView({block: 'start'}); });
  document.getElementById('mode-label').hidden = D.build.mode !== 'preview';
  window.addEventListener('beforeprint', () => document.querySelectorAll('details.block').forEach(d => { d.open = true; }));
  window.addEventListener('hashchange', route);
  route();
})();
