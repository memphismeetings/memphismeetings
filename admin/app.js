const state = {
  meeting: null,
  annotation: null,
  index: 0,
  storageKey: null,
};

const CUSTOM_SPEAKER = '__custom__';
const MEMPHIS_CITY_COUNCIL_ID = 'memphis-city-council';
const CURRENT_COUNCILPEOPLE = [
  { id: 'jana-swearengen-washington', name: 'Jana Swearengen Washington' },
  { id: 'rhonda-logan', name: 'Rhonda Logan' },
  { id: 'jerri-green', name: 'Jerri Green' },
  { id: 'pearl-eva-walker', name: 'Pearl Eva Walker' },
  { id: 'philip-spinosa', name: 'Philip Spinosa' },
  { id: 'edmund-ford-sr', name: 'Edmund Ford, Sr.' },
  { id: 'michalyn-easter-thomas', name: 'Michalyn Easter-Thomas' },
  { id: 'jb-smiley-jr', name: 'JB Smiley, Jr.' },
  { id: 'janika-white', name: 'Janika White' },
  { id: 'yolanda-cooper-sutton', name: 'Yolanda Cooper-Sutton' },
  { id: 'chase-carlisle', name: 'Chase Carlisle' },
  { id: 'j-ford-canale', name: 'J. Ford Canale' },
  { id: 'jeff-warren', name: 'Dr. Jeff Warren' },
];

const els = {
  meetingFile: document.querySelector('#meetingFile'),
  annotationFile: document.querySelector('#annotationFile'),
  loadBtn: document.querySelector('#loadBtn'),
  status: document.querySelector('#status'),
  editor: document.querySelector('#editor'),
  progress: document.querySelector('#progress'),
  videoFrame: document.querySelector('#videoFrame'),
  syncVideoBtn: document.querySelector('#syncVideoBtn'),
  autoSyncVideo: document.querySelector('#autoSyncVideo'),
  openVideoLink: document.querySelector('#openVideoLink'),
  chunkTitle: document.querySelector('#chunkTitle'),
  linesGrid: document.querySelector('#linesGrid'),
  turnCount: document.querySelector('#turnCount'),
  displayMode: document.querySelector('#displayMode'),
  displayText: document.querySelector('#displayText'),
  displayPreview: document.querySelector('#displayPreview'),
  applyModeBtn: document.querySelector('#applyModeBtn'),
  resetDisplayBtn: document.querySelector('#resetDisplayBtn'),
  summary: document.querySelector('#summary'),
  tags: document.querySelector('#tags'),
  mentions: document.querySelector('#mentions'),
  newMemberName: document.querySelector('#newMemberName'),
  addMemberBtn: document.querySelector('#addMemberBtn'),
  votes: document.querySelector('#votes'),
  notes: document.querySelector('#notes'),
  prevBtn: document.querySelector('#prevBtn'),
  nextBtn: document.querySelector('#nextBtn'),
  saveBtn: document.querySelector('#saveBtn'),
  downloadBtn: document.querySelector('#downloadBtn'),
  addVoteBtn: document.querySelector('#addVoteBtn'),
};

