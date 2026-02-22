"""
Service for tracking file processing status with SSE support.
"""
import asyncio
from typing import Dict, AsyncGenerator
from collections import defaultdict
import json
from datetime import datetime

import logging

logger = logging.getLogger(__name__)


class ProcessingStatusManager:
    """
    Singleton service to track file processing status in memory.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProcessingStatusManager, cls).__new__(cls)
            cls._instance._batches = defaultdict(dict)
            cls._instance._events = defaultdict(asyncio.Queue)
        return cls._instance

    def init_batch(self, batch_id: str, files: list):
        """Initialize tracking for a batch of files."""
        for file in files:
            self._batches[batch_id][file.filename] = {
                "status": "pending",
                "detail": "Waiting to start...",
                "timestamp": datetime.utcnow().isoformat()
            }

    async def update_file_status(self, batch_id: str, filename: str, status: str, detail: str = None):
        """Update status for a specific file in a batch."""
        if batch_id in self._batches and filename in self._batches[batch_id]:
            self._batches[batch_id][filename].update({
                "status": status,
                "detail": detail,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # Notify subscribers
            event_data = {
                "batch_id": batch_id,
                "filename": filename,
                "status": status,
                "detail": detail,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Put event in the queue for this batch
            if batch_id in self._events:
                await self._events[batch_id].put(event_data)

    async def stream_status(self, batch_id: str) -> AsyncGenerator[str, None]:
        """Stream status updates for a batch."""
        # Check if batch exists
        if batch_id not in self._batches:
            yield f"data: {json.dumps({'error': 'Batch not found'})}\n\n"
            return

        # Send initial state
        initial_state = {
            "type": "initial_state",
            "batch_id": batch_id,
            "files": self._batches[batch_id]
        }
        yield f"data: {json.dumps(initial_state)}\n\n"
        
        # Stream updates
        queue = self._events[batch_id]
        try:
            while True:
                try:
                    # Wait for event with timeout for heartbeat
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Send heartbeat to keep connection alive
                    heartbeat = {
                        "type": "heartbeat",
                        "batch_id": batch_id,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                    yield f"data: {json.dumps(heartbeat)}\n\n"
                
                # specific check to end stream if all files are completed or failed if needed
                # For now, we keep it open until client disconnects or we implement strict closure
        except asyncio.CancelledError:
            # Cleanup if needed
            logger.debug(f"Stream cancelled for batch {batch_id}")

    def get_batch_status(self, batch_id: str) -> Dict:
        """Get current status of a batch (non-streaming)."""
        if batch_id in self._batches:
            return {
                "batch_id": batch_id,
                "files": self._batches[batch_id],
                "timestamp": datetime.utcnow().isoformat()
            }
        return None
