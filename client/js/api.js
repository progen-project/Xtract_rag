/**
 * API Wrapper for PetroRAG
 */
const API_BASE = 'http://localhost:8001/client-api';

class Api {
    // --- Categories ---
    static async listCategories() {
        const res = await fetch(`${API_BASE}/categories`);
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
        return res.json();
    }

    static async uploadDocuments(categoryId, files, isDaily = false) {
        const formData = new FormData();
        for (let i = 0; i < files.length; i++) {
            formData.append('files', files[i]);
        }
        
        const endpoint = isDaily ? 'documents/upload/daily' : 'documents/upload';
        const res = await fetch(`${API_BASE}/${endpoint}/${categoryId}`, {
            method: 'POST',
            body: formData
        });

        if (!res.ok) throw new Error('Upload failed');
        return res.json(); // Returns array of uploaded docs with batch_id
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
        
        evtSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            onMessage(data);
        };

        evtSource.onerror = (err) => {
            console.error("EventSource failed:", err);
            evtSource.close();
            if (onError) onError(err);
        };

        return evtSource; // Return to allow closing
    }

    // --- Chat ---
    static async listChats() {
        const res = await fetch(`${API_BASE}/chat`);
        return res.json();
    }

    static async deleteChat(chatId) {
        const res = await fetch(`${API_BASE}/chat/${chatId}`, {
            method: 'DELETE'
        });
        if (!res.ok) throw new Error('Failed to delete chat');
        return res.json();
    }

    static async sendMessage(message, chatId, categoryIds = []) {
        const formData = new FormData();
        formData.append('message', message);
        if (chatId) formData.append('chat_id', chatId);
        if (categoryIds.length > 0) {
            // API expects stringified JSON or comma-separated
             formData.append('category_ids', JSON.stringify(categoryIds));
        }
        
        const res = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            body: formData
        });

        if (!res.ok) throw new Error('Message sending failed');
        return res.json();
    }
}
