/**
 * PetroRAG API Client
 * Wraps all communication with the Python Client Proxy (port 8001).
 */
// Detect environment or use config
const HOST = window.location.hostname;
const PROTOCOL = window.location.protocol;
const PORT_CLIENT = '8001';
const PORT_BACKEND = '8000';

// If running on localhost, use distinct ports.
// If deployed (e.g. via Nginx reverse proxy), these usually map to paths like /api or /client-api
// But for this Docker setup where ports are exposed directly:
// const API_BASE = `${PROTOCOL}//${HOST}:${PORT_CLIENT}/client-api`;
// const BACKEND_BASE = `${PROTOCOL}//${HOST}:${PORT_BACKEND}`;

// Docker on github code space :
// function replacePortInHostname(hostname, newPort) {
//   // Codespaces format: name-8002.app.github.dev
//   return hostname.replace(/-\d+\.app\.github\.dev$/, `-${newPort}.app.github.dev`);
// }

// const API_HOST = replacePortInHostname(HOST, PORT_CLIENT);
// const BACKEND_HOST = replacePortInHostname(HOST, PORT_BACKEND);

// const API_BASE = `${PROTOCOL}//${API_HOST}/client-api`;
// const BACKEND_BASE = `${PROTOCOL}//${BACKEND_HOST}`;

const API_BASE = "/client-api";
const BACKEND_BASE = "/api";

class Api {
    /**
     * Resolve image paths to full URLs served by the backend.
     * Paths like "extracted_images/..." or "chat_images/..." become "http://localhost:8000/extracted_images/..."
     */
    static resolveImageUrl(path) {
        if (!path) return '';
        if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('data:')) return path;
        // Strip leading ./ or /
        const cleaned = path.replace(/^\.?\//, '');
        return `${BACKEND_BASE}/${cleaned}`;
    }
    // --- Categories ---
    static async listCategories() {
        const res = await fetch(`${API_BASE}/categories`);
        if (!res.ok) throw new Error('Failed to load categories');
        return res.json();
    }

