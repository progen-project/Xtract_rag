/**
 * PetroRAG — Main Application Logic
 * 
 * Handles navigation, state management, and all UI interactions.
 */

// ============================
// STATE
// ============================
let state = {
    categories: [],
    chats: [],
    documents: [],
    currentView: 'dashboard',
    selectedCategoryId: null,
    selectedChatId: null,
    selectedCategoryIds: [], // for chat context
    activeBatchId: null,
    eventSource: null
};

// ============================
// INITIALIZATION
// ============================
document.addEventListener('DOMContentLoaded', async () => {
    initEventListeners();
    await refreshAll();
});

async function refreshAll() {
    await Promise.all([loadCategories(), loadChats()]);
    updateDashboardStats();
}

function initEventListeners() {
    // File Upload — Drop Zone
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');

    dropZone.addEventListener('click', (e) => {
        // Don't trigger file dialog if clicking the file preview list
        if (e.target.closest('.file-preview-list')) return;
        fileInput.click();
    });

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        if (e.dataTransfer.files.length) {
            showFilePreview(e.dataTransfer.files);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            showFilePreview(e.target.files);
        }
    });

    // Chat Image Input
    const chatImageInput = document.getElementById('chat-image-input');
    if (chatImageInput) {
        chatImageInput.addEventListener('change', (e) => {
            if (e.target.files.length) {
                handleChatImageSelection(e.target.files);
            }
        });
    }

    // Explicit Upload Button
    const uploadBtn = document.getElementById('upload-files-btn');
    if (uploadBtn) {
        uploadBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (pendingFiles) {
                // Hide preview and button immediately
                document.getElementById('file-preview-list').classList.add('hidden');
                uploadBtn.classList.add('hidden');
                
                // Start upload
                handleUpload(pendingFiles);
                pendingFiles = null;
            }
        });
    }

    // Chat Input — Enter Key
    document.getElementById('chat-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Chat scroll detection for scroll-to-bottom button
    const chatMessages = document.getElementById('chat-messages');
    chatMessages.addEventListener('scroll', () => {
        const btn = document.getElementById('scroll-bottom-btn');
        const isNearBottom = chatMessages.scrollHeight - chatMessages.scrollTop - chatMessages.clientHeight < 100;
        btn.classList.toggle('visible', !isNearBottom);
    });
}

