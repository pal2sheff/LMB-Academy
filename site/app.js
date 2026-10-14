(() => {
  'use strict';
  const D = window.LMB_DATA;
  const main = document.getElementById('main');
  const nav = document.getElementById('module-nav');
  const live = document.getElementById('live');
  const embedded = !!window.LMB_EMBEDDED;

  const modules = D.modules.filter(m => m.lessons.some(id => D.lessons[id]));
  const lessonsOf = m => m.lessons.map(id => D.lessons[id]).filter(Boolean).sort((a, b) => a.order - b.order);
  const allLessons = modules.flatMap(lessonsOf);
  const moduleById = id => modules.find(m => m.id === id);
  const categories = ['Все', ...new Set(modules.map(m => m.category))];
  const variantIds = D.variants.map(v => v.id);
  const OPEN_OTHER = {doctors: 'Открыть врачебный материал', admins: 'Открыть материал для администраторов'};

  let variant = 'doctors';
  let category = 'Все';
  let query = '';

  // ------------------------------------------------------------ утилиты
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmtDate = iso => iso ? iso.split('-').reverse().join('.') : '';
  const href = (v, path) => '#' + (v === 'admins' ? 'admins' + (path ? '/' + path : '') : (path || ''));

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

  // ------------------------------------------------------------ отметки о прочтении (локально, по версии)
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
      .filter(l => category === 'Все' || moduleById(l.moduleId).category === category)
      .map(l => {
        const t = lessonSearchText(l);
        if (!terms.every(alts => alts.some(a => altMatches(a, t.all)))) return null;
        return {l, score: terms.filter(alts => alts.some(a => altMatches(a, t.title))).length};
      })
      .filter(Boolean)
      .sort((a, b) => b.score - a.score)
      .map(x => x.l);
  }

  // ------------------------------------------------------------ общие блоки
  function rolebar() {
    return `<div class="roles" role="group" aria-label="Вариант обучения">${D.variants.map(v =>
      `<button type="button" data-role="${v.id}" class="${v.id === variant ? 'selected' : ''}" aria-pressed="${v.id === variant}">${esc(v.label)}</button>`).join('')}</div>`;
  }
  function updateNav(activeModule) {
    nav.innerHTML = modules.map(m => `<a href="${moduleHref(m)}" class="${m.id === activeModule ? 'active' : ''}" ${m.id === activeModule ? 'aria-current="page"' : ''}>${esc(m.title)}</a>`).join('');
    const cat = document.getElementById('catalog-link');
    cat.href = href(variant, '');
    cat.classList.toggle('active', !activeModule);
    if (!activeModule) cat.setAttribute('aria-current', 'page'); else cat.removeAttribute('aria-current');
    document.getElementById('brand').href = href(variant, '');
  }
  const lessonRow = l => {
    const v = vOf(l), rs = readState(l);
    return `<li><a href="${href(variant, 'lesson/' + l.id)}"><span class="item-title">${esc(l.title)}</span><span class="item-meta">${chip(v.state)}${rs === 'read' ? '<span class="read-mark">Прочитано</span>' : rs === 'outdated' ? '<span class="read-mark updated">Обновлено</span>' : ''}</span></a></li>`;
  };

  // ------------------------------------------------------------ каталог
  function renderHome() {
    updateNav();
    document.title = 'ЛМБ Академия';
    main.innerHTML = rolebar() + `<h1 class="page-title">Направления</h1>
      <div class="search"><label for="search">Поиск по темам</label><div class="search-field"><input type="search" id="search" value="${esc(query)}" autocomplete="off"><button type="button" class="search-clear" id="clear-search" aria-label="Очистить поиск" ${query ? '' : 'hidden'}>×</button></div></div>
      <div class="filters" role="group" aria-label="Категории">${categories.map(c => `<button type="button" class="filter ${c === category ? 'selected' : ''}" data-category="${esc(c)}" aria-pressed="${c === category}">${esc(c)}</button>`).join('')}</div>
      <p class="result-count" id="result-count"></p>
      <div id="cards"></div>`;
    renderCards();
    document.getElementById('search').addEventListener('input', e => { query = e.target.value; document.getElementById('clear-search').hidden = !query; renderCards(); });
  }
  function renderCards() {
    const box = document.getElementById('cards');
    const count = document.getElementById('result-count');
    if (query.trim()) {
      const hits = search(query);
      box.innerHTML = hits.length ? `<ul class="list">${hits.map(l => { const m = moduleById(l.moduleId), v = vOf(l);
        return `<li><a href="${href(variant, 'lesson/' + l.id)}"><span class="item-title">${esc(l.title)}</span>${m.title !== l.title ? `<span class="item-sub">${esc(m.title)}</span>` : ''}<span class="item-meta">${chip(v.state)}</span></a></li>`; }).join('')}</ul>` : emptyState();
      count.textContent = `Найдено тем: ${hits.length}`;
      count.hidden = false;
      live.textContent = `Найдено тем: ${hits.length}`;
      return;
    }
    const list = modules.filter(m => category === 'Все' || m.category === category);
    count.hidden = true;
    box.innerHTML = list.length ? `<ul class="list catalog">${list.map(m => `<li><a href="${moduleHref(m)}"><span class="item-title">${esc(m.title)}</span><span class="item-meta">${moduleStatus(m)}${readMark(m)}</span></a></li>`).join('')}</ul>` : emptyState();
    live.textContent = `Направлений: ${list.length}`;
  }
  const emptyState = () => `<div class="empty"><p>Ничего не найдено.</p><button type="button" class="button" data-reset>Сбросить поиск и фильтр</button></div>`;

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
    main.innerHTML = rolebar() + `<nav class="breadcrumb" aria-label="Путь"><a href="${href(variant, '')}">Направления</a></nav>
      <h1 class="page-title">${esc(m.title)}</h1><p class="lead">${esc(m.lead)}</p>
      <h2 class="list-title">Темы</h2><ul class="list">${lessonsOf(m).map(lessonRow).join('')}</ul>
      ${linked.length ? `<h2 class="list-title">Связанные темы</h2><ul class="list">${linked.map(lessonRow).join('')}</ul>` : ''}`;
    window.scrollTo(0, 0);
    main.focus({preventScroll: true});
  }

  // ------------------------------------------------------------ тема
  function neighbours(l) {
    const i = allLessons.indexOf(l), prev = allLessons[i - 1], next = allLessons[i + 1];
    return `<nav class="pager" aria-label="Соседние материалы">${prev ? `<a href="${href(variant, 'lesson/' + prev.id)}"><small>Назад</small>${esc(prev.title)}</a>` : '<span></span>'}${next ? `<a class="next" href="${href(variant, 'lesson/' + next.id)}"><small>Далее</small>${esc(next.title)}</a>` : ''}</nav>`;
  }
  function renderLesson(id, anchor) {
    const l = D.lessons[id];
    if (!l || !moduleById(l.moduleId)) return renderNotFound();
    const m = moduleById(l.moduleId), v = vOf(l);
    const direct = directLesson(m) === l;
    updateNav(m.id);
    document.title = l.title + ' — ЛМБ Академия';
    const crumbs = `<nav class="breadcrumb" aria-label="Путь"><a href="${href(variant, '')}">Направления</a>${direct ? '' : `<span aria-hidden="true">/</span><a href="${href(variant, 'module/' + m.id)}">${esc(m.title)}</a>`}</nav>`;
    const other = variantIds.find(x => x !== variant);
    const otherAction = hasText(vOf(l, other).state) ? `<a href="${href(other, 'lesson/' + l.id)}">${OPEN_OTHER[other]}</a>` : '';

    if (!hasText(v.state)) {
      const withdrawn = v.state === 'withdrawn';
      main.innerHTML = rolebar() + crumbs + `<article class="lesson"><h1 class="page-title">${esc(l.title)}</h1>
        <p class="state-line">${withdrawn ? 'Недоступно' : 'Материал готовится'}</p>
        ${withdrawn && v.withdrawnNote ? `<p>${esc(v.withdrawnNote)}</p>` : ''}
        ${!withdrawn && v.program && v.program.length ? `<h2 class="list-title">Запланированные разделы</h2><ul class="program">${v.program.map(p => `<li>${esc(p)}</li>`).join('')}</ul>` : ''}
        <p class="actions"><a href="${href(variant, '')}">К направлениям</a>${otherAction}</p>${neighbours(l)}</article>`;
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
    const related = (l.related || []).map(rid => D.lessons[rid]).filter(Boolean);

    main.innerHTML = rolebar() + `<article class="lesson">${crumbs}
      <header class="lesson-head"><h1 class="page-title">${esc(l.title)}</h1>
      <p class="lesson-meta">${chip(v.state)}${v.subtitle ? `<span>${esc(v.subtitle)}</span>` : ''}${v.updatedAt ? `<span>Обновлено ${fmtDate(v.updatedAt)}</span>` : ''}</p></header>
      <div class="lesson-layout"><div class="lesson-body">
      ${v.state !== 'outline' && v.takeaway ? `<p class="takeaway"><strong>Главное.</strong> ${esc(v.takeaway)}</p>` : ''}
      ${toc.length > 1 ? `<details class="toc-mobile"><summary>Содержание</summary><nav aria-label="Содержание">${tocLinks}</nav></details>` : ''}
      <div class="text">${v.html}</div>
      ${sources ? `<details class="block"><summary>Источники</summary><ul class="sources">${sources}</ul></details>` : ''}
      ${related.length ? `<section class="related"><h2>Связанные темы</h2><ul>${related.map(r => `<li><a href="${href(variant, 'lesson/' + r.id)}">${esc(r.title)}</a></li>`).join('')}</ul></section>` : ''}
      <div class="lesson-actions">${isSummary(v.state) ? `<div class="read-box">${readBlock(l)}</div>` : ''}${embedded ? '' : '<button type="button" class="link-button" data-print>Печать</button>'}${otherAction}</div>
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
  // #, #admins, [#admins/]module/ID, [#admins/]lesson/ID[/section-N]. Старый маршрут #module/ID сохраняется.
  function route() {
    let h = decodeURIComponent(location.hash.slice(1));
    if (/^section-\d+$/.test(h)) return;
    variant = /^admins(\/|$)/.test(h) ? 'admins' : 'doctors';
    h = h.replace(/^admins\/?/, '');
    const parts = h.split('/');
    if (!h) { renderHome(); window.scrollTo(0, 0); }
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
        history.pushState(null, '', section.getAttribute('href'));
        el.setAttribute('tabindex', '-1'); el.focus({preventScroll: true});
        const mob = section.closest('.toc-mobile'); if (mob) mob.open = false;
      }
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
