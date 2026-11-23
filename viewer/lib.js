// "Projekty" menu shared by the 3D viewer and the canvas: every model and canvas file in the project folder, to open with one click.
(() => {
  const bar = document.getElementById('bar'), sp = bar && bar.querySelector('.sp');
  if (!bar) return;
  const onCanvas = location.pathname.startsWith('/canvas');
  const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids.flat().filter(k => k != null)); return e; };
  const post = async (url, body) => { const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`); return j; };
  const ago = t => { const s = Date.now() / 1000 - t; return s < 90 ? 'právě teď' : s < 5400 ? `${Math.round(s / 60)} min` : s < 129600 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} d`; };
  const kb = n => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1e3))} kB`);

  const btn = el('button', { id: 'bLib', title: 'Projekty: modely a plátna k otevření' });
  btn.innerHTML = '<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"><path d="M8 1.5l6 3-6 3-6-3z"/><path d="M2 8l6 3 6-3M2 11.5l6 3 6-3"/></svg>';
  const grp = el('div', { className: 'grp' }, el('span', { className: 'cap', textContent: 'Projekty' }), el('div', { className: 'tb', style: 'display:flex;align-items:center' }, btn));
  if (!document.querySelector('#bar .cap')) grp.querySelector('.cap').remove(); // the viewer toolbar has no captions
  bar.insertBefore(grp, sp || null);

  const menu = el('div', { id: 'menuLib', style: 'position:fixed;z-index:70;display:none;width:min(360px,calc(100vw - 16px));max-height:calc(100vh - 80px);overflow:auto;background:var(--panel);border:1px solid var(--line2);border-radius:12px;padding:10px;box-shadow:0 12px 32px rgba(0,0,0,.45);font-size:12px;color:var(--text)' });
  document.body.append(menu);
  const row = (main, sub, on, extra, cur) => el('div', { style: `display:flex;align-items:center;gap:4px;border-radius:8px;${cur ? 'background:var(--accent-bg);' : ''}` },
    el('button', { className: 'ghost', style: 'flex:1;min-width:0;display:flex;flex-direction:column;align-items:flex-start;height:auto;padding:4px 8px;text-align:left', title: sub, onclick: on },
      el('span', { textContent: main, style: 'max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap' }), el('span', { textContent: sub, style: 'color:var(--faint);font-size:11px' })), extra);
  const head = t => el('div', { textContent: t, style: 'color:var(--faint);text-transform:uppercase;letter-spacing:.07em;font-size:10px;margin:8px 4px 2px' });
  const flash = msg => { const t = document.getElementById('toast'); if (t) { t.textContent = msg; t.style.display = 'block'; setTimeout(() => { t.style.display = 'none'; }, 2500); } };

  async function fill() {
    menu.replaceChildren(el('div', { textContent: 'Načítám…', style: 'color:var(--faint)' }));
    let lib;
    try { lib = await (await fetch('/api/library')).json(); } catch { menu.replaceChildren(el('div', { textContent: 'Seznam se nepodařilo načíst' })); return; }
    const q = el('input', { type: 'text', placeholder: 'Hledat…', style: 'width:100%;box-sizing:border-box;margin-bottom:2px' });
    const models = lib.models.map(m => ({ m, node: row(`${m.name}${m.variants.length ? `  ·  ${m.variants.length} var.` : ''}`, `${m.path.replace(lib.root, '.')} · ${kb(m.size)} · ${ago(m.mtime)}`, async () => {
      try { await post('/api/open', { path: m.path }); } catch (e) { flash(e.message); return; }
      if (onCanvas) location.href = '/'; else { menu.style.display = 'none'; flash(`Otevřeno: ${m.name}`); }
    }, null, m.path === lib.current) }));
    const canvases = lib.canvases.map(c => ({ m: c, node: row(c.name, `${c.path.replace(lib.root, '.')} · ${ago(c.mtime)} · klik = nahradit plátno`, async () => {
      try { await post('/api/canvas/file/open', { path: c.path, mode: 'replace' }); } catch (e) { flash(e.message); return; }
      if (onCanvas) { menu.style.display = 'none'; flash('Plátno otevřeno'); setTimeout(() => document.getElementById('bFit')?.click(), 600); } else location.href = '/canvas';
    }, el('button', { className: 'ghost', textContent: '+', title: 'Vložit k aktuálnímu plátnu', onclick: async () => { try { await post('/api/canvas/file/open', { path: c.path, mode: 'add' }); flash('Vloženo do plátna'); } catch (e) { flash(e.message); } } })) }));
    const empty = t => el('div', { textContent: t, style: 'color:var(--faint);padding:2px 8px' });
    const list = el('div');
    const draw = () => {
      const f = q.value.trim().toLowerCase(), ok = x => !f || x.m.name.toLowerCase().includes(f);
      const ms = models.filter(ok), cs = canvases.filter(ok);
      list.replaceChildren(head('3D modely'), ...(ms.length ? ms.map(x => x.node) : [empty('Žádný model')]), head('Plátna (.platno.json)'), ...(cs.length ? cs.map(x => x.node) : [empty('Žádný soubor plátna. Ulož ho přes Soubor › Uložit.')]));
    };
    q.oninput = draw; draw();
    const mk = (t, f) => el('button', { className: 'ghost', textContent: t, style: 'flex:1', onclick: f });
    // confirm() / prompt() are blocked in some embedded browsers, so confirmation and the model brief live inside the menu
    const twice = (btn, label, run) => { const t0 = btn.textContent; let tm; btn.onclick = () => { if (btn.dataset.arm) { clearTimeout(tm); delete btn.dataset.arm; btn.textContent = t0; run(); return; } btn.dataset.arm = 1; btn.textContent = label; tm = setTimeout(() => { delete btn.dataset.arm; btn.textContent = t0; }, 4000); }; return btn; };
    const bNew = twice(mk('+ Nové plátno'), 'Smazat? Klikni znovu', async () => {
      try {
        await post('/api/canvas/snapshot', { name: 'před novým plátnem' });
        const cur = await (await fetch('/api/canvas?since=0')).json();
        await post('/api/canvas/ops', { del: cur.objs.filter(o => !o.deleted).map(o => o.id) });
      } catch (e) { flash(e.message); return; }
      if (onCanvas) location.reload(); else location.href = '/canvas';
    });
    const nm = el('input', { type: 'text', placeholder: 'Název (např. drzak_kabelu)', style: 'width:100%;box-sizing:border-box' });
    const tx = el('textarea', { placeholder: 'Co to má být? Rozměry, účel, materiál…', rows: 3, style: 'width:100%;box-sizing:border-box;margin-top:4px;resize:vertical' });
    const form = el('div', { style: 'display:none;margin-bottom:6px' }, nm, tx, mk('Poslat zadání do chatu', async () => {
      try { await post('/api/new/model', { name: nm.value, text: tx.value }); menu.style.display = 'none'; flash('Zadání je ve zprávě v chatu, odešli ji tam.'); } catch (e) { flash(e.message); }
    }));
    const newBar = el('div', {}, el('div', { style: 'display:flex;gap:6px;margin-bottom:6px' }, bNew, mk('+ Nový model', () => { form.style.display = form.style.display === 'none' ? 'block' : 'none'; if (form.style.display === 'block') nm.focus(); })), form);
    menu.replaceChildren(newBar, q, list, el('div', { textContent: lib.root, style: 'color:var(--faint);font-size:10px;margin:8px 4px 0;word-break:break-all' }));
  }
  btn.addEventListener('click', () => {
    if (menu.style.display === 'block') { menu.style.display = 'none'; return; }
    const b = btn.getBoundingClientRect();
    menu.style.display = 'block'; menu.style.top = `${b.bottom + 6}px`; menu.style.left = `${Math.max(8, Math.min(b.left - 8, innerWidth - menu.offsetWidth - 8))}px`;
    fill();
  });
  document.addEventListener('pointerdown', e => { if (!menu.contains(e.target) && !btn.contains(e.target)) menu.style.display = 'none'; });
  addEventListener('resize', () => { menu.style.display = 'none'; });
})();