// ============================
// TOAST NOTIFICATIONS
// ============================
function showToast(message, type = 'info', duration = 3500) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    
    const icons = {
        success: 'fa-circle-check',
        error: 'fa-circle-xmark',
        warning: 'fa-triangle-exclamation',
        info: 'fa-circle-info'
    };

    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<i class="fa-solid ${icons[type] || icons.info}"></i> ${message}`;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('toast-exit');
        setTimeout(() => toast.remove(), 250);
    }, duration);
}

// ============================
// LOADING HELPERS
// ============================
function showLoading() {
    document.getElementById('loading-overlay').classList.add('active');
}

function hideLoading() {
    document.getElementById('loading-overlay').classList.remove('active');
}

// ============================
// SIDEBAR TOGGLE (MOBILE)
// ============================
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    sidebar.classList.toggle('open');
    overlay.classList.toggle('active');
}

// ============================
// FILE PREVIEW BEFORE UPLOAD
// ============================
let pendingFiles = null;

function showFilePreview(files) {
    pendingFiles = files;
    const list = document.getElementById('file-preview-list');
    const uploadBtn = document.getElementById('upload-files-btn');
    
    list.classList.remove('hidden');
    list.innerHTML = '';

    Array.from(files).forEach(file => {
        const sizeKB = (file.size / 1024).toFixed(1);
        const sizeMB = (file.size / (1024 * 1024)).toFixed(1);
        const sizeStr = file.size > 1024 * 1024 ? `${sizeMB} MB` : `${sizeKB} KB`;
        
        const li = document.createElement('li');
        li.innerHTML = `<i class="fa-solid fa-file-pdf"></i> ${file.name} <span class="file-size">${sizeStr}</span>`;
        list.appendChild(li);
    });

    // Show upload button
    uploadBtn.classList.remove('hidden');
    uploadBtn.innerHTML = `<i class="fa-solid fa-cloud-arrow-up"></i> Upload ${files.length} file(s)`;
}

function formatFileSize(bytes) {
    if (bytes > 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / 1024).toFixed(1) + ' KB';
}

// ============================
// NAVIGATION & VIEWS
// ============================
function switchView(viewName) {
    document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
    document.getElementById(`view-${viewName}`).classList.add('active');
    state.currentView = viewName;

    const title = document.getElementById('page-title');
    const subtitle = document.getElementById('page-subtitle');
    const actions = document.getElementById('header-actions');
    actions.innerHTML = '';

    if (viewName === 'dashboard') {
        title.innerText = 'Dashboard';
        subtitle.innerText = 'Overview of your knowledge base';
        state.selectedCategoryId = null;
        state.selectedChatId = null;
    } else if (viewName === 'category') {
        const cat = state.categories.find(c => c.category_id === state.selectedCategoryId);
        if (cat) {
            title.innerText = cat.name;
            subtitle.innerText = cat.description || 'No description';
            actions.innerHTML = `
                <button class="btn btn-secondary" onclick="openRenameModal('${cat.category_id}')">
                    <i class="fa-solid fa-pen"></i> Rename
                </button>
                <button class="btn btn-danger" onclick="deleteCategory('${cat.category_id}')">
                    <i class="fa-solid fa-trash"></i> Delete
                </button>
            `;
        }
        loadDocuments(state.selectedCategoryId);
    } else if (viewName === 'chat') {
        title.innerText = 'Chat Session';
        subtitle.innerText = state.selectedChatId ? 'Conversation History' : 'New Session';

        if (state.selectedChatId) {
            actions.innerHTML = `
                <button class="btn btn-danger" onclick="deleteChat('${state.selectedChatId}')">
                    <i class="fa-solid fa-trash"></i> Delete Chat
                </button>
            `;
        }
    }
}

// ============================
// CATEGORIES
// ============================
async function loadCategories() {
    try {
        state.categories = await Api.listCategories();
        renderSidebarCategories();
    } catch (e) {
        console.error('Failed to load categories:', e);
    }
}

function renderSidebarCategories() {
    const list = document.getElementById('category-list');
    list.innerHTML = state.categories.map(cat => `
        <div class="nav-item ${state.selectedCategoryId === cat.category_id ? 'active' : ''}" 
             onclick="selectCategory('${cat.category_id}')">
            <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${cat.name}</span>
            <span class="badge">${cat.document_count}</span>
        </div>
    `).join('');
}

function selectCategory(id) {
    state.selectedCategoryId = id;
    state.selectedChatId = null;
    renderSidebarCategories();
    renderSidebarChats();
    switchView('category');
    // Reset file preview
    const list = document.getElementById('file-preview-list');
    list.classList.add('hidden');
    pendingFiles = null;
}

async function createCategory() {
    const name = document.getElementById('new-cat-name').value.trim();
    const desc = document.getElementById('new-cat-desc').value.trim();

    if (!name) { showToast('Category name is required', 'warning'); return; }

    try {
        await Api.createCategory(name, desc || null);
        closeModal('create-category-modal');
        document.getElementById('new-cat-name').value = '';
        document.getElementById('new-cat-desc').value = '';
        await loadCategories();
        updateDashboardStats();
        showToast('Category created successfully', 'success');
    } catch (e) {
        showToast(e.message, 'error');
    }
}

function openRenameModal(id) {
    const cat = state.categories.find(c => c.category_id === id);
    if (!cat) return;

    document.getElementById('rename-cat-id').value = id;
    document.getElementById('rename-cat-name').value = cat.name;
    document.getElementById('rename-cat-desc').value = cat.description || '';
    openModal('rename-category-modal');
}

async function submitRenameCategory() {
    const id = document.getElementById('rename-cat-id').value;
    const name = document.getElementById('rename-cat-name').value.trim();
    const desc = document.getElementById('rename-cat-desc').value.trim();

    if (!name) { showToast('Name cannot be empty', 'warning'); return; }

    try {
        await Api.updateCategory(id, name, desc || null);
        closeModal('rename-category-modal');
        await loadCategories();
        switchView('category');
        showToast('Category renamed', 'success');
    } catch (e) {
        showToast(e.message, 'error');
    }
}

async function deleteCategory(id) {
    if (!confirm('Delete this category? Documents will remain but lose their category grouping.')) return;
    try {
        showLoading();
        await Api.deleteCategory(id);
        state.selectedCategoryId = null;
        await loadCategories();
        switchView('dashboard');
        updateDashboardStats();
        showToast('Category deleted', 'success');
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        hideLoading();
    }
}

// ============================
// DOCUMENTS
// ============================
async function loadDocuments(categoryId) {
    try {
        state.documents = await Api.listDocuments(categoryId);
        renderDocuments();
    } catch (e) {
        console.error('Failed to load documents:', e);
    }
}

function renderDocuments() {
    const tbody = document.getElementById('documents-list');
    if (state.documents.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 2.5rem; color: var(--text-muted);">No documents uploaded yet</td></tr>';
        return;
    }

    tbody.innerHTML = state.documents.map(doc => `
        <tr>
            <td style="font-weight: 500;">
                <i class="fa-solid fa-file-pdf" style="color: var(--danger-color); margin-right: 0.4rem;"></i>
                ${doc.filename}
            </td>
            <td><span class="status-badge status-${doc.status.toLowerCase()}">${doc.status}</span></td>
            <td>${doc.is_daily ? '<span style="color: var(--warning-color); font-weight: 500;">Daily</span>' : '<span style="color: var(--text-muted);">Permanent</span>'}</td>
            <td style="color: var(--text-muted); font-size: 0.82rem;">${new Date(doc.upload_date).toLocaleDateString()}</td>
            <td>
                <div class="doc-actions">
                    <button class="btn btn-secondary btn-icon" title="Download" onclick="downloadDocument('${doc.document_id}')">
                        <i class="fa-solid fa-download"></i>
                    </button>
                    <button class="btn btn-danger btn-icon" title="Burn Document" onclick="burnDocument('${doc.document_id}')">
                        <i class="fa-solid fa-fire"></i>
                    </button>
                </div>
            </td>
        </tr>
    `).join('');

    updateDashboardStats();
}

function downloadDocument(documentId) {
    // Trigger browser download via anchor
    const url = Api.getDownloadUrl(documentId);
    const a = document.createElement('a');
    a.href = url;
    a.download = '';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToast('Download started', 'info');
}

async function handleUpload(files) {
    if (!state.selectedCategoryId) {
        showToast('Please select a category first', 'warning');
        return;
    }

    const isDaily = document.getElementById('is-daily').checked;

    try {
        const statusText = document.getElementById('upload-status-text');
        statusText.innerText = `Uploading ${files.length} file(s)...`;
        document.getElementById('upload-progress-container').style.display = 'block';
        
        const docs = await Api.uploadDocuments(state.selectedCategoryId, files, isDaily);

        if (docs.length > 0 && docs[0].batch_id) {
            startBatchMonitoring(docs[0].batch_id);
        }

        await loadDocuments(state.selectedCategoryId);
        showToast(`${docs.length} file(s) uploaded`, 'success');
    } catch (e) {
        showToast(e.message, 'error');
        document.getElementById('upload-progress-container').style.display = 'none';
    }

    // Reset file input
    document.getElementById('file-input').value = '';
}

function startBatchMonitoring(batchId) {
    state.activeBatchId = batchId;
    document.getElementById('batch-controls').classList.remove('hidden');
    document.getElementById('upload-progress-container').style.display = 'block';
    const progressBar = document.getElementById('upload-progress-bar');
    const statusText = document.getElementById('upload-status-text');

    // Animate progress bar indeterminately
    progressBar.style.width = '30%';

    state.eventSource = Api.streamBatchProgress(
        batchId,
        (data) => {
            if (data.type === 'initial_state') return;

            statusText.innerText = `${data.filename}: ${data.status} — ${data.detail || ''}`;

            // Increment progress
            const current = parseInt(progressBar.style.width) || 30;
            progressBar.style.width = Math.min(current + 5, 90) + '%';

            loadDocuments(state.selectedCategoryId);
        },
        (err) => {
            stopBatchMonitoring();
        }
    );
}

function stopBatchMonitoring() {
    if (state.eventSource) {
        state.eventSource.close();
        state.eventSource = null;
    }
    document.getElementById('batch-controls').classList.add('hidden');
    const progressBar = document.getElementById('upload-progress-bar');
    progressBar.style.width = '100%';
    setTimeout(() => {
        document.getElementById('upload-progress-container').style.display = 'none';
        progressBar.style.width = '0%';
    }, 800);
    document.getElementById('upload-status-text').innerText = 'Processing complete';
    state.activeBatchId = null;
    loadDocuments(state.selectedCategoryId);
    loadCategories(); // Refresh doc counts
}

async function terminateCurrentBatch() {
    if (!state.activeBatchId) return;
    try {
        const result = await Api.terminateBatch(state.activeBatchId);
        stopBatchMonitoring();
        showToast(`Batch terminated. Kept ${result.kept_completed} completed, removed ${result.deleted_incomplete} incomplete.`, 'warning');
    } catch (e) {
        showToast(e.message, 'error');
    }
}

async function burnDocument(id) {
    if (!confirm('Permanently burn this document and all its data?')) return;
    try {
        showLoading();
        await Api.burnDocument(id);
        loadDocuments(state.selectedCategoryId);
        loadCategories();
        showToast('Document burned', 'success');
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        hideLoading();
    }
}

async function cleanupDaily() {
    if (!confirm('Remove all expired daily documents?')) return;
    try {
        showLoading();
        await Api.cleanupDaily();
        loadDocuments(state.selectedCategoryId);
        loadCategories();
        showToast('Daily cleanup complete', 'success');
    } catch (e) {
        showToast(e.message, 'error');
    } finally {
        hideLoading();
    }
}

async function refreshDocuments() {
    if (state.selectedCategoryId) {
        await loadDocuments(state.selectedCategoryId);
        showToast('Refreshed', 'info');
    }
}

// ============================
// CHAT
// ============================
async function loadChats() {
    try {
        state.chats = await Api.listChats();
        renderSidebarChats();
    } catch (e) {
        console.error('Failed to load chats:', e);
    }
}

function renderSidebarChats() {
    const list = document.getElementById('chat-list');
    list.innerHTML = state.chats.map(chat => `
        <div class="nav-item ${state.selectedChatId === chat.chat_id ? 'active' : ''}" 
             onclick="selectChat('${chat.chat_id}')">
            <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width: 200px;">
                ${chat.title || chat.chat_id.substring(0, 10) + '...'}
            </span>
        </div>
    `).join('');
}

function startNewChat() {
    renderChatCategorySelection();
    openModal('new-chat-modal');
}

function renderChatCategorySelection() {
    const container = document.getElementById('chat-category-selection');
    if (state.categories.length === 0) {
        container.innerHTML = '<div style="padding: 1rem; text-align: center; color: var(--text-muted);">No categories available</div>';
        return;
    }

    container.innerHTML = state.categories.map(cat => `
        <div style="padding: 0.5rem; border-bottom: 1px solid var(--border-color); display: flex; align-items: center; gap: 0.5rem;">
            <input type="checkbox" name="chat-cat" value="${cat.category_id}" id="chk-${cat.category_id}" checked>
            <label for="chk-${cat.category_id}" style="cursor: pointer; flex: 1;">
                <div style="font-weight: 500; font-size: 0.9rem;">${cat.name}</div>
                <div style="font-size: 0.72rem; color: var(--text-muted);">${cat.document_count} documents</div>
            </label>
        </div>
    `).join('');
}

function toggleSelectAllCategories(select) {
    document.querySelectorAll('input[name="chat-cat"]').forEach(cb => cb.checked = select);
}

function confirmStartChat() {
    const selected = Array.from(document.querySelectorAll('input[name="chat-cat"]:checked')).map(cb => cb.value);

    if (selected.length === 0) {
        if (!confirm('No categories selected. The chat will search all documents. Proceed?')) return;
    }

    state.selectedCategoryIds = selected;
    state.selectedChatId = null;
    state.selectedCategoryId = null;

    document.getElementById('chat-messages').innerHTML = `
        <div class="message ai">
            <div class="markdown-content">
                <p>Hello! I'm <strong>PetroRAG</strong>. I'll search across <strong>${selected.length}</strong> selected categories.</p>
            </div>
        </div>
    `;

    closeModal('new-chat-modal');
    switchView('chat');
    renderSidebarChats();
}

async function selectChat(id) {
    state.selectedChatId = id;
    state.selectedCategoryId = null;

    try {
        const chatSession = await Api.getChat(id);
        renderChatHistory(chatSession.messages || []);
        switchView('chat');
        renderSidebarChats();
        renderSidebarCategories();
    } catch (e) {
        console.error('Failed to load chat:', e);
        showToast('Failed to load chat history', 'error');
    }
}

function renderChatHistory(messages) {
    const container = document.getElementById('chat-messages');
    if (messages.length === 0) {
        container.innerHTML = `
            <div class="message ai">
                <div class="markdown-content">
                    <p>Hello! I'm <strong>PetroRAG</strong>. Ask me anything about your uploaded documents.</p>
                </div>
            </div>
        `;
        return;
    }
    container.innerHTML = messages.map(msg => renderMessageContent(msg)).join('');
    scrollChatToBottom();
}

function renderMessageContent(msg) {
    let html = `<div class="message ${msg.role === 'user' ? 'user' : 'ai'}">`;

    // 1. Text Content (Markdown)
    let content = msg.content || '';
    try {
        content = marked.parse(content);
    } catch (e) {
        content = content.replace(/\n/g, '<br>');
    }

    // 1.5. Style inline citations: [filename.pdf, Page X-Y] → clickable badges
    if (msg.role !== 'user' && msg.inline_citations && msg.inline_citations.length > 0) {
        // Build lookup from filename to citation data
        const citationLookup = {};
        msg.inline_citations.forEach(c => {
            const key = c.filename;
            if (!citationLookup[key]) citationLookup[key] = c;
        });

        // Replace [filename, Page X-Y] patterns with styled badges
        content = content.replace(
            /\[([^\[\]]+?\.\w{2,5}),\s*Page[s]?\s*([\d\-–]+)\]/g,
            (match, filename, pageRange) => {
                const citation = citationLookup[filename];
                if (citation && citation.document_id) {
                    const downloadUrl = Api.getDownloadUrl(citation.document_id);
                    return `<a href="${downloadUrl}" target="_blank" class="inline-citation" title="${filename} — Page ${pageRange}">`
                         + `<i class="fa-solid fa-file-pdf"></i> ${filename}, p.${pageRange}</a>`;
                }
                // No matching citation data — still style it
                return `<span class="inline-citation"><i class="fa-solid fa-file-lines"></i> ${filename}, p.${pageRange}</span>`;
            }
        );
    } else if (msg.role !== 'user') {
        // Fallback: style any [filename.pdf, Page X-Y] without structured data
        content = content.replace(
            /\[([^\[\]]+?\.\w{2,5}),\s*Page[s]?\s*([\d\-–]+)\]/g,
            '<span class="inline-citation"><i class="fa-solid fa-file-lines"></i> $1, p.$2</span>'
        );
    }

    html += `<div class="markdown-content">${content}</div>`;

    // 2. Images
    const images = msg.image_results || msg.images || msg.image_paths;
    if (images && images.length > 0) {
        html += `<div class="image-gallery">`;
        images.forEach(img => {
            const rawSrc = typeof img === 'string' ? img : (img.image_path || img.url || img.path);
            if (rawSrc) {
                const src = Api.resolveImageUrl(rawSrc);
                html += `<img src="${src}" class="chat-image" onclick="window.open('${src}', '_blank')" title="Click to enlarge">`;
            }
        });
        html += `</div>`;
    }

    // 3. Sources summary (existing behavior)
    if (msg.sources) {
        html += `<div class="source-list"><div class="source-title">Sources</div>`;

        if (Array.isArray(msg.sources)) {
            msg.sources.forEach(source => {
                const text = typeof source === 'string' ? source : (source.filename || JSON.stringify(source));
                html += `<span class="source-item"><i class="fa-solid fa-file-lines"></i> ${text}</span>`;
            });
        } else if (typeof msg.sources === 'object') {
            Object.entries(msg.sources).forEach(([docId, sourceData]) => {
                let pages = [];
                let filename = `Doc ${docId.substring(0, 8)}...`;

                if (Array.isArray(sourceData)) {
                    pages = sourceData;
                } else if (typeof sourceData === 'object') {
                    pages = sourceData.pages || [];
                    if (sourceData.filename) filename = sourceData.filename;
                }

                const pageStr = Array.isArray(pages) ? pages.join(', ') : pages;
                const downloadUrl = Api.getDownloadUrl(docId);

                html += `<a href="${downloadUrl}" target="_blank" class="source-item" title="Download ${filename}">
                            <i class="fa-solid fa-file-pdf"></i> ${filename} (p. ${pageStr})
                         </a>`;
            });
        }

        html += `</div>`;
    }

    html += `</div>`;
    return html;
}

// ============================
// CHAT IMAGE HANDLING
// ============================
let selectedChatImages = [];

function handleChatImageSelection(files) {
    Array.from(files).forEach(file => {
        if (selectedChatImages.length >= 10) return;
        selectedChatImages.push(file);
    });
    renderChatImagePreviews();
}

function removeChatImage(index) {
    selectedChatImages.splice(index, 1);
    renderChatImagePreviews();
}

function renderChatImagePreviews() {
    const previewContainer = document.getElementById('chat-image-preview');
    previewContainer.innerHTML = '';

    if (selectedChatImages.length === 0) {
        previewContainer.style.display = 'none';
        return;
    }

    previewContainer.style.display = 'flex';
    selectedChatImages.forEach((file, index) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const div = document.createElement('div');
            div.style.position = 'relative';
            div.innerHTML = `
                <img src="${e.target.result}" style="height: 56px; border-radius: 6px; border: 1px solid var(--border-color);">
                <button onclick="removeChatImage(${index})" 
                        style="position: absolute; top: -6px; right: -6px; background: var(--danger-color); color: white; border: none; border-radius: 50%; width: 18px; height: 18px; font-size: 9px; cursor: pointer; display: flex; align-items: center; justify-content: center;">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            `;
            previewContainer.appendChild(div);
        };
        reader.readAsDataURL(file);
    });
}

// ============================
// SEND MESSAGE (UNIFIED — handles text + images)
// ============================
async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    if (!message && selectedChatImages.length === 0) return;

    const container = document.getElementById('chat-messages');
    const sendBtn = document.getElementById('chat-send-btn');

    // Capture and clear images before rendering
    const imagesToSend = [...selectedChatImages];
    selectedChatImages = [];
    renderChatImagePreviews();
    document.getElementById('chat-image-input').value = '';

    // Convert images to data URLs for display, then show the user message
    const imageDataUrls = [];
    if (imagesToSend.length > 0) {
        const readPromises = imagesToSend.map(file => new Promise((resolve) => {
            const reader = new FileReader();
            reader.onload = (e) => resolve(e.target.result);
            reader.onerror = () => resolve(null);
            reader.readAsDataURL(file);
        }));
        const results = await Promise.all(readPromises);
        results.forEach(url => { if (url) imageDataUrls.push(url); });
    }

    // Show user message with inline image thumbnails
    container.innerHTML += renderMessageContent({
        role: 'user',
        content: message,
        image_paths: imageDataUrls
    });
    input.value = '';
    scrollChatToBottom();

    // Show typing indicator
    const typingId = 'typing-' + Date.now();
    container.innerHTML += `<div class="typing-indicator" id="${typingId}"><span></span><span></span><span></span></div>`;
    scrollChatToBottom();

    // Disable send button
    sendBtn.disabled = true;
    sendBtn.innerHTML = '<span class="spinner-inline"></span>';

    // Create AI message container for streaming
    const aiMsgId = 'ai-msg-' + Date.now();

    // Stream the response word-by-word
    await Api.sendMessageStream(
        message,
        state.selectedChatId,
        state.selectedCategoryIds,
        imagesToSend,
        // onToken: append each token to the AI message
        (token) => {
            // Remove typing indicator on first token
            const typingEl = document.getElementById(typingId);
            if (typingEl) {
                typingEl.remove();
                // Create the AI message bubble
                container.innerHTML += `<div class="message ai" id="${aiMsgId}"><div class="markdown-content" id="${aiMsgId}-content"></div></div>`;
            }
            const contentEl = document.getElementById(`${aiMsgId}-content`);
            if (contentEl) {
                contentEl.textContent += token;
                scrollChatToBottom();
            }
        },
        // onDone: render final content with markdown, citations, sources, images
        (data) => {
            // Remove typing indicator if still present (no tokens were received)
            const typingEl = document.getElementById(typingId);
            if (typingEl) {
                typingEl.remove();
            }

            const aiMsg = {
                role: 'ai',
                content: data.answer,
                sources: data.sources,
                inline_citations: data.inline_citations || [],
                image_results: data.image_results,
                images: data.images
            };

            // Replace the streaming div with fully-rendered content
            const existingEl = document.getElementById(aiMsgId);
            if (existingEl) {
                existingEl.outerHTML = renderMessageContent(aiMsg);
            } else {
                container.innerHTML += renderMessageContent(aiMsg);
            }
            scrollChatToBottom();

            if (!state.selectedChatId && data.chat_id) {
                state.selectedChatId = data.chat_id;
                loadChats();
            }

            sendBtn.disabled = false;
            sendBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i>';
        },
        // onError
        (err) => {
            const typingEl = document.getElementById(typingId);
            if (typingEl) typingEl.remove();

            container.innerHTML += `<div class="message ai"><div class="markdown-content" style="color: var(--danger-color);"><i class="fa-solid fa-circle-xmark"></i> Error: ${err.message}</div></div>`;
            scrollChatToBottom();
            showToast('Failed to send message', 'error');

            sendBtn.disabled = false;
            sendBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i>';
        }
    );
}

function scrollChatToBottom() {
    const container = document.getElementById('chat-messages');
    setTimeout(() => {
        container.scrollTop = container.scrollHeight;
    }, 50);
}

async function deleteChat(id) {
    if (!confirm('Delete this chat history?')) return;
    try {
        await Api.deleteChat(id);
        state.selectedChatId = null;
        await loadChats();
        switchView('dashboard');
        showToast('Chat deleted', 'success');
    } catch (e) {
        showToast(e.message, 'error');
    }
}

// ============================
// DASHBOARD STATS
// ============================
function updateDashboardStats() {
    document.getElementById('stat-categories').innerText = state.categories.length;
    const totalDocs = state.categories.reduce((acc, cat) => acc + cat.document_count, 0);
    document.getElementById('stat-documents').innerText = totalDocs;
    document.getElementById('stat-chats').innerText = state.chats.length;
}

// ============================
// MODAL UTILS
// ============================
function openModal(id) {
    document.getElementById(id).classList.add('active');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

// ============================
// GLOBAL EXPORTS
// ============================
window.openModal = openModal;
window.closeModal = closeModal;
window.createCategory = createCategory;
window.selectCategory = selectCategory;
window.startNewChat = startNewChat;
window.selectChat = selectChat;
window.sendMessage = sendMessage;
window.deleteCategory = deleteCategory;
window.openRenameModal = openRenameModal;
window.submitRenameCategory = submitRenameCategory;
window.deleteChat = deleteChat;
window.refreshDocuments = refreshDocuments;
window.cleanupDaily = cleanupDaily;
window.burnDocument = burnDocument;
window.terminateCurrentBatch = terminateCurrentBatch;
window.confirmStartChat = confirmStartChat;
window.toggleSelectAllCategories = toggleSelectAllCategories;
window.toggleSidebar = toggleSidebar;
window.scrollChatToBottom = scrollChatToBottom;
window.downloadDocument = downloadDocument;
window.removeChatImage = removeChatImage;