    static async createCategory(name, description) {
        const res = await fetch(`${API_BASE}/categories`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description })
        });
        if (!res.ok) throw new Error('Failed to create category');
        return res.json();
    }

    static async updateCategory(categoryId, name, description) {
        const res = await fetch(`${API_BASE}/categories/${categoryId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description })
        });
        if (!res.ok) throw new Error('Failed to update category');
        return res.json();
    }

    static async deleteCategory(categoryId) {
        const res = await fetch(`${API_BASE}/categories/${categoryId}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error('Failed to delete category');
        return res.json();
    }

    // --- Documents ---
    static async listDocuments(categoryId) {
        let url = `${API_BASE}/documents`;
        if (categoryId) url += `?category_id=${categoryId}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error('Failed to load documents');
        return res.json();
    }

    static async getDocument(documentId) {
        const res = await fetch(`${API_BASE}/documents/${documentId}`);
        if (!res.ok) throw new Error('Failed to get document');
        return res.json();
    }

    static async uploadDocuments(categoryId, files, isDaily = false) {
        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            formData.append('files', files[i]);
        }

        const res = await fetch(`${API_BASE}/documents/upload/${categoryId}`, {
            method: 'POST',
            body: formData
        });

        if (!res.ok) throw new Error('Upload failed');
        return res.json();
    }

    static async deleteDocument(documentId) {
        const res = await fetch(`${API_BASE}/documents/${documentId}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error('Failed to delete document');
        return res.json();
    }

    static async burnDocument(documentId) {
        const res = await fetch(`${API_BASE}/documents/${documentId}/burn`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error('Failed to burn document');
        return res.json();
    }

    static getDownloadUrl(documentId) {
        return `${API_BASE}/documents/${documentId}/download`;
    }

    
    /**
     * Download a document with the correct filename.
     * Uses fetch + blob to bypass cross-origin download attribute limitations.
     */
    static async downloadDocumentBlob(documentId, suggestedFilename) {
        const res = await fetch(`${API_BASE}/documents/${documentId}/download`);
        if (!res.ok) throw new Error('Download failed');

        // Extract filename from Content-Disposition header
        const disp = res.headers.get('content-disposition') || '';
        let filename = suggestedFilename || 'document.pdf';
        const match = disp.match(/filename="?([^";\n]+)"?/);
        if (match) filename = match[1].trim();

        // Create blob URL (same-origin) so download attribute works
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    static async cleanupDaily() {
        const res = await fetch(`${API_BASE}/documents/cleanup/daily`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error('Cleanup failed');
        return res.json();
    }

    // --- Batches ---
    static async getBatchStatus(batchId) {
        try {
            const res = await fetch(`${API_BASE}/batches/${batchId}`);
            if (!res.ok) return null;
            return res.json();
        } catch (e) {
            return null;
        }
    }

    static async terminateBatch(batchId) {
        const res = await fetch(`${API_BASE}/batches/${batchId}/terminate`, {
            method: 'POST'
        });
        if (!res.ok) throw new Error('Termination failed');
        return res.json();
    }

    static streamBatchProgress(batchId, onMessage, onError) {
        const evtSource = new EventSource(`${API_BASE}/batches/${batchId}/progress`);
        let batchCompleted = false;
        
        evtSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            onMessage(data);
            
            // ✅ تتبع لو الباتش خلص
            if (data.type === 'initial_state') {
                // initial state - مش خلص بعد
            } else if (data.status === 'completed' || 
                    data.status === 'failed' || 
                    data.status === 'cancelled') {
                batchCompleted = true;
            }
        };
        
        evtSource.onerror = (err) => {
            evtSource.close();
            
            // ✅ لو الباتش خلص، ده مش error حقيقي
            if (!batchCompleted) {
                console.error("EventSource failed:", err);
                if (onError) onError(err);
            }
        };
        
        return evtSource;
    }

    // --- Chat ---
    static async listChats() {
        const res = await fetch(`${API_BASE}/chat`);
        if (!res.ok) throw new Error('Failed to load chats');
        return res.json();
    }

    static async getChat(chatId) {
        const res = await fetch(`${API_BASE}/chat/${chatId}`);
        if (!res.ok) throw new Error('Failed to load chat');
        return res.json();
    }

    static async deleteChat(chatId) {
        const res = await fetch(`${API_BASE}/chat/${chatId}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error('Failed to delete chat');
        return res.json();
    }

    static async sendMessage(message, chatId, categoryIds = [], images = []) {
        const formData = new FormData();
        formData.append('message', message);
        if (chatId) formData.append('chat_id', chatId);
        if (categoryIds && categoryIds.length > 0) {
            formData.append('category_ids', JSON.stringify(categoryIds));
        }

        // Attach image files
        if (images && images.length > 0) {
            images.forEach(img => formData.append('images', img));
        }

        const res = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            body: formData
        });

        if (!res.ok) throw new Error('Message sending failed');
        return res.json();
    }

    /**
     * Stream a chat message response word-by-word via SSE.
     * @param {string} message
     * @param {string|null} chatId
     * @param {string[]} categoryIds
     * @param {File[]} images
     * @param {function} onToken  - called with each text token
     * @param {function} onDone   - called with final metadata object
     * @param {function} onError  - called on error
     */
    static async sendMessageStream(message, chatId, categoryIds = [], images = [], onToken, onDone, onError) {
        const formData = new FormData();
        formData.append('message', message);
        if (chatId) formData.append('chat_id', chatId);
        if (categoryIds && categoryIds.length > 0) {
            formData.append('category_ids', JSON.stringify(categoryIds));
        }
        if (images && images.length > 0) {
            images.forEach(img => formData.append('images', img));
        }

        try {
            const res = await fetch(`${BACKEND_BASE}/api/chat/stream`, {
                method: 'POST',
                body: formData
            });

            if (!res.ok) throw new Error('Stream request failed');

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });

                // Parse SSE lines
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep incomplete line in buffer

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.done) {
                                if (onDone) onDone(data);
                            } else if (data.token) {
                                if (onToken) onToken(data.token);
                            } else if (data.error) {
                                if (onError) onError(new Error(data.error));
                            }
                        } catch (e) {
                            // skip unparseable lines
                        }
                    }
                }
            }
        } catch (e) {
            if (onError) onError(e);
        }
    }

    // --- Query ---
    static async query(queryText, categoryIds = null, topK = 5) {
        const body = { query: queryText, top_k: topK };
        if (categoryIds) body.category_ids = categoryIds;

        const res = await fetch(`${API_BASE}/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) throw new Error('Query failed');
        return res.json();
    }

    static async searchImages(queryText = null, imageBase64 = null, categoryIds = null) {
        const body = {};
        if (queryText) body.query_text = queryText;
        if (imageBase64) body.query_image_base64 = imageBase64;
        if (categoryIds) body.category_ids = categoryIds;

        const res = await fetch(`${API_BASE}/query/image-search`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        if (!res.ok) throw new Error('Image search failed');
        return res.json();
    }
}
