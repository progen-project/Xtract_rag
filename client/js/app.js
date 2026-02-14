/**
 * Main Application Logic
 */

// State
let state = {
    categories: [],
    chats: [],
    documents: [],
    currentView: 'dashboard',
    selectedCategoryId: null,
    selectedChatId: null,
    activeBatchId: null,
    eventSource: null
};

// --- Initialization ---
document.addEventListener('DOMContentLoaded', async () => {
    initEventListeners();
    await refreshAll();
});

async function refreshAll() {
    await loadCategories();
    await loadChats();
    updateDashboardStats();
}

function initEventListeners() {
    // File Upload
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');

    dropZone.addEventListener('click', () => fileInput.click());
    
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'var(--primary-color)';
    });

    dropZone.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'var(--border-color)';
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.style.borderColor = 'var(--border-color)';
        if (e.dataTransfer.files.length) {
            handleUpload(e.dataTransfer.files);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleUpload(e.target.files);
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

    // Chat Input Enter Key
    document.getElementById('chat-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
}

// ... (Rest of navigation code) ...

// --- Chat Image Handling ---
let selectedChatImages = [];

function handleChatImageSelection(files) {
    const previewContainer = document.getElementById('chat-image-preview');
    previewContainer.style.display = 'flex';
    
    Array.from(files).forEach(file => {
        if (selectedChatImages.length >= 10) return; // Limit 10
        selectedChatImages.push(file);
        
        const reader = new FileReader();
        reader.onload = (e) => {
            const div = document.createElement('div');
            div.style.position = 'relative';
            div.innerHTML = `
                <img src="${e.target.result}" style="height: 60px; border-radius: 4px; border: 1px solid var(--border-color);">
                <button onclick="removeChatImage(${selectedChatImages.length - 1})" 
                        style="position: absolute; top: -5px; right: -5px; background: red; color: white; border: none; border-radius: 50%; width: 18px; height: 18px; font-size: 10px; cursor: pointer;">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            `;
            previewContainer.appendChild(div);
            // Re-render all to fix indices? Actually simple append is buggy for removal index. 
            // Better to re-render all.
            renderChatImagePreviews();
        };
        reader.readAsDataURL(file);
    });
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
                <img src="${e.target.result}" style="height: 60px; border-radius: 4px; border: 1px solid var(--border-color);">
                <button onclick="removeChatImage(${index})" 
                        style="position: absolute; top: -5px; right: -5px; background: red; color: white; border: none; border-radius: 50%; width: 18px; height: 18px; font-size: 10px; cursor: pointer;">
                    <i class="fa-solid fa-xmark"></i>
                </button>
            `;
            previewContainer.appendChild(div);
        };
        reader.readAsDataURL(file);
    });
}

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    
    // Allow sending if there are images, even if message is empty? 
    // Usually we want at least some context, but images alone might be valid.
    if (!message && selectedChatImages.length === 0) return;
    
    // Add user message to UI
    const container = document.getElementById('chat-messages');
    
    // Create preview data for UI
    let uiImages = [];
    if (selectedChatImages.length > 0) {
         // We can't synchronously get base64 here easily without wait.
         // But we can just show "Sending X images..." or try to show previews if we stored them.
         // For simplicity, let's just say "[Uploaded X Images]" or render text.
         // Ideally we render them.
    }

    // Improve UI rendering for pending user message
    // We'll rely on the fact that we clear the input and the user sees the response eventually?
    // No, better to show immediate feedback.
    
    let userMsgContent = message;
    if (selectedChatImages.length > 0) {
        userMsgContent += `\n\n*[Uploading ${selectedChatImages.length} image(s)...]*`;
    }

    container.innerHTML += renderMessageContent({ role: 'user', content: userMsgContent });
    input.value = '';
    
    // Clear images from UI immediately or wait? 
    // Clear immediately to prevent double send.
    const imagesToSend = [...selectedChatImages];
    selectedChatImages = [];
    renderChatImagePreviews();
    document.getElementById('chat-image-input').value = ''; // reset input
    
    container.scrollTop = container.scrollHeight;
    
    try {
        const res = await Api.sendMessage(message, state.selectedChatId, state.selectedCategoryIds, imagesToSend);
        console.log("Chat Response:", res);
        
        // Add AI response
        const aiMsg = {
            role: 'ai',
            content: res.answer,
            sources: res.sources,
            image_results: res.image_results, 
            images: res.images
        };
        
        container.innerHTML += renderMessageContent(aiMsg);
        container.scrollTop = container.scrollHeight;
        
        if (!state.selectedChatId && res.chat_id) {
            state.selectedChatId = res.chat_id;
            loadChats(); 
        }
    } catch (e) {
        container.innerHTML += `<div class="message ai" style="color:red">Error: ${e.message}</div>`;
    }
}
// --- Navigation & Views ---
function switchView(viewName) {
    document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
    document.getElementById(`view-${viewName}`).classList.add('active');
    state.currentView = viewName;

    // Update Header
    const title = document.getElementById('page-title');
    const subtitle = document.getElementById('page-subtitle');
    const actions = document.getElementById('header-actions');
    actions.innerHTML = ''; // Clear actions

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
            
            // Add Rename/Delete buttons
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
        subtitle.innerText = state.selectedChatId ? 'History' : 'New Session';
        
        if (state.selectedChatId) {
            actions.innerHTML = `
                <button class="btn btn-danger" onclick="deleteChat('${state.selectedChatId}')">
                    <i class="fa-solid fa-trash"></i> Delete Chat
                </button>
            `;
        }
    }
}

// --- Categories ---
async function loadCategories() {
    try {
        state.categories = await Api.listCategories();
        renderSidebarCategories();
    } catch (e) {
        console.error(e);
    }
}

function renderSidebarCategories() {
    const list = document.getElementById('category-list');
    list.innerHTML = state.categories.map(cat => `
        <div class="nav-item ${state.selectedCategoryId === cat.category_id ? 'active' : ''}" 
             onclick="selectCategory('${cat.category_id}')">
            <span>${cat.name}</span>
            <span class="text-muted" style="font-size: 0.75rem">${cat.document_count}</span>
        </div>
    `).join('');
}

function selectCategory(id) {
    state.selectedCategoryId = id;
    state.selectedChatId = null;
    loadCategories(); // Re-render for active state
    switchView('category');
}

async function createCategory() {
    const name = document.getElementById('new-cat-name').value;
    const desc = document.getElementById('new-cat-desc').value;
    
    if (!name) return alert('Name is required');
    
    try {
        await Api.createCategory(name, desc);
        closeModal('create-category-modal');
        await loadCategories();
    } catch (e) {
        alert(e.message);
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
    const name = document.getElementById('rename-cat-name').value;
    const desc = document.getElementById('rename-cat-desc').value;
    
    try {
        await Api.updateCategory(id, name, desc);
        closeModal('rename-category-modal');
        await loadCategories();
        switchView('category'); // Refresh header
    } catch (e) {
        alert(e.message);
    }
}

async function deleteCategory(id) {
    if (!confirm('Are you sure? This will not delete documents but will remove the category organization.')) return;
    try {
        await Api.deleteCategory(id);
        state.selectedCategoryId = null;
        await loadCategories();
        switchView('dashboard');
    } catch (e) {
        alert(e.message);
    }
}

// --- Documents ---
async function loadDocuments(categoryId) {
    try {
        state.documents = await Api.listDocuments(categoryId);
        renderDocuments();
    } catch (e) {
        console.error(e);
    }
}

function renderDocuments() {
    const tbody = document.getElementById('documents-list');
    if (state.documents.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 2rem;">No documents found</td></tr>';
        return;
    }

    tbody.innerHTML = state.documents.map(doc => `
        <tr>
            <td>${doc.filename}</td>
            <td><span class="status-badge status-${doc.status.toLowerCase()}">${doc.status}</span></td>
            <td>${doc.is_daily ? '<span style="color:red">Daily</span>' : 'Permanent'}</td>
            <td>${new Date(doc.upload_date).toLocaleDateString()}</td>
            <td>
                <button class="btn btn-secondary" style="padding: 0.25rem 0.5rem;" onclick="burnDocument('${doc.document_id}')">
                    <i class="fa-solid fa-fire"></i>
                </button>
            </td>
        </tr>
    `).join('');
    
    updateDashboardStats();
}

async function handleUpload(files) {
    const isDaily = document.getElementById('is-daily').checked;
    
    try {
        // 1. Upload
        document.getElementById('upload-status-text').innerText = "Uploading...";
        const docs = await Api.uploadDocuments(state.selectedCategoryId, files, isDaily);
        
        if (docs.length > 0 && docs[0].batch_id) {
            startBatchMonitoring(docs[0].batch_id);
        }
        
        await loadDocuments(state.selectedCategoryId); // Show pending docs
    } catch (e) {
        alert(e.message);
    }
}

function startBatchMonitoring(batchId) {
    state.activeBatchId = batchId;
    document.getElementById('batch-controls').classList.remove('hidden');
    document.getElementById('upload-progress-container').style.display = 'block';
    const progressBar = document.getElementById('upload-progress-bar');
    const statusText = document.getElementById('upload-status-text');

    state.eventSource = Api.streamBatchProgress(
        batchId,
        (data) => {
            if (data.type === 'initial_state') return;
            
            // Simple logic: If we get an event, assume some progress.
            // A real progress bar needs total files vs processed files count from backend.
            // For now, we just animate/show status.
            
            statusText.innerText = `${data.filename}: ${data.status} - ${data.detail || ''}`;
            
            // If all done logic? Backend doesn't send "Batch Complete" event yet explicitly except per file.
            // We can refresh the list periodically.
            loadDocuments(state.selectedCategoryId);
        },
        (err) => {
            // End of stream or error
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
    document.getElementById('upload-progress-container').style.display = 'none';
    document.getElementById('upload-status-text').innerText = "Upload Complete / Stream Ended";
    state.activeBatchId = null;
    loadDocuments(state.selectedCategoryId);
}

async function terminateCurrentBatch() {
    if (!state.activeBatchId) return;
    try {
        await Api.terminateBatch(state.activeBatchId);
        stopBatchMonitoring();
        alert('Batch terminated');
    } catch (e) {
        alert(e.message);
    }
}

async function burnDocument(id) {
    if(!confirm("Permanently burn this document?")) return;
    try {
        await Api.burnDocument(id);
        loadDocuments(state.selectedCategoryId);
    } catch (e) {
        alert(e.message);
    }
}

async function cleanupDaily() {
    if(!confirm("Remove all expired daily documents?")) return;
    try {
        await Api.cleanupDaily();
        loadDocuments(state.selectedCategoryId);
    } catch (e) {
        alert(e.message);
    }
}

async function refreshDocuments() {
    if (state.selectedCategoryId) loadDocuments(state.selectedCategoryId);
}

// --- Chat ---
async function loadChats() {
    try {
        state.chats = await Api.listChats();
        renderSidebarChats();
    } catch (e) {
        console.error(e);
    }
}

function renderSidebarChats() {
    const list = document.getElementById('chat-list');
    list.innerHTML = state.chats.map(chat => `
        <div class="nav-item ${state.selectedChatId === chat.chat_id ? 'active' : ''}" 
             onclick="selectChat('${chat.chat_id}')">
            <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width: 180px;">
                ${chat.title || chat.chat_id.substring(0, 8)}...
            </span>
        </div>
    `).join('');
}

function startNewChat() {
    // Open Modal instead of direct start
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
                <div style="font-weight: 500;">${cat.name}</div>
                <div style="font-size: 0.75rem; color: var(--text-muted);">${cat.document_count} documents</div>
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
        if (!confirm("No categories selected. Ensure you want to search EVERYTHING (if allowed) or nothing? Proceed?")) return;
    }
    
    // Store selected categories for this session context
    state.selectedCategoryIds = selected;
    state.selectedChatId = null;
    state.selectedCategoryId = null; // Clear single category view selection
    
    // Reset UI
    document.getElementById('chat-messages').innerHTML = `
        <div class="message ai">
            Hello! I am PetroRAG. I will search across <b>${selected.length}</b> selected categories.
        </div>
    `;
    
    closeModal('new-chat-modal');
    switchView('chat');
    loadChats(); // clear selection in sidebar
}

async function selectChat(id) {
    state.selectedChatId = id;
    state.selectedCategoryId = null;
    
    // Load history
    try {
        // Currently API doesn't have "get chat details" endpoint with messages returned in list?
        // Wait, standard get_chat returns session object. Does it have messages?
        // Let's check schema. Usually yes.
        // Assuming GetChat returns { messages: [...] }
        
        // Use GET /api/chat/{id}
        const res = await fetch(`${API_BASE}/chat/${id}`); // Direct fetch or add to Api.js
        const chatSession = await res.json();
        
        renderChatHistory(chatSession.messages || []);
        switchView('chat');
        loadChats();
    } catch (e) {
        console.error(e);
    }
}

function renderChatHistory(messages) {
    const container = document.getElementById('chat-messages');
    container.innerHTML = messages.map(msg => renderMessageContent(msg)).join('');
    container.scrollTop = container.scrollHeight;
}

function renderMessageContent(msg) {
    let html = `<div class="message ${msg.role === 'user' ? 'user' : 'ai'}">`;
    
    // 1. Content (Text)
    // Use marked.js for Markdown parsing
    let content = msg.content;
    try {
        content = marked.parse(content);
    } catch (e) {
        console.error("Markdown parsing failed:", e);
        content = content.replace(/\n/g, '<br>'); // Fallback
    }
    
    html += `<div class="markdown-content">${content}</div>`;
    
    // 2. Images (if available) - Handle 'image_results' (rich), 'images' (legacy), 'image_paths' (history)
    const images = msg.image_results || msg.images || msg.image_paths;
    if (images && images.length > 0) {
        html += `<div class="image-gallery">`;
        images.forEach(img => {
            // Check if img is object or string (URL)
            // Server ImageSearchResult has 'image_path'
            const src = typeof img === 'string' ? img : (img.image_path || img.url || img.path);
            
            if (src) {
                // Determine if it needs full URL prefix if relative
                // Usually backend sends relative path /static/... or full URL
                // Let's assume it works or is proxied.
                // If it starts with 'e:', it's a local file path which browser won't load.
                // We might need a backend endpoint to serve these images if they aren't static URLs.
                // BUT for now, let's try to render what we get.
                
                html += `<img src="${src}" class="chat-image" onclick="window.open('${src}', '_blank')">`;
            }
        });
        html += `</div>`;
    }

    // 3. Sources (if available) - Handle both old List and new Dict
    if (msg.sources) {
        html += `<div class="source-list"><div class="source-title">Sources:</div>`;
        
        if (Array.isArray(msg.sources)) {
            // Old list format
            msg.sources.forEach(source => {
                const text = typeof source === 'string' ? source : (source.filename || JSON.stringify(source));
                html += `<span class="source-item">${text}</span>`;
            });
        } else if (typeof msg.sources === 'object') {
            // New Dict format: { "doc_id": { filename: "foo.pdf", pages: [1, 2] } }
            Object.entries(msg.sources).forEach(([docId, sourceData]) => {
                // Check if sourceData is just pages array (backward compatibility) or rich object
                let pages = [];
                let filename = `Doc ${docId.substring(0,8)}...`;
                
                if (Array.isArray(sourceData)) {
                    pages = sourceData;
                } else if (typeof sourceData === 'object') {
                    pages = sourceData.pages || [];
                    if (sourceData.filename) {
                        filename = sourceData.filename;
                    }
                }
                
                const pageStr = Array.isArray(pages) ? pages.join(', ') : pages;
                
                // Create download link
                const downloadUrl = `${API_BASE}/documents/${docId}/download`;
                
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

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;
    
    // Add user message to UI
    const container = document.getElementById('chat-messages');
    container.innerHTML += renderMessageContent({ role: 'user', content: message });
    input.value = '';
    container.scrollTop = container.scrollHeight;
    
    try {
        // Use the selected categories from the new chat modal
        // If state.selectedCategoryIds is undefined (e.g. existing chat loaded), we might need to rely on backend session context 
        // OR the user continues without specific context if it wasn't stored.
        // For new questions in existing chats, usually the history defines the context, but if RAG allows narrowing:
        // We will send it if available.
        
        const res = await Api.sendMessage(message, state.selectedChatId, state.selectedCategoryIds);
        console.log("Chat Response:", res); // Debug log
        
        // Add AI response with rich content
        const aiMsg = {
            role: 'ai',
            content: res.answer,
            sources: res.sources,
            image_results: res.image_results, // using new field
            images: res.images // fallback
        };
        
        container.innerHTML += renderMessageContent(aiMsg);
        container.scrollTop = container.scrollHeight;
        
        if (!state.selectedChatId && res.chat_id) {
            state.selectedChatId = res.chat_id;
            loadChats(); // Refresh list to show new chat
        }
    } catch (e) {
        container.innerHTML += `<div class="message ai" style="color:red">Error: ${e.message}</div>`;
    }
}

async function deleteChat(id) {
    if (!confirm("Delete this chat history?")) return;
    try {
        await Api.deleteChat(id);
        startNewChat();
        await loadChats();
    } catch (e) {
        alert(e.message);
    }
}

// --- Utils ---
function updateDashboardStats() {
    document.getElementById('stat-categories').innerText = state.categories.length;
    // Count total documents across categories
    const totalDocs = state.categories.reduce((acc, cat) => acc + cat.document_count, 0);
    document.getElementById('stat-documents').innerText = totalDocs;
    document.getElementById('stat-chats').innerText = state.chats.length;
}

function openModal(id) {
    document.getElementById(id).classList.add('active');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

// Global expose
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