function secToClock(seconds) {
  const total = Math.floor(Number(seconds || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  return `${m}:${String(s).padStart(2, '0')}`;
}

async function readJSON(fileInput) {
  const file = fileInput.files[0];
  if (!file) return null;
  const text = await file.text();
  return JSON.parse(text);
}

function parseTurns(rawText) {
  return String(rawText || '')
    .split(/\s*>>\s*/)
    .map((t) => t.trim())
    .filter(Boolean)
    .map((text) => ({ text, speaker_id: '', speaker_name: '' }));
}

function buildEmptyAnnotation(meeting) {
  return {
    meeting_id: meeting.id,
    councilpeople: (meeting.councilpeople || []).map((p) => ({ id: p.id, name: p.name })),
    meeting_summary: '',
    global_tags: [],
    sections: meeting.transcript.map((c) => ({
      chunk_index: c.chunk_index,
      speaker_id: '',
      speaker_name: '',
      lines: parseTurns(c.text),
      display_mode: 'raw',
      display_text: '',
      summary: '',
      tags: [],
      mentions: [],
      votes: [],
      notes: '',
    })),
  };
}

function normalizeAnnotation(meeting, annotationInput) {
  const fallback = buildEmptyAnnotation(meeting);
  const annotation = (annotationInput && typeof annotationInput === 'object' && !Array.isArray(annotationInput))
    ? annotationInput
    : {};
  const rawSections = Array.isArray(annotation.sections)
    ? annotation.sections
    : (Array.isArray(annotation.chunks) ? annotation.chunks : []);

  return {
    meeting_id: annotation.meeting_id || meeting.id,
    councilpeople: Array.isArray(annotation.councilpeople) ? annotation.councilpeople : fallback.councilpeople,
    meeting_summary: String(annotation.meeting_summary || ''),
    global_tags: Array.isArray(annotation.global_tags) ? annotation.global_tags : [],
    sections: rawSections,
  };
}

function slugifyId(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function mergeCouncilpeople(...groups) {
  const out = [];
  const seen = new Set();
  for (const group of groups) {
    for (const person of group || []) {
      const id = String(person.id || '').trim();
      const name = String(person.name || '').trim();
      if (!id || !name || seen.has(id)) continue;
      seen.add(id);
      out.push({ id, name });
    }
  }
  out.sort((a, b) => a.name.localeCompare(b.name));
  return out;
}

function normalizeCouncilpeople(meeting, annotation) {
  const defaults = meeting.body_id === MEMPHIS_CITY_COUNCIL_ID ? CURRENT_COUNCILPEOPLE : [];
  const merged = mergeCouncilpeople(defaults, meeting.councilpeople, annotation.councilpeople);
  meeting.councilpeople = merged;
  annotation.councilpeople = merged;
}

function addCouncilperson(name) {
  const cleanName = String(name || '').trim();
  if (!cleanName || !state.meeting || !state.annotation) return false;

  const byName = (state.meeting.councilpeople || []).some((p) => p.name.toLowerCase() === cleanName.toLowerCase());
  if (byName) return false;

  const base = slugifyId(cleanName) || 'member';
  let nextId = base;
  let i = 2;
  const existingIds = new Set((state.meeting.councilpeople || []).map((p) => p.id));
  while (existingIds.has(nextId)) {
    nextId = `${base}-${i}`;
    i += 1;
  }

  const added = { id: nextId, name: cleanName };
  state.meeting.councilpeople = mergeCouncilpeople(state.meeting.councilpeople, [added]);
  state.annotation.councilpeople = mergeCouncilpeople(state.annotation.councilpeople, [added]);
  return true;
}

function sectionAt(index) {
  const chunk = state.meeting.transcript[index];
  if (!Array.isArray(state.annotation.sections)) {
    state.annotation.sections = [];
  }
  let section = state.annotation.sections.find((s) => s.chunk_index === chunk.chunk_index);
  if (!section) {
    section = {
      chunk_index: chunk.chunk_index,
      speaker_id: '',
      speaker_name: '',
      lines: parseTurns(chunk.text),
      display_mode: 'raw',
      display_text: '',
      summary: '',
      tags: [],
      mentions: [],
      votes: [],
      notes: '',
    };
    state.annotation.sections.push(section);
  } else if (!section.lines || section.lines.length === 0) {
    section.lines = parseTurns(chunk.text);
  }
  return { chunk, section };
}

function videoIdFromUrl(url) {
  const text = String(url || '');
  const patterns = [/(?:v=)([A-Za-z0-9_-]{11})/, /youtu\.be\/([A-Za-z0-9_-]{11})/, /youtube\.com\/embed\/([A-Za-z0-9_-]{11})/];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) return match[1];
  }
  return '';
}

function youtubeWatchUrl(url, startSeconds) {
  const start = Math.max(0, Math.floor(Number(startSeconds || 0)));
  if (!url) return '#';
  return `${url}${url.includes('?') ? '&' : '?'}t=${start}s`;
}

function youtubeEmbedUrl(videoId, startSeconds) {
  const start = Math.max(0, Math.floor(Number(startSeconds || 0)));
  if (!videoId) return '';
  return `https://www.youtube-nocookie.com/embed/${videoId}?start=${start}&rel=0`;
}

function councilpersonById(personId) {
  return (state.meeting.councilpeople || []).find((p) => p.id === personId) || null;
}

function escapeHtml(str) {
  return String(str || '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function makeCombobox(options, initialId, initialCustomName) {
  const container = document.createElement('div');
  container.className = 'combobox';

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'combobox-input';
  input.autocomplete = 'off';
  input.spellcheck = false;

  const list = document.createElement('ul');
  list.className = 'combobox-list';
  list.hidden = true;

  let _id = initialId || '';
  let _activeIndex = -1;

  if (_id) {
    const person = options.find((p) => p.id === _id);
    input.value = person ? person.name : '';
  } else {
    input.value = initialCustomName || '';
  }

  function buildList(query) {
    list.innerHTML = '';
    _activeIndex = -1;
    const q = (query || '').toLowerCase();
    const addItem = (id, name) => {
      const li = document.createElement('li');
      li.className = 'combobox-item';
      li.dataset.id = id;
      li.dataset.name = name;
      if (q && name) {
        const i = name.toLowerCase().indexOf(q);
        if (i >= 0) {
          li.innerHTML = escapeHtml(name.slice(0, i))
            + '<mark>' + escapeHtml(name.slice(i, i + q.length)) + '</mark>'
            + escapeHtml(name.slice(i + q.length));
        } else {
          li.textContent = name;
        }
      } else {
        li.textContent = name || '\u2014 Unknown';
      }
      list.appendChild(li);
    };
    addItem('', '');
    for (const opt of options) {
      if (!q || opt.name.toLowerCase().includes(q)) addItem(opt.id, opt.name);
    }
  }

  function setActive(i) {
    const items = [...list.querySelectorAll('.combobox-item')];
    items.forEach((el, j) => el.classList.toggle('is-active', j === i));
    _activeIndex = i;
    if (items[i]) items[i].scrollIntoView({ block: 'nearest' });
  }

  function commit(id, name) {
    _id = id;
    input.value = name;
    list.hidden = true;
    _activeIndex = -1;
  }

  function openList() {
    buildList(input.value);
    list.hidden = false;
  }

  container.getId = () => _id;
  container.getName = () => input.value.trim();
  container.setSelection = (id, name) => { _id = id; input.value = name; };

  input.addEventListener('focus', openList);
  input.addEventListener('input', () => { _id = ''; buildList(input.value); list.hidden = false; });
  input.addEventListener('keydown', (e) => {
    const items = [...list.querySelectorAll('.combobox-item')];
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (list.hidden) openList();
      setActive(Math.min(_activeIndex + 1, items.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive(Math.max(_activeIndex - 1, 0));
    } else if (e.key === 'Enter') {
      if (!list.hidden && _activeIndex >= 0 && items[_activeIndex]) {
        e.preventDefault();
        e.stopPropagation();
        const li = items[_activeIndex];
        commit(li.dataset.id, li.dataset.name);
      } else if (!list.hidden) {
        e.preventDefault();
        e.stopPropagation();
        list.hidden = true;
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      list.hidden = true;
    }
  });
  input.addEventListener('blur', () => {
    setTimeout(() => { if (!container.contains(document.activeElement)) list.hidden = true; }, 130);
  });
  list.addEventListener('mousedown', (e) => {
    const li = e.target.closest('.combobox-item');
    if (!li) return;
    e.preventDefault();
    commit(li.dataset.id, li.dataset.name);
  });

  container.append(input, list);
  return container;
}

function lineRow(line) {
  const div = document.createElement('div');
  div.className = 'line-row';

  const people = state.meeting.councilpeople || [];
  const cb = makeCombobox(people, line.speaker_id, line.speaker_name);

  const cbInput = cb.querySelector('.combobox-input');
  cbInput.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'ArrowDown') {
      e.preventDefault();
      const rows = [...els.linesGrid.querySelectorAll('.line-row')];
      const start = rows.indexOf(div);
      for (let i = start + 1; i < rows.length; i++) {
        const tgt = rows[i].querySelector('.combobox');
        if (tgt) tgt.setSelection(cb.getId(), cb.getName());
      }
    }
  });

  const carry = document.createElement('button');
  carry.type = 'button';
  carry.className = 'line-carry';
  carry.title = 'Carry speaker to all turns below (Ctrl+Shift+\u2193)';
  carry.textContent = '\u2193';
  carry.addEventListener('click', () => {
    const rows = [...els.linesGrid.querySelectorAll('.line-row')];
    const start = rows.indexOf(div);
    for (let i = start + 1; i < rows.length; i++) {
      const tgt = rows[i].querySelector('.combobox');
      if (tgt) tgt.setSelection(cb.getId(), cb.getName());
    }
  });

  const text = document.createElement('p');
  text.className = 'line-text';
  text.textContent = line.text;

  div.append(cb, carry, text);
  return div;
}

function renderLines(lines) {
  els.linesGrid.innerHTML = '';
  lines.forEach((line) => els.linesGrid.appendChild(lineRow(line)));
  els.turnCount.textContent = `(${lines.length} turns)`;
}

function syncVideoToCurrentChunk(force = false) {
  if (!state.meeting) return;
  if (!force && !els.autoSyncVideo.checked) return;

  const chunk = state.meeting.transcript[state.index];
  if (!chunk) return;

  const videoId = state.meeting.video_id || videoIdFromUrl(state.meeting.youtube_url);
  const embed = youtubeEmbedUrl(videoId, chunk.start);
  const watch = youtubeWatchUrl(state.meeting.youtube_url, chunk.start);
  els.openVideoLink.href = watch;
  if (embed) {
    els.videoFrame.src = embed;
  }
}

function formatDisplayText(rawText, mode) {
  const raw = String(rawText || '').trim();
  if (!raw) return '';

  if (mode === 'compact') {
    return raw.replace(/\s+/g, ' ').trim();
  }

  if (mode === 'sentences') {
    return raw.replace(/\s*([.!?])\s+/g, '$1\n').trim();
  }

  return raw;
}

function renderDisplayPreview() {
  const { chunk } = sectionAt(state.index);
  const mode = els.displayMode.value || 'raw';
  const override = els.displayText.value.trim();
  const preview = override || formatDisplayText(chunk.text, mode);
  els.displayPreview.textContent = preview;
}

function renderMentions(selected = []) {
  els.mentions.innerHTML = '';
  for (const person of state.meeting.councilpeople || []) {
    const id = `mention-${person.id}`;
    const checked = selected.includes(person.id) ? 'checked' : '';
    const wrap = document.createElement('label');
    wrap.innerHTML = `<input type="checkbox" value="${person.id}" id="${id}" ${checked}> ${person.name}`;
    els.mentions.appendChild(wrap);
  }
}

function voteRow(vote = { motion: '', person_id: '', vote: '' }) {
  const row = document.createElement('div');
  row.className = 'vote-row';

  const motion = document.createElement('input');
  motion.className = 'vote-motion';
  motion.value = vote.motion || '';
  motion.placeholder = 'Motion';

  const people = state.meeting.councilpeople || [];
  const existingPerson = people.find((p) => p.id === vote.person_id);
  const memberCb = makeCombobox(people, vote.person_id, existingPerson ? existingPerson.name : '');
  memberCb.querySelector('.combobox-input').placeholder = 'Member...';

  const voteInput = document.createElement('select');
  voteInput.className = 'vote-outcome';
  voteInput.innerHTML = `
    <option value="">Vote</option>
    <option value="yes">yes</option>
    <option value="no">no</option>
    <option value="abstain">abstain</option>
    <option value="present">present</option>
    <option value="absent">absent</option>
  `;
  voteInput.value = vote.vote || '';

  const remove = document.createElement('button');
  remove.type = 'button';
  remove.textContent = 'Remove';
  remove.addEventListener('click', () => row.remove());

  row.append(motion, memberCb, voteInput, remove);
  return row;
}

function renderVotes(votes = []) {
  els.votes.innerHTML = '';
  votes.forEach((v) => els.votes.appendChild(voteRow(v)));
}

function saveCurrentSection() {
  if (!state.meeting || !state.annotation) return;
  const { section } = sectionAt(state.index);

  const rows = [...els.linesGrid.querySelectorAll('.line-row')];
  const lines = rows.map((row) => {
    const cb = row.querySelector('.combobox');
    const speakerId = cb ? cb.getId() : '';
    const rawName = cb ? cb.getName() : '';
    const turnText = row.querySelector('.line-text').textContent;
    const person = speakerId ? councilpersonById(speakerId) : null;
    return {
      text: turnText,
      speaker_id: speakerId,
      speaker_name: rawName || (person ? person.name : ''),
    };
  });
  section.lines = lines;
  // keep chunk-level speaker as first attributed turn for backward compat
  const firstAttributed = lines.find((l) => l.speaker_id || l.speaker_name);
  section.speaker_id = firstAttributed ? firstAttributed.speaker_id : '';
  section.speaker_name = firstAttributed ? firstAttributed.speaker_name : '';

  section.display_mode = els.displayMode.value || 'raw';
  section.display_text = els.displayText.value.trim();
  section.summary = els.summary.value.trim();
  section.tags = els.tags.value.split(',').map((x) => x.trim()).filter(Boolean);
  section.mentions = [...els.mentions.querySelectorAll('input[type="checkbox"]:checked')].map((x) => x.value);
  section.notes = els.notes.value.trim();

  section.votes = [...els.votes.querySelectorAll('.vote-row')]
    .map((row) => {
      const motionInput = row.querySelector('.vote-motion');
      const memberCb = row.querySelector('.combobox');
      const voteOutcome = row.querySelector('.vote-outcome');
      return {
        motion: motionInput ? motionInput.value.trim() : '',
        person_id: memberCb ? memberCb.getId() : '',
        vote: voteOutcome ? voteOutcome.value : '',
      };
    })
    .filter((v) => v.motion || v.person_id || v.vote);
}

function render() {
  const total = state.meeting.transcript.length;
  const { chunk, section } = sectionAt(state.index);
  els.progress.textContent = `Chunk ${state.index + 1} of ${total}`;
  els.chunkTitle.textContent = `${secToClock(chunk.start)} – ${secToClock(chunk.end)}`;

  const lines = section.lines && section.lines.length > 0 ? section.lines : parseTurns(chunk.text);
  renderLines(lines);

  els.displayMode.value = section.display_mode || 'raw';
  els.displayText.value = section.display_text || '';
  els.summary.value = section.summary || '';
  els.tags.value = (section.tags || []).join(', ');
  els.notes.value = section.notes || '';
  renderMentions(section.mentions || []);
  renderVotes(section.votes || []);
  renderDisplayPreview();
  syncVideoToCurrentChunk();
  els.prevBtn.disabled = state.index <= 0;
  els.nextBtn.disabled = state.index >= total - 1;
}

function addMemberFromInput() {
  if (!state.meeting || !state.annotation) return;
  const name = els.newMemberName.value.trim();
  if (!name) {
    els.status.textContent = 'Enter a member name first.';
    return;
  }
  saveCurrentSection();
  const added = addCouncilperson(name);
  if (!added) {
    els.status.textContent = 'Member already exists or name is invalid.';
    return;
  }
  els.newMemberName.value = '';
  render();
  els.status.textContent = `Added member: ${name}`;
}

function persist() {
  saveCurrentSection();
  localStorage.setItem(state.storageKey, JSON.stringify(state.annotation));
  els.status.textContent = `Saved locally at ${new Date().toLocaleTimeString()}`;
}

function download() {
  saveCurrentSection();
  const blob = new Blob([JSON.stringify(state.annotation, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${state.meeting.id}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function navigate(direction) {
  saveCurrentSection();
  localStorage.setItem(state.storageKey, JSON.stringify(state.annotation));
  const next = state.index + direction;
  if (next < 0 || next >= state.meeting.transcript.length) return;
  state.index = next;
  render();
}

els.loadBtn.addEventListener('click', async () => {
  try {
    const meeting = await readJSON(els.meetingFile);
    if (!meeting || !meeting.transcript) {
      throw new Error('Meeting JSON must include transcript array.');
    }
    state.meeting = meeting;
    state.storageKey = `annotation:${meeting.id}`;

    const uploadedAnnotation = await readJSON(els.annotationFile);
    const saved = localStorage.getItem(state.storageKey);

    const baseAnnotation = uploadedAnnotation || (saved ? JSON.parse(saved) : buildEmptyAnnotation(meeting));
    state.annotation = normalizeAnnotation(meeting, baseAnnotation);
    normalizeCouncilpeople(state.meeting, state.annotation);
    state.index = 0;
    els.editor.classList.remove('hidden');
    render();
    els.status.textContent = `Loaded ${meeting.id}`;
  } catch (err) {
    els.status.textContent = err.message;
  }
});

els.prevBtn.addEventListener('click', () => navigate(-1));
els.nextBtn.addEventListener('click', () => navigate(1));
els.saveBtn.addEventListener('click', persist);
els.downloadBtn.addEventListener('click', download);
els.addVoteBtn.addEventListener('click', () => els.votes.appendChild(voteRow()));
els.displayMode.addEventListener('change', renderDisplayPreview);
els.displayText.addEventListener('input', renderDisplayPreview);
els.addMemberBtn.addEventListener('click', addMemberFromInput);
els.newMemberName.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') {
    event.preventDefault();
    addMemberFromInput();
  }
});
els.applyModeBtn.addEventListener('click', () => {
  const { chunk } = sectionAt(state.index);
  els.displayText.value = formatDisplayText(chunk.text, els.displayMode.value || 'raw');
  renderDisplayPreview();
});
els.resetDisplayBtn.addEventListener('click', () => {
  els.displayText.value = '';
  renderDisplayPreview();
});
els.syncVideoBtn.addEventListener('click', () => syncVideoToCurrentChunk(true));

// ── Keyboard shortcuts ──────────────────────────────────────────────────────
document.addEventListener('keydown', (e) => {
  if (!state.meeting) return;
  const mod = e.ctrlKey || e.metaKey;
  if (!mod) return;

  // Ctrl/⌘+S → save
  if (e.key === 's' && !e.shiftKey && !e.altKey) {
    e.preventDefault();
    persist();
    return;
  }

  // Ctrl/⌘+Shift+D → download
  if (e.key === 'd' && e.shiftKey && !e.altKey) {
    e.preventDefault();
    download();
    return;
  }

  // Ctrl/⌘+Enter → save + next chunk
  if (e.key === 'Enter' && !e.shiftKey && !e.altKey) {
    // Only intercept when not inside a combobox list (let combobox handle its own Enter)
    if (document.activeElement && document.activeElement.classList.contains('combobox-input')) return;
    e.preventDefault();
    persist();
    navigate(1);
    return;
  }

  // Ctrl/⌘+Shift+Enter → save + previous chunk
  if (e.key === 'Enter' && e.shiftKey && !e.altKey) {
    if (document.activeElement && document.activeElement.classList.contains('combobox-input')) return;
    e.preventDefault();
    persist();
    navigate(-1);
    return;
  }

  // Ctrl/⌘+] → next chunk (no save)
  if (e.key === ']' && !e.shiftKey && !e.altKey) {
    const tag = document.activeElement ? document.activeElement.tagName : '';
    if (tag === 'TEXTAREA' || tag === 'INPUT') return;
    e.preventDefault();
    navigate(1);
    return;
  }

  // Ctrl/⌘+[ → previous chunk (no save)
  if (e.key === '[' && !e.shiftKey && !e.altKey) {
    const tag = document.activeElement ? document.activeElement.tagName : '';
    if (tag === 'TEXTAREA' || tag === 'INPUT') return;
    e.preventDefault();
    navigate(-1);
    return;
  }
});
