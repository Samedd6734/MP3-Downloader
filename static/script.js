/* ══════════════════════════════════════════════════════════
   MP3 İNDİRİCİ — New Music System v5.0
   
   HOME:   Rastgele, orijinal sanatçı şarkıları — her açılışta farklı
   SEARCH: Sanatçı kartı en üstte + şarkı listesi
   ARTIST: Lazy loading ile sonsuz şarkı listesi
   AUTH:   Google hesabı → YTM Keşfet önerileri
══════════════════════════════════════════════════════════ */

const $ = id => document.getElementById(id);
const main  = $('main');
const input = $('searchInput');

/* ────────────────────────────────────────────────────────
   HOME BUFFER — pre-fetched songs for instant serving
──────────────────────────────────────────────────────── */
let homeBuffer = [];       // Pre-fetched songs waiting to be shown
let homeFetching = false;  // Prevent parallel fetches
let homeMode = 'explore';  // 'explore' | 'discover'
let currentUser = null;

async function fetchHomeBuffer(force = false) {
    if (homeFetching) return;
    homeFetching = true;
    try {
        const url = force ? '/api/home?refresh=true' : '/api/home';
        const d = await apiFetch(url);
        homeBuffer = d.results || [];
        homeMode = d.mode || 'explore';
        if (d.user) currentUser = { name: d.user };
    } catch (e) {
        console.warn('Home fetch failed:', e);
    } finally {
        homeFetching = false;
    }
}

/* ────────────────────────────────────────────────────────
   AUTH — Google login state
──────────────────────────────────────────────────────── */
async function initAuth() {
    try {
        const d = await apiFetch('/api/auth/status');
        const btn = $('googleBtn');
        const avatar = $('userAvatar');
        if (d.logged_in) {
            currentUser = d;
            if (btn) btn.style.display = 'none';
            if (avatar) {
                avatar.style.display = 'flex';
                avatar.innerHTML = `
                    <img src="${escA(d.picture)}" alt="${escH(d.name)}" title="${escH(d.name)}" 
                         onerror="this.style.display='none'">
                    <button id="logoutBtn" onclick="doLogout()" title="Çıkış Yap">×</button>
                `;
            }
        } else {
            if (btn) btn.style.display = 'flex';
            if (avatar) avatar.style.display = 'none';
        }
    } catch {}
}

async function doLogout() {
    await fetch('/api/auth/logout', { method: 'POST' });
    location.reload();
}

/* ────────────────────────────────────────────────────────
   NAVIGATION
──────────────────────────────────────────────────────── */
$('homeLink').onclick = e => { e.preventDefault(); goHome(); };
$('searchBtn').onclick = doSearch;
input.onkeydown = e => { if (e.key === 'Enter') doSearch(); };

function goHome() {
    input.value = '';
    main.innerHTML = renderHomeSkeleton();
    showHome();
}

async function showHome() {
    // If buffer is ready, show immediately
    if (homeBuffer.length > 0) {
        renderHomeContent(homeBuffer, true);
        // Trigger background refresh for next visit
        fetchHomeBuffer(true).then(() => {});
        return;
    }
    // Buffer empty — fetch now
    await fetchHomeBuffer();
    renderHomeContent(homeBuffer);
}

function renderHomeContent(songs, withRefresh = false) {
    if (!songs || songs.length === 0) {
        main.innerHTML = `<p class="msg">Şarkılar yüklenemedi, lütfen yenileyin.</p>`;
        return;
    }

    const modeLabel = homeMode === 'discover'
        ? `<span class="mode-badge discover">✨ Keşfet — ${escH(currentUser?.name || '')}</span>`
        : `<span class="mode-badge explore">🌍 Keşfet</span>`;

    main.innerHTML = `
        <div class="home-header">
            <div class="home-header-titles">
                <h1 class="home-title">Müziği Keşfet</h1>
                ${modeLabel}
            </div>
            <button class="refresh-btn" id="refreshBtn" onclick="refreshHome()" title="Yeni şarkılar">
                <svg viewBox="0 0 24 24" width="18" height="18" stroke="currentColor" fill="none" stroke-width="2">
                    <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
                    <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
                </svg>
                Yenile
            </button>
        </div>
        <div id="homeGrid" class="songs-grid">
            ${songs.map(s => makeSongCardHTML(s)).join('')}
        </div>
    `;

    // Attach download listeners
    main.querySelectorAll('.btn-dl-card').forEach(btn => {
        btn.addEventListener('click', function() {
            const url   = this.dataset.url;
            const title = this.dataset.title;
            queueDownload(url, title, this);
        });
    });

    // Attach artist name click listeners
    main.querySelectorAll('[data-channel-url]').forEach(el => {
        el.addEventListener('click', function(e) {
            e.stopPropagation();
            const url  = this.dataset.channelUrl;
            const name = this.dataset.channelName;
            if (url) openArtist(url, name);
        });
    });
}

