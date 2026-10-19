// Client-side controller for ICAO Document Search UI

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const statsSummary = document.getElementById('statsSummary');
    const reindexBtn = document.getElementById('reindexBtn');
    const searchForm = document.getElementById('searchForm');
    const queryInput = document.getElementById('queryInput');
    const searchBtn = document.getElementById('searchBtn');
    const resultsFeed = document.getElementById('resultsFeed');
    const resultsMeta = document.getElementById('resultsMeta');
    const resCount = document.getElementById('resCount');
    const resQuery = document.getElementById('resQuery');
    const resTime = document.getElementById('resTime');
    const resMode = document.getElementById('resMode');

    // Filters
    const filtersToggle = document.getElementById('filtersToggle');
    const filtersBody = document.getElementById('filtersBody');
    const filterToggleIcon = document.getElementById('filterToggleIcon');
    const docFilter = document.getElementById('docFilter');
    const chapterFilter = document.getElementById('chapterFilter');
    const minPage = document.getElementById('minPage');
    const maxPage = document.getElementById('maxPage');
    const topK = document.getElementById('topK');
    const weightSlider = document.getElementById('weightSlider');
    const weightDisplay = document.getElementById('weightDisplay');

    // Modal
    const chunkModal = document.getElementById('chunkModal');
    const closeModalBtn = document.getElementById('closeModalBtn');
    const modalTitle = document.getElementById('modalTitle');
    const modalSubtitle = document.getElementById('modalSubtitle');
    const modalContext = document.getElementById('modalContext');
    const modalText = document.getElementById('modalText');
    const copyCitationBtn = document.getElementById('copyCitationBtn');

    // Import and Notification Elements
    const importAlertBanner = document.getElementById('importAlertBanner');
    const alertMessage = document.getElementById('alertMessage');
    const alertDetails = document.getElementById('alertDetails');
    const openImportModalBtn = document.getElementById('openImportModalBtn');
    const dismissAlertBtn = document.getElementById('dismissAlertBtn');
    const importBtn = document.getElementById('importBtn');
    const importDot = document.getElementById('importDot');
    const importModal = document.getElementById('importModal');
    const closeImportModalBtn = document.getElementById('closeImportModalBtn');
    const dropzone = document.getElementById('dropzone');
    const browseLink = document.getElementById('browseLink');
    const fileUploadInput = document.getElementById('fileUploadInput');
    const importFileList = document.getElementById('importFileList');
    const refreshImportBtn = document.getElementById('refreshImportBtn');
    const syncReparseBtn = document.getElementById('syncReparseBtn');
    const pendingBtnCount = document.getElementById('pendingBtnCount');

    let currentModalChunk = null;
    let latestImportStatus = null;
    let isBannerDismissed = false;

    // Load Index Stats & Documents
    async function loadStats() {
        try {
            const res = await fetch('/api/stats');
            if (!res.ok) throw new Error('Failed to load stats');
            const data = await res.json();
            statsSummary.textContent = `${data.total_chunks.toLocaleString()} Chunks | ${data.total_documents} Docs (${data.total_pages_indexed} Pages)`;

            // Dynamically populate target document selector
            if (data.documents && data.documents.length > 0) {
                const currentVal = docFilter.value;
                const sortedDocs = [...data.documents].sort((a, b) => a.title.localeCompare(b.title));
                docFilter.innerHTML = '<option value="">All Documents</option>' + 
                    sortedDocs.map(d => `<option value="${d.doc_id}">${escapeHtml(d.title)} (${d.filename})</option>`).join('');
                if (currentVal && sortedDocs.some(d => d.doc_id === currentVal)) {
                    docFilter.value = currentVal;
                }
            }
        } catch (err) {
            statsSummary.textContent = 'Ready (Not yet indexed)';
        }
    }

    // Check Import Directory for New or Modified PDFs
    async function checkImportStatus() {
        try {
            const res = await fetch('/api/import/status');
            if (!res.ok) return;
            const data = await res.json();
            latestImportStatus = data;

            if (data.has_pending_changes) {
                // Show notification dot
                importDot.classList.remove('hidden');
                pendingBtnCount.textContent = data.total_pending;

                // Show alert banner unless user dismissed it for this session
                if (!isBannerDismissed) {
                    const newCount = data.new_files.length;
                    const updCount = data.updated_files.length;
                    const parts = [];
                    if (newCount > 0) parts.push(`${newCount} new document${newCount > 1 ? 's' : ''}`);
                    if (updCount > 0) parts.push(`${updCount} updated version${updCount > 1 ? 's' : ''}`);

                    alertMessage.textContent = `New or updated ICAO PDFs detected (${parts.join(', ')})!`;
                    const sampleNames = [...data.new_files, ...data.updated_files].map(f => f.filename).slice(0, 3).join(', ');
                    alertDetails.textContent = `Files ready to re-parse in import_pdfs/: ${sampleNames}`;
                    importAlertBanner.classList.remove('hidden');
                }
            } else {
                importDot.classList.add('hidden');
                importAlertBanner.classList.add('hidden');
                pendingBtnCount.textContent = '0';
            }

            // If modal is open, re-render file list
            if (!importModal.classList.contains('hidden')) {
                renderImportList(data);
            }
        } catch (err) {
            console.error('Failed to check import status:', err);
        }
    }

    // Toggle Filters Panel
    filtersToggle.addEventListener('click', () => {
        const isCollapsed = filtersBody.classList.toggle('collapsed');
        filterToggleIcon.textContent = isCollapsed ? '▼' : '▲';
    });

    // Slider Balance Update
    weightSlider.addEventListener('input', (e) => {
        const dense = parseInt(e.target.value, 10);
        const bm25 = 100 - dense;
        weightDisplay.textContent = `Dense: ${dense}% | BM25: ${bm25}%`;
    });

    // Quick Tag Chips
    document.querySelectorAll('.tag-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            queryInput.value = chip.dataset.query;
            searchForm.dispatchEvent(new Event('submit'));
        });
    });

    // Re-index Action
    reindexBtn.addEventListener('click', async () => {
        if (!confirm('Re-index all ICAO PDF documents? This will re-parse and embed all content.')) return;

        reindexBtn.disabled = true;
        reindexBtn.innerHTML = `
            <svg class="spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-dashoffset="12"/>
            </svg>
            Indexing...
        `;

        try {
            const res = await fetch('/api/index?force=true', { method: 'POST' });
            const data = await res.json();
            alert(`Indexing complete! Processed ${data.total_documents} documents (${data.total_chunks} chunks).`);
            await loadStats();
        } catch (err) {
            alert('Indexing failed: ' + err.message);
        } finally {
            reindexBtn.disabled = false;
            reindexBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
                </svg>
                Re-index
            `;
        }
    });

    // Search Execution
    searchForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = queryInput.value.trim();
        if (!query) return;

        searchBtn.disabled = true;
        searchBtn.querySelector('span').textContent = 'Searching...';

        // Prepare request payload
        const denseWeight = parseFloat(weightSlider.value) / 100.0;
        const bm25Weight = 1.0 - denseWeight;

        const payload = {
            query: query,
            top_k: parseInt(topK.value, 10),
            dense_weight: denseWeight,
            bm25_weight: bm25Weight,
            filter: {
                doc_id: docFilter.value || null,
                chapter_keyword: chapterFilter.value.trim() || null,
                min_page: minPage.value ? parseInt(minPage.value, 10) : null,
                max_page: maxPage.value ? parseInt(maxPage.value, 10) : null,
                exclude_front_matter: false
            }
        };

        try {
            const res = await fetch('/api/search', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || 'Search request failed');
            }

            const data = await res.json();
            renderResults(data);
        } catch (err) {
            resultsFeed.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">⚠️</div>
                    <h3>Search Error</h3>
                    <p>${escapeHtml(err.message)}</p>
                </div>
            `;
        } finally {
            searchBtn.disabled = false;
            searchBtn.querySelector('span').textContent = 'Search';
        }
    });

    // Render Search Results
    function renderResults(data) {
        resultsMeta.classList.remove('hidden');
        resCount.textContent = data.total_results;
        resQuery.textContent = data.query;
        resTime.textContent = `${data.time_taken_ms}ms`;
        resMode.textContent = data.retrieval_mode;

        if (data.results.length === 0) {
            resultsFeed.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">🔍</div>
                    <h3>No Direct Matches Found</h3>
                    <p>Try broadening your query, lowering the page filters, or adjusting the hybrid weight slider.</p>
                </div>
            `;
            return;
        }

        resultsFeed.innerHTML = data.results.map((item, idx) => {
            let docClass = 'doc_generic';
            if (item.doc_id && item.doc_id.includes('4444')) docClass = 'doc_4444';
            else if (item.doc_id && item.doc_id.includes('9562')) docClass = 'doc_9562';
            else if (item.doc_id && item.doc_id.includes('9750')) docClass = 'doc_9750';
            else if (item.doc_id && item.doc_id.includes('annex')) docClass = 'annex';

            const displayTitle = item.doc_title || item.filename || item.doc_id;

            return `
                <article class="result-card" data-chunk-id="${item.chunk_id}">
                    <div class="card-top">
                        <div class="doc-badge-group">
                            <span class="badge-doc ${docClass}">${escapeHtml(displayTitle)}</span>
                            <span class="badge-page">Page ${item.page_number}</span>
                            ${item.chapter ? `<span class="chapter-title">📁 ${escapeHtml(item.chapter)}</span>` : ''}
                        </div>
                        <div class="score-pill" title="Dense: ${item.dense_score ?? 'N/A'}, BM25: ${item.bm25_score ?? 'N/A'}">
                            <span>Score: ${item.score.toFixed(3)}</span>
                        </div>
                    </div>

                    <div class="snippet-content">
                        ${item.snippet}
                    </div>

                    <div class="card-actions">
                        <button class="btn btn-secondary view-chunk-btn" data-chunk-id="${item.chunk_id}">
                            Inspect Full Context
                        </button>
                    </div>
                </article>
            `;
        }).join('');

        // Attach modal openers
        document.querySelectorAll('.view-chunk-btn').forEach(btn => {
            btn.addEventListener('click', () => openChunkModal(btn.dataset.chunkId));
        });
    }

    // Modal Handling
    async function openChunkModal(chunkId) {
        try {
            const res = await fetch(`/api/chunk/${chunkId}`);
            if (!res.ok) throw new Error('Chunk not found');
            const chunk = await res.json();
            currentModalChunk = chunk;

            modalTitle.textContent = `${chunk.metadata.doc_title}`;
            modalSubtitle.textContent = `Page ${chunk.metadata.page_number} &bull; ${chunk.metadata.chapter || 'Section'}`;
            modalContext.textContent = chunk.context_prefix || 'No prefix';
            modalText.textContent = chunk.text;

            chunkModal.classList.remove('hidden');
        } catch (err) {
            alert('Failed to load chunk details: ' + err.message);
        }
    }

    closeModalBtn.addEventListener('click', () => {
        chunkModal.classList.add('hidden');
    });

    chunkModal.addEventListener('click', (e) => {
        if (e.target === chunkModal) {
            chunkModal.classList.add('hidden');
        }
    });

    // Copy Citation
    copyCitationBtn.addEventListener('click', () => {
        if (!currentModalChunk) return;
        const meta = currentModalChunk.metadata;
        const citation = `[ICAO Citation] ${meta.doc_title}, Page ${meta.page_number}${meta.chapter ? `, ${meta.chapter}` : ''}.\n\nPassage:\n"${currentModalChunk.text}"`;
        navigator.clipboard.writeText(citation).then(() => {
            copyCitationBtn.innerHTML = '✓ Copied!';
            setTimeout(() => {
                copyCitationBtn.innerHTML = `
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                    </svg>
                    Copy Citation
                `;
            }, 1800);
        });
    });

    // Render Import Files List in Modal
    function renderImportList(status) {
        if (!status) return;
        const allFiles = [
            ...status.new_files.map(f => ({ ...f, type: 'new' })),
            ...status.updated_files.map(f => ({ ...f, type: 'updated' })),
            ...status.up_to_date_files.map(f => ({ ...f, type: 'up_to_date' }))
        ];

        if (allFiles.length === 0) {
            importFileList.innerHTML = `
                <div class="loading-placeholder">
                    No PDF files found in <code>import_pdfs/</code>. Drop or browse a file above!
                </div>
            `;
            return;
        }

        importFileList.innerHTML = allFiles.map(f => {
            const sizeStr = f.size_bytes > 1024 * 1024
                ? `${(f.size_bytes / (1024 * 1024)).toFixed(2)} MB`
                : `${Math.round(f.size_bytes / 1024)} KB`;

            let badgeHtml = '';
            if (f.type === 'new') {
                badgeHtml = '<span class="badge-status new">New &bull; Ready to parse</span>';
            } else if (f.type === 'updated') {
                badgeHtml = '<span class="badge-status updated">Modified &bull; Needs update</span>';
            } else {
                badgeHtml = '<span class="badge-status up_to_date">Indexed &bull; Up to date</span>';
            }

            return `
                <div class="import-file-item">
                    <div class="file-info-group">
                        <span class="file-icon">📄</span>
                        <div>
                            <div class="file-name">${escapeHtml(f.filename)}</div>
                            <div class="file-meta">${sizeStr} &bull; Modified ${f.last_modified}</div>
                        </div>
                    </div>
                    <div>
                        ${badgeHtml}
                    </div>
                </div>
            `;
        }).join('');
    }

    // Open & Close Import Modal
    function openImportModal() {
        importModal.classList.remove('hidden');
        if (latestImportStatus) {
            renderImportList(latestImportStatus);
        } else {
            checkImportStatus();
        }
    }

    importBtn.addEventListener('click', openImportModal);
    openImportModalBtn.addEventListener('click', openImportModal);

    closeImportModalBtn.addEventListener('click', () => {
        importModal.classList.add('hidden');
    });

    importModal.addEventListener('click', (e) => {
        if (e.target === importModal) {
            importModal.classList.add('hidden');
        }
    });

    dismissAlertBtn.addEventListener('click', () => {
        isBannerDismissed = true;
        importAlertBanner.classList.add('hidden');
    });

    refreshImportBtn.addEventListener('click', () => {
        refreshImportBtn.disabled = true;
        refreshImportBtn.textContent = 'Refreshing...';
        checkImportStatus().finally(() => {
            refreshImportBtn.disabled = false;
            refreshImportBtn.textContent = '↻ Refresh';
        });
    });

    // File Upload / Dropzone Handlers
    browseLink.addEventListener('click', (e) => {
        e.stopPropagation();
        fileUploadInput.click();
    });

    dropzone.addEventListener('click', () => {
        fileUploadInput.click();
    });

    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            uploadFiles(e.dataTransfer.files);
        }
    });

    fileUploadInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
            uploadFiles(e.target.files);
        }
    });

    async function uploadFiles(files) {
        for (const file of files) {
            if (!file.name.toLowerCase().endsWith('.pdf')) {
                alert(`"${file.name}" is not a PDF file. Please select PDF documents.`);
                continue;
            }

            const formData = new FormData();
            formData.append('file', file);

            try {
                const res = await fetch('/api/import/upload', {
                    method: 'POST',
                    body: formData
                });
                if (!res.ok) throw new Error('Upload failed');
            } catch (err) {
                alert(`Failed to upload ${file.name}: ${err.message}`);
            }
        }
        await checkImportStatus();
    }

    // Sync / Reparse Action
    syncReparseBtn.addEventListener('click', async () => {
        syncReparseBtn.disabled = true;
        syncReparseBtn.innerHTML = `
            <svg class="spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10" stroke-dasharray="32" stroke-dashoffset="12"/>
            </svg>
            Reparsing & Embedding...
        `;

        try {
            const res = await fetch('/api/import/sync', { method: 'POST' });
            if (!res.ok) throw new Error('Sync failed');
            const data = await res.json();
            alert(`Sync complete! Reparsed ${data.synced_count} document(s). Total chunks now: ${data.stats.total_chunks}.`);
            await loadStats();
            await checkImportStatus();
        } catch (err) {
            alert('Reparsing failed: ' + err.message);
        } finally {
            syncReparseBtn.disabled = false;
            syncReparseBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/>
                </svg>
                Reparse & Sync Pending (<span id="pendingBtnCount">0</span>)
            `;
        }
    });

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Initialize stats & import status
    loadStats();
    checkImportStatus();

    // Check imports periodically (every 15 seconds) and on window focus
    setInterval(checkImportStatus, 15000);
    window.addEventListener('focus', checkImportStatus);
});