async function refreshHome() {
    const btn = $('refreshBtn');
    if (btn) { btn.disabled = true; btn.textContent = '...'; }
    main.querySelectorAll('.songs-grid').forEach(g => {
        g.style.opacity = '0.4';
        g.style.transition = 'opacity 0.2s';
    });
    await fetchHomeBuffer(true);
    renderHomeContent(homeBuffer);
}

function renderHomeSkeleton() {
    return `
        <div class="home-header">
            <div class="home-header-titles">
                <div class="skeleton" style="height:28px;width:180px;border-radius:6px"></div>
            </div>
        </div>
        <div class="songs-grid">
            ${Array.from({length: 20}, () => `
                <div class="song-card skeleton-card">
                    <div class="skeleton" style="width:100%;padding-bottom:56%;border-radius:8px 8px 0 0"></div>
                    <div class="song-card-body">
                        <div class="skeleton" style="height:13px;width:80%;margin-bottom:6px"></div>
                        <div class="skeleton" style="height:11px;width:50%"></div>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

/* ────────────────────────────────────────────────────────
   SEARCH
──────────────────────────────────────────────────────── */
async function doSearch() {
    const q = input.value.trim();
    if (!q) return;

    // Scroll to top on search
    window.scrollTo({ top: 0, behavior: 'smooth' });

    main.innerHTML = `
        <div class="search-results-wrap">
            <div id="artistSection"></div>
            <div id="songsSection">
                <div class="section-hd"><h2>Şarkılar</h2></div>
                <div id="soList" class="songs-grid">${skelCards(12)}</div>
            </div>
        </div>
    `;

    try {
        // Parallel: fetch artist info + songs simultaneously
        const [artistResult, songsResult] = await Promise.allSettled([
            apiFetch(`/api/search/artist?q=${enc(q)}`),
            apiFetch(`/api/search?q=${enc(q)}&max_results=24`),
        ]);

        // Render artist section if found
        const artistSection = $('artistSection');
        if (artistResult.status === 'fulfilled' && artistResult.value?.artist) {
            artistSection.innerHTML = renderArtistCard(artistResult.value.artist, q);
            artistSection.querySelector('.artist-card')?.addEventListener('click', function() {
                openArtist(this.dataset.channelUrl, this.dataset.channelName);
            });
        }

        // Render songs list
        const soList = $('soList');
        if (soList) {
            if (songsResult.status === 'fulfilled') {
                const songs = songsResult.value?.results || [];
                if (songs.length === 0) {
                    soList.innerHTML = '<p class="msg">Şarkı bulunamadı.</p>';
                } else {
                    soList.innerHTML = songs.map(s => makeSongCardHTML(s)).join('');
                    
                    // Attach listeners
                    soList.querySelectorAll('.btn-dl-card').forEach(btn => {
                        btn.addEventListener('click', function(e) {
                            e.stopPropagation();
                            queueDownload(this.dataset.url, this.dataset.title, this);
                        });
                    });
                    soList.querySelectorAll('[data-channel-url]').forEach(el => {
                        el.addEventListener('click', function(e) {
                            e.stopPropagation();
                            openArtist(this.dataset.channelUrl, this.dataset.channelName);
                        });
                    });
                }
            } else {
                soList.innerHTML = '<p class="msg err">Sonuçlar yüklenirken bir sorun oluştu.</p>';
            }
        }
    } catch (err) {
        console.error('Search error:', err);
        main.innerHTML = `<p class="msg err">Arama sırasında bir hata oluştu.</p>`;
    }
}

function renderArtistCard(artist, query) {
    const name    = escH(artist.name || query);
    const thumb   = escA(artist.thumbnail || '');
    const url     = escA(artist.channel_url || '');
    const subs    = artist.subscriber_count
        ? fmtSubs(artist.subscriber_count)
        : '';
    
    return `
        <div class="section-hd"><h2>En İyi Eşleşme</h2></div>
        <div class="artist-card" data-channel-url="${url}" data-channel-name="${name}" style="cursor:pointer">
            <div class="artist-card-img-wrap">
                ${thumb
                    ? `<img src="${thumb}" alt="${name}" onerror="this.parentElement.innerHTML='<div class=artist-img-fallback>${name.charAt(0)}</div>'">`
                    : `<div class="artist-img-fallback">${name.charAt(0)}</div>`
                }
            </div>
            <div class="artist-card-info">
                <div class="artist-card-name">${name}</div>
                ${subs ? `<span class="artist-card-subs">${subs} abone</span>` : ''}
                <div class="artist-card-cta">
                    <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
                    </svg>
                    Tüm Şarkıları Gör
                </div>
            </div>
        </div>
    `;
}

/* ────────────────────────────────────────────────────────
   ARTIST PAGE — lazy loading
──────────────────────────────────────────────────────── */
let artistOffset = 0;
let artistUrl    = '';
let artistName   = '';
let artistLoading = false;
let artistObserver = null;
let artistHasMore  = true;

function openArtist(url, name) {
    artistUrl    = url;
    artistName   = name || 'Sanatçı';
    artistOffset = 0;
    artistHasMore = true;
    artistLoading = false;

    main.innerHTML = `
        <div class="artist-page-header">
            <button class="back-btn" onclick="goHome()">← Geri</button>
            <h1 class="artist-page-name">${escH(artistName)}</h1>
        </div>
        <div class="section-hd"><h2>Şarkılar</h2></div>
        <div id="artistList" class="songs-list"></div>
        <div id="lazyAnchor" style="height:1px;margin-top:20px"></div>
    `;

    // Disconnect previous observer if any
    if (artistObserver) artistObserver.disconnect();

    // Load first batch immediately
    loadArtistBatch();

    // Setup IntersectionObserver for lazy loading
    const anchor = $('lazyAnchor');
    if (anchor) {
        artistObserver = new IntersectionObserver(entries => {
            if (entries[0].isIntersecting && !artistLoading && artistHasMore) {
                loadArtistBatch();
            }
        }, { rootMargin: '200px' });
        artistObserver.observe(anchor);
    }
}

async function loadArtistBatch() {
    if (artistLoading || !artistHasMore) return;
    artistLoading = true;

    const list = $('artistList');
    if (!list) { artistLoading = false; return; }

    // Show skeleton for first batch
    if (artistOffset === 0) {
        list.innerHTML = skelRows(10);
    } else {
        const skelEl = document.createElement('div');
        skelEl.id = 'artistSkel';
        skelEl.innerHTML = skelRows(6);
        list.appendChild(skelEl);
    }

    try {
        const d = await apiFetch(
            `/api/artist?url=${enc(artistUrl)}&max_results=20&offset=${artistOffset}`
        );
        const songs = d.results || [];
        artistHasMore = d.has_more && songs.length > 0;

        // Remove skeleton
        const skel = $('artistSkel');
        if (skel) skel.remove();

        if (artistOffset === 0) list.innerHTML = '';

        if (songs.length === 0 && artistOffset === 0) {
            list.innerHTML = '<p class="msg">Bu sanatçıya ait şarkı bulunamadı.</p>';
            artistHasMore = false;
        } else {
            const frag = document.createDocumentFragment();
            songs.forEach((item, i) => {
                frag.appendChild(makeRow(item, artistOffset + i + 1));
            });
            list.appendChild(frag);
            artistOffset += songs.length;
        }

        if (!artistHasMore && artistObserver) {
            artistObserver.disconnect();
        }
    } catch {
        const skel = $('artistSkel');
        if (skel) skel.innerHTML = '<p class="msg err">Yüklenemedi.</p>';
    } finally {
        artistLoading = false;
    }
}

/* ────────────────────────────────────────────────────────
   DOM BUILDERS
──────────────────────────────────────────────────────── */
function makeSongCardHTML(item) {
    const thumb = escA(item.thumbnail || '');
    const title = escH(item.title || '');
    const ch    = escH(item.channel || '');
    const url   = escA(item.url || '');
    const dur   = fmtDur(item.duration);
    const chUrl = escA(item.channel_url || '');
    const isOff = item.is_official;

    return `
        <div class="song-card">
            <div class="song-card-thumb">
                ${thumb ? `<img src="${thumb}" loading="lazy" alt="${title}" onerror="this.parentElement.classList.add('no-img')">` : ''}
                ${dur ? `<span class="song-card-dur">${dur}</span>` : ''}
                <button class="btn-dl-card" data-url="${url}" data-title="${title}" title="İndir">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5">
                        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
                    </svg>
                </button>
            </div>
            <div class="song-card-body">
                <div class="song-card-title" title="${title}">${title}</div>
                <div class="song-card-artist ${chUrl ? 'clickable' : ''}" 
                     ${chUrl ? `data-channel-url="${chUrl}" data-channel-name="${ch}"` : ''}>
                    ${isOff ? '<span class="official-dot" title="Resmi Kanal">●</span>' : ''}
                    ${ch}
                </div>
            </div>
        </div>
    `;
}

function makeRow(item, num) {
    const el = document.createElement('div');
    el.className = 'list-row';
    el.style.animationDelay = `${Math.min(num - 1, 19) * 18}ms`;
    const dur = fmtDur(item.duration);
    el.innerHTML = `
        <div class="list-num">${num}</div>
        <div class="list-thumb"><img src="${escA(item.thumbnail || '')}" loading="lazy" onerror="this.style.display='none'"></div>
        <div class="list-body">
            <div class="list-title">${escH(item.title || '')}</div>
            <div class="list-sub">${escH(item.channel || '')}</div>
        </div>
        <div class="list-actions">
            ${dur ? `<span class="list-dur">${dur}</span>` : ''}
            <button class="btn-dl-list" data-url="${escA(item.url)}" data-title="${escH(item.title || '')}">İndir</button>
        </div>
    `;
    el.querySelector('.btn-dl-list').addEventListener('click', function() {
        queueDownload(item.url, item.title, this);
    });
    return el;
}

function skelCards(n) {
    return Array.from({length: n}, () => `
        <div class="song-card skeleton-card">
            <div class="skeleton" style="width:100%;padding-bottom:56%;border-radius:8px 8px 0 0"></div>
            <div class="song-card-body">
                <div class="skeleton" style="height:13px;width:80%;margin-bottom:6px"></div>
                <div class="skeleton" style="height:11px;width:50%"></div>
            </div>
        </div>
    `).join('');
}

function skelRows(n) {
    return Array.from({length: n}, (_, i) => `
        <div class="list-row" style="pointer-events:none;animation-delay:${i * 25}ms">
            <div class="list-num" style="opacity:0">${i + 1}</div>
            <div class="skeleton" style="width:72px;height:45px;border-radius:6px;flex-shrink:0"></div>
            <div class="list-body">
                <div class="skeleton" style="height:13px;width:65%;margin-bottom:7px"></div>
                <div class="skeleton" style="height:11px;width:38%"></div>
            </div>
        </div>`).join('');
}

/* ────────────────────────────────────────────────────────
   UTILITIES
──────────────────────────────────────────────────────── */
function fmtDur(s) {
    if (!s) return '';
    const m = Math.floor(s / 60);
    return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}
function fmtSubs(n) {
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000)     return Math.round(n / 1_000) + 'B';
    return String(n);
}
function enc(v)  { return encodeURIComponent(v); }
function escH(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function escA(s) { return String(s).replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
async function apiFetch(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
}

/* ────────────────────────────────────────────────────────
   DOWNLOAD QUEUE
──────────────────────────────────────────────────────── */
async function queueDownload(url, title, btn) {
    if (btn.classList.contains('dl-active')) return;
    
    btn.classList.add('dl-active');
    const origHTML = btn.innerHTML;
    btn.innerHTML = '...';
    
    try {
        const d = await apiFetch(`/api/download?url=${enc(url)}`);
        const taskId = d.task_id;
        if (!taskId) throw new Error();

        // Polling loop
        const iv = setInterval(async () => {
            try {
                const r = await fetch(`/api/progress?task_id=${taskId}`);
                if (!r.ok) { clearInterval(iv); throw new Error(); }
                const prog = await r.json();

                if (prog.status === 'done') {
                    clearInterval(iv);
                    btn.innerHTML = '✓';
                    btn.style.background = 'var(--green)';
                    btn.style.borderColor = 'var(--green)';
                    
                    // Auto-trigger download
                    const a = document.createElement('a');
                    a.href = `/api/file?task_id=${taskId}`;
                    a.download = ''; 
                    document.body.appendChild(a);
                    a.click();
                    document.body.removeChild(a);

                    setTimeout(() => {
                        btn.classList.remove('dl-active');
                        btn.innerHTML = origHTML;
                        btn.style.background = '';
                        btn.style.borderColor = '';
                    }, 3000);
                } else if (prog.status === 'error') {
                    clearInterval(iv);
                    throw new Error();
                } else {
                    // Updating text based on status can be noisy on the small button, 
                    // but we can show progress percentage if we want.
                    if (prog.progress > 0) btn.innerHTML = Math.round(prog.progress) + '%';
                }
            } catch (e) {
                clearInterval(iv);
                btn.innerHTML = 'Hata';
                btn.style.color = 'var(--red)';
                setTimeout(() => {
                    btn.classList.remove('dl-active');
                    btn.innerHTML = origHTML;
                    btn.style.color = '';
                }, 2000);
            }
        }, 2000);

    } catch {
        btn.innerHTML = 'Hata';
        btn.classList.remove('dl-active');
        btn.style.color = 'var(--red)';
        setTimeout(() => { btn.innerHTML = origHTML; btn.style.color = ''; }, 2000);
    }
}

/* ────────────────────────────────────────────────────────
   BOOT
──────────────────────────────────────────────────────── */
(async () => {
    // Start auth check and home buffer fetch in parallel
    Promise.all([
        initAuth(),
        fetchHomeBuffer(),
    ]).then(() => {
        goHome();
    });
})();
