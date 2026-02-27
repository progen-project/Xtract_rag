"""
IMPROVED Chat Controller - Uses unified search and retrieval orchestrator.
Clean separation of concerns.
"""
from typing import List, Optional
from pathlib import Path
import logging
import uuid
import re
from datetime import datetime
from app.config.settings import get_settings
from app.repositories import ChatRepository
from app.schemas import (
    ChatMessage,
    ChatSession,
    ChatResponse,
    ImageSearchResult,
)
from app.utils.exceptions import ChatNotFoundError, ValidationError
from app.services.search_service import UnifiedSearchService
from app.services.retrieval_service import RetrievalOrchestrator

logger = logging.getLogger(__name__)


class ChatController:
    """
    Chat controller with unified search across text, tables, and images.
    Delegates search to UnifiedSearchService and retrieval to RetrievalOrchestrator.
    """
    
    def __init__(
        self,
        chat_repo: ChatRepository,
        indexer,
        llm_service,
        settings,
        document_repo,
        guard=None
    ):
        self.chat_repo = chat_repo
        self.indexer = indexer
        self.llm = llm_service
        self.settings = settings
        self.document_repo = document_repo
        self.guard = guard
        
        # Initialize new services
        self.search_service = UnifiedSearchService(
            indexer=indexer,
            embed_model=indexer.embed_model
        )
        self.retrieval_service = RetrievalOrchestrator(
            document_repo=document_repo
        )
    
    async def _resolve_search_filters(
        self,
        category_ids: Optional[List[str]],
        document_ids: Optional[List[str]],
    ) -> tuple:
        """
        Resolve category/document selection into concrete filter IDs.
        
        4 Cases:
          1. Both null/empty   → general search (no filter)
          2. Categories only   → expand to ALL documents in those categories
          3. Documents only    → filter by those documents
          4. Both provided     → documents win (category is UI context only)
        
        Returns:
            (resolved_category_ids, resolved_document_ids)
        """
        has_categories = bool(category_ids)
        has_documents = bool(document_ids)
        
        # Case 1: No filters → general search across everything
        if not has_categories and not has_documents:
            logger.info("Filter mode: GENERAL — no category/document filter applied")
            return (None, None)
        
        # Case 4: Both provided → documents take priority
        if has_categories and has_documents:
            logger.info(
                f"Filter mode: DOCUMENTS_PRIORITY — "
                f"ignoring {len(category_ids)} categories, "
                f"using {len(document_ids)} explicit documents: {document_ids}"
            )
            return (None, document_ids)
        
        # Case 3: Documents only
        if has_documents:
            logger.info(
                f"Filter mode: DOCUMENTS_ONLY — "
                f"filtering by {len(document_ids)} documents: {document_ids}"
            )
            return (None, document_ids)
        
        # Case 2: Categories only → expand to all documents in those categories
        logger.info(
            f"Filter mode: CATEGORIES_EXPAND — "
            f"expanding {len(category_ids)} categories to their documents"
        )
        all_doc_ids = []
        for cat_id in category_ids:
            docs = await self.document_repo.get_by_category(cat_id)
            cat_doc_ids = [doc.document_id for doc in docs]
            logger.info(f"  Category {cat_id}: {len(cat_doc_ids)} documents")
            all_doc_ids.extend(cat_doc_ids)
        
        if not all_doc_ids:
            logger.warning(
                "CATEGORIES_EXPAND resulted in 0 documents — "
                "falling back to general search"
            )
            return (None, None)
        
        logger.info(
            f"CATEGORIES_EXPAND resolved to {len(all_doc_ids)} documents: {all_doc_ids}"
        )
        return (category_ids, all_doc_ids)
    
    async def send_message(
        self,
        message: str,
        username: str,
        chat_id: Optional[str] = None,
        category_ids: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None,
        image_paths: Optional[List[str]] = None,
        top_k: int = get_settings().top_k
    ) -> ChatResponse:
        """
        Send a message and get a response.
        
        IMPROVED:
        - Uses UnifiedSearchService for automatic search across all collections
        - Uses RetrievalOrchestrator to fetch actual objects by ID
        - Clean separation: search → retrieve → generate
        """
        # Validate
        if image_paths and len(image_paths) > self.settings.max_chat_images:
            raise ValidationError(
                f"Maximum {self.settings.max_chat_images} images allowed"
            )
        
        # Create/get chat session
        is_new_chat = chat_id is None
        if is_new_chat:
            chat_id = f"chat_{uuid.uuid4().hex[:12]}"
            await self.chat_repo.create(
                chat_id=chat_id, 
                username=username, 
                category_ids=category_ids, 
                document_ids=document_ids
            )
        else:
            existing_chat = await self.chat_repo.get_by_id(chat_id, username)
            if not existing_chat:
                raise ChatNotFoundError(chat_id)
            if category_ids is None:
                category_ids = existing_chat.category_ids
            if document_ids is None:
                document_ids = existing_chat.document_ids
        
        # Resolve filter logic (4 cases)
        category_ids, document_ids = await self._resolve_search_filters(
            category_ids, document_ids
        )
        
        # Create user message
        user_message_id = f"msg_{uuid.uuid4().hex[:12]}"
        user_message = ChatMessage(
            message_id=user_message_id,
            role="user",
            content=message,
            image_paths=image_paths or [],
            timestamp=datetime.utcnow()
        )
        
        await self.chat_repo.add_message(chat_id, user_message)
        
        # Get context window
        context_messages = await self.chat_repo.get_recent_messages(
            chat_id,
            limit=self.settings.chat_context_window
        )
        
        # Initialize services
        self.indexer.initialize()
        self.llm.initialize()

        # ========================================
        # STEP 1: GUARD CHECK
        # ========================================
        is_relevant = True
        if self.guard:
            is_relevant = self.guard.check(message)
            logger.info(f"LLM Guard relevance: {is_relevant}")

        if not is_relevant:
            logger.info("Message irrelevant to domain. Using direct path.")
            answer = await self.llm.generate_direct_response(message)
            
            # Create assistant message (no sources/images for irrelevant queries)
            assistant_message_id = f"msg_{uuid.uuid4().hex[:12]}"
            assistant_message = ChatMessage(
                message_id=assistant_message_id,
                role="assistant",
                content=answer,
                image_paths=[],
                sources={},
                timestamp=datetime.utcnow()
            )
            await self.chat_repo.add_message(chat_id, assistant_message)
            
            return ChatResponse(
                chat_id=chat_id,
                username=username,
                message_id=assistant_message_id,
                answer=answer,
                sources={},
                inline_citations=[],
                image_results=[]
            )

        # ========================================
        # STEP 2: UNIFIED SEARCH
        # ========================================
        query_image_data = None
        if image_paths:
            # Load first image for search
            try:
                import base64
                with open(image_paths[0], "rb") as f:
                    query_image_data = base64.b64encode(f.read()).decode()
            except:
                pass
        
        search_results = self.search_service.search(
            query_text=message,
            query_image_data=query_image_data,
            top_k=top_k,
            document_ids=document_ids,
            category_ids=category_ids,
            search_text=True,
            search_tables=True,
            search_images=True
        )
        
        # ========================================
        # STEP 3: ENRICH - Get actual objects
        # ========================================
        enriched = await self.retrieval_service.enrich_search_results(
            search_results
        )
        
        text_chunks = enriched["text_chunks"]
        tables = enriched["tables"]
        images_from_search = enriched["images"]
        
        logger.info(
            f"Enriched: {len(text_chunks)} text, "
            f"{len(tables)} tables, {len(images_from_search)} images"
        )
        
        # ========================================
        # STEP 3: Prepare image paths for LLM
        # ========================================
        all_image_paths = []
        
        # Images from search results
        for img in images_from_search:
            if img.image_path and Path(img.image_path).exists():
                all_image_paths.append(img.image_path)
        
        # Limit to avoid token overflow
        all_image_paths = all_image_paths[:3]
        
        logger.info(f"Prepared {len(all_image_paths)} images for LLM: {all_image_paths}")
        logger.info(f"User uploaded images: {image_paths}")  # Log user images too
        
        # ========================================
        # STEP 4: Build chat history
        # ========================================
        chat_history = self._build_chat_context(context_messages[:-1])
        
        # ========================================
        # STEP 5: Generate response
        # ========================================
        try:
            enhanced_query = (
                f"Previous conversation:\n{chat_history}\n\n"
                f"Current question: {message}"
                if chat_history
                else message
            )
            
            # Convert text_chunks to RetrievedChunk format
            from app.schemas import RetrievedChunk
            
            retrieved_chunks = []
            for result in text_chunks:
                retrieved_chunks.append(
                    RetrievedChunk(
                        chunk_id=result.chunk_id or "",
                        content=result.content,
                        score=result.score,
                        section_title=result.section_title,
                        page_start=result.page_number,
                        page_end=result.page_number,
                        images=[],
                        tables=[]
                    )
                )
            
            answer = await self.llm.generate_multimodal_response(
                query=enhanced_query,
                context_chunks=retrieved_chunks,
                tables=tables,
                retrieved_images=images_from_search,  # Changed: Pass objects
                user_uploaded_images=image_paths,
                max_retrieved_images=3,
                max_user_images=5
            )
            
            logger.info("Response generated successfully")
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            answer = "I apologize, but I couldn't generate a response. Please try again."
        
        # ========================================
        # STEP 6: Build sources metadata
        # ========================================
        sources = await self._build_sources(search_results, category_ids)
        
        # ========================================
        # STEP 6.5: Enrich inline citations
        # ========================================
        answer, inline_citations = self._enrich_inline_citations(
            answer, retrieved_chunks, sources
        )
        
        # Intelligent Source Attachment: Filter sources to only those cited by the LLM
        if inline_citations:
            cited_doc_ids = {c["document_id"] for c in inline_citations}
            sources = {doc_id: data for doc_id, data in sources.items() if doc_id in cited_doc_ids}
            logger.info(f"Filtered sources to {len(sources)} cited documents.")
        else:
            logger.info(f"No inline citations found. Keeping all {len(sources)} sources.")
        
        # ========================================
        # STEP 7: Create assistant message
        # ========================================
        assistant_message_id = f"msg_{uuid.uuid4().hex[:12]}"
        assistant_message = ChatMessage(
            message_id=assistant_message_id,
            role="assistant",
            content=answer,
            image_paths=[img.image_path for img in images_from_search],
            sources=sources,
            timestamp=datetime.utcnow()
        )
        
        await self.chat_repo.add_message(chat_id, assistant_message)
        
        # Build image results
        image_results = [
            ImageSearchResult(
                image_id=img.image_id,
                document_id=img.document_id,
                page_number=img.page_number,
                section_title=img.section_title or "",
                caption=img.caption or "",
                image_path=img.image_path,
                score=0.0  # Score already used in ranking
            )
            for img in images_from_search
        ]
        
        logger.info(f"Responding with {len(image_results)} image results, {len(inline_citations)} inline citations")
        
        # Auto-generate title on first response
        title = None
        if is_new_chat:
            try:
                title_result = await self.name_chat(chat_id, username)
                title = title_result.get("title")
                logger.info(f"Auto-generated chat title: {title}")
            except Exception as e:
                logger.warning(f"Failed to auto-generate chat title: {e}")
        
        return ChatResponse(
            chat_id=chat_id,
            username=username,
            message_id=assistant_message_id,
            answer=answer,
            title=title,
            sources=sources,
            inline_citations=inline_citations,
            image_results=image_results
        )

    async def send_message_stream(
        self,
        message: str,
        username: str,
        chat_id: Optional[str] = None,
        category_ids: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None,
        image_paths: Optional[List[str]] = None,
        top_k: int = get_settings().top_k
    ):
        """
        Streaming version of send_message.
        Yields SSE-formatted strings: 'data: {"token": "..."}\n\n'
        Final event: 'data: {"done": true, "chat_id": "...", ...}\n\n'
        """
        import json as json_mod

        # Validate
        if image_paths and len(image_paths) > self.settings.max_chat_images:
            raise ValidationError(
                f"Maximum {self.settings.max_chat_images} images allowed"
            )

        # Create/get chat session
        is_new_chat = chat_id is None
        if is_new_chat:
            chat_id = f"chat_{uuid.uuid4().hex[:12]}"
            await self.chat_repo.create(
                chat_id=chat_id, 
                username=username, 
                category_ids=category_ids, 
                document_ids=document_ids
            )
        else:
            existing_chat = await self.chat_repo.get_by_id(chat_id, username)
            if not existing_chat:
                raise ChatNotFoundError(chat_id)
            if category_ids is None:
                category_ids = existing_chat.category_ids
            if document_ids is None:
                document_ids = existing_chat.document_ids
        
        # Resolve filter logic (4 cases)
        category_ids, document_ids = await self._resolve_search_filters(
            category_ids, document_ids
        )

        # Create user message
        user_message_id = f"msg_{uuid.uuid4().hex[:12]}"
        user_message = ChatMessage(
            message_id=user_message_id,
            role="user",
            content=message,
            image_paths=image_paths or [],
            timestamp=datetime.utcnow()
        )
        await self.chat_repo.add_message(chat_id, user_message)

        # Get context window
        context_messages = await self.chat_repo.get_recent_messages(
            chat_id, limit=self.settings.chat_context_window
        )

        # Initialize services
        self.indexer.initialize()
        self.llm.initialize()

        # STEP 1: UNIFIED SEARCH (and Guard Check)
        query_image_data = None
        if image_paths:
            try:
                import base64
                with open(image_paths[0], "rb") as f:
                    query_image_data = base64.b64encode(f.read()).decode()
            except:
                pass

        is_relevant = True
        if self.guard:
            is_relevant = self.guard.check(message)
            logger.info(f"LLM Guard relevance (stream): {is_relevant}")

        if not is_relevant:
            logger.info("Message irrelevant to domain (stream). Using direct path.")
            full_answer = ""
            async for token in self.llm.generate_direct_response_stream(message):
                full_answer += token
                yield f"data: {json_mod.dumps({'token': token})}\n\n"
            
            # Save assistant message
            assistant_message_id = f"msg_{uuid.uuid4().hex[:12]}"
            assistant_message = ChatMessage(
                message_id=assistant_message_id,
                role="assistant",
                content=full_answer,
                image_paths=[],
                sources={},
                timestamp=datetime.utcnow()
            )
            await self.chat_repo.add_message(chat_id, assistant_message)
            
            # Auto-generate title on first response
            title = None
            if is_new_chat:
                try:
                    title_result = await self.name_chat(chat_id, username)
                    title = title_result.get("title")
                except Exception as e:
                    logger.warning(f"Failed to auto-generate chat title (stream/direct): {e}")
            
            yield f"data: {json_mod.dumps({'done': True, 'chat_id': chat_id, 'username': username, 'message_id': assistant_message_id, 'answer': full_answer, 'title': title, 'sources': {}, 'inline_citations': [], 'image_results': []})}\n\n"
            return

        search_results = self.search_service.search(
            query_text=message,
            query_image_data=query_image_data,
            top_k=top_k,
            document_ids=document_ids,
            category_ids=category_ids,
            search_text=True,
            search_tables=True,
            search_images=True
        )

        # STEP 2: ENRICH
        enriched = await self.retrieval_service.enrich_search_results(search_results)
        text_chunks = enriched["text_chunks"]
        tables = enriched["tables"]
        images_from_search = enriched["images"]

        # STEP 3: Prepare image paths
        all_image_paths = []
        for img in images_from_search:
            if img.image_path and Path(img.image_path).exists():
                all_image_paths.append(img.image_path)
        all_image_paths = all_image_paths[:3]

        # STEP 4: Build chat history
        chat_history = self._build_chat_context(context_messages[:-1])

        # STEP 5: Build chunks for LLM
        from app.schemas import RetrievedChunk
        enhanced_query = (
            f"Previous conversation:\n{chat_history}\n\n"
            f"Current question: {message}"
            if chat_history else message
        )

        retrieved_chunks = []
        for result in text_chunks:
            retrieved_chunks.append(
                RetrievedChunk(
                    chunk_id=result.chunk_id or "",
                    content=result.content,
                    score=result.score,
                    section_title=result.section_title,
                    page_start=result.page_number,
                    page_end=result.page_number,
                    images=[],
                    tables=[]
                )
            )

        # STEP 6: Stream LLM response
        full_answer = ""
        try:
            async for token in self.llm.generate_multimodal_response_stream(
                query=enhanced_query,
                context_chunks=retrieved_chunks,
                tables=tables,
                retrieved_images=images_from_search if all_image_paths else None,
                user_uploaded_images=image_paths
            ):
                full_answer += token
                yield f"data: {json_mod.dumps({'token': token})}\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"data: {json_mod.dumps({'error': str(e)})}\n\n"
            return

        # STEP 7: Post-process (enrich citations on the full answer)
        sources = await self._build_sources(search_results, category_ids)
        answer, inline_citations = self._enrich_inline_citations(
            full_answer, retrieved_chunks, sources
        )
        
        # Intelligent Source Attachment: Filter sources to only those cited by the LLM
        if inline_citations:
            cited_doc_ids = {c["document_id"] for c in inline_citations}
            sources = {doc_id: data for doc_id, data in sources.items() if doc_id in cited_doc_ids}
            logger.info(f"Filtered sources to {len(sources)} cited documents.")
        else:
            logger.info(f"No inline citations found. Keeping all {len(sources)} sources.")

        # STEP 8: Save assistant message
        assistant_message_id = f"msg_{uuid.uuid4().hex[:12]}"
        assistant_message = ChatMessage(
            message_id=assistant_message_id,
            role="assistant",
            content=answer,
            image_paths=[img.image_path for img in images_from_search],
            sources=sources,
            timestamp=datetime.utcnow()
        )
        await self.chat_repo.add_message(chat_id, assistant_message)

        # Build image results
        image_results = [
            {
                "image_id": img.image_id,
                "document_id": img.document_id,
                "page_number": img.page_number,
                "section_title": img.section_title or "",
                "caption": img.caption or "",
                "image_path": img.image_path,
                "score": 0.0
            }
            for img in images_from_search
        ]

        # Auto-generate title on first response
        title = None
        if is_new_chat:
            try:
                title_result = await self.name_chat(chat_id, username)
                title = title_result.get("title")
                logger.info(f"Auto-generated chat title (stream): {title}")
            except Exception as e:
                logger.warning(f"Failed to auto-generate chat title (stream): {e}")

        # STEP 9: Send final event with metadata
        yield f"data: {json_mod.dumps({'done': True, 'chat_id': chat_id, 'username': username, 'message_id': assistant_message_id, 'answer': answer, 'title': title, 'sources': sources, 'inline_citations': inline_citations, 'image_results': image_results})}\n\n"
    
    def _enrich_inline_citations(
        self,
        answer: str,
        context_chunks,
        sources_map: dict
    ) -> tuple:
        """
        Post-process the LLM answer to replace [Source N, Page X-Y] with
        [filename.pdf, Page X-Y] and build a structured inline_citations list.
        
        Returns:
            (enriched_answer, inline_citations_list)
        """
        inline_citations = []
        
        # Build chunk_index -> (doc_id, filename) mapping
        chunk_doc_map = {}
        for i, chunk in enumerate(context_chunks, 1):
            doc_id = chunk.chunk_id.split("_chunk_")[0] if chunk.chunk_id else ""
            source_info = sources_map.get(doc_id, {})
            filename = source_info.get("filename", "Unknown") if isinstance(source_info, dict) else "Unknown"
            chunk_doc_map[i] = {
                "document_id": doc_id,
                "filename": filename,
                "section_title": chunk.section_title,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
            }
        
        # Build filename -> doc info lookup from sources_map
        filename_doc_map = {}
        for doc_id, source_info in sources_map.items():
            if isinstance(source_info, dict) and source_info.get("filename"):
                filename_doc_map[source_info["filename"]] = {
                    "document_id": doc_id,
                    "filename": source_info["filename"],
                }
        
        def replace_citation(match):
            group1 = match.group(1)  # Could be "Source N" or "filename.pdf"
            page_range = match.group(2)
            
            # Parse page numbers
            pages = []
            for part in re.split(r'[-–]', page_range):
                part = part.strip()
                if part.isdigit():
                    pages.append(int(part))
            
            # Case 1: [Source N, Page X-Y]
            source_match = re.match(r'Source\s+(\d+)', group1)
            if source_match:
                source_num = int(source_match.group(1))
                if source_num in chunk_doc_map:
                    info = chunk_doc_map[source_num]
                    inline_citations.append({
                        "source_number": source_num,
                        "document_id": info["document_id"],
                        "filename": info["filename"],
                        "section_title": info["section_title"],
                        "pages": pages or [info["page_start"], info["page_end"]],
                    })
                    return f'[{info["filename"]}, Page {page_range}]'
                return match.group(0)
            
            # Case 2: [filename.pdf, Page X-Y] — lookup by filename
            filename = group1.strip()
            if filename in filename_doc_map:
                info = filename_doc_map[filename]
                inline_citations.append({
                    "document_id": info["document_id"],
                    "filename": info["filename"],
                    "section_title": "",
                    "pages": pages,
                })
                return match.group(0)  # Keep as-is, already has filename
            
            return match.group(0)
        
        # Match both [Source N, Page X-Y] and [filename.pdf, Page X-Y]
        enriched = re.sub(
            r'\[(.+?\.\w{2,5}),\s*(?:Pages?|p\.?)\s*([\d\-–]+)\]',
            replace_citation,
            answer
        )
        # Also match [Source N, Page X-Y] format
        enriched = re.sub(
            r'\[Source\s+(\d+),\s*(?:Pages?|p\.?)\s*([\d\-–]+)\]',
            replace_citation,
            enriched
        )
        
        logger.info(f"Enriched {len(inline_citations)} inline citations")
        
        return enriched, inline_citations
    
    async def _build_sources(
        self,
        search_results,
        category_ids: Optional[List[str]]
    ) -> dict:
        """
        Build sources dict with metadata.
        
        Returns:
            {
                document_id: {
                    "filename": str,
                    "category_name": str,
                    "pages": [int],
                    "score": float,
                    "contains": ["text", "table", "image"]
                }
            }
        """
        sources_map = {}
        
        for result in search_results:
            doc_id = result.document_id
            
            if doc_id not in sources_map:
                # Get document metadata
                try:
                    doc = await self.document_repo.get_by_id(doc_id)
                    
                    category_name = None
                    if doc and doc.category_id:
                        from app.core.dependencies import container
                        category = await container.category_repo.get_by_id(
                            doc.category_id
                        )
                        category_name = category.name if category else None
                    
                    sources_map[doc_id] = {
                        "document_id": doc_id,
                        "filename": doc.filename if doc else "Unknown",
                        "category_id": doc.category_id if doc else None,
                        "category_name": category_name,
                        "pages": set(),
                        "max_score": 0.0,
                        "source_types": set()
                    }
                except Exception as e:
                    logger.warning(f"Could not get doc metadata for {doc_id}: {e}")
                    sources_map[doc_id] = {
                        "document_id": doc_id,
                        "filename": "Unknown",
                        "category_id": None,
                        "category_name": None,
                        "pages": set(),
                        "max_score": 0.0,
                        "source_types": set()
                    }
            
            # Add page
            sources_map[doc_id]["pages"].add(result.page_number)
            
            # Update max score (use original similarity, not reranker score)
            original_score = getattr(result, 'similarity_score', 0) or result.score
            sources_map[doc_id]["max_score"] = max(
                sources_map[doc_id]["max_score"],
                original_score
            )
            
            # Track source type
            sources_map[doc_id]["source_types"].add(result.source_type)
        
        # Format for response
        formatted_sources = {}
        for doc_id, data in sorted(
            sources_map.items(),
            key=lambda x: x[1]["max_score"],
            reverse=True
        ):
            formatted_sources[doc_id] = {
                "filename": data["filename"],
                "category_id": data["category_id"],
                "category_name": data["category_name"],
                "pages": sorted(list(data["pages"])),
                "score": data["max_score"],
                "contains": list(data["source_types"])
            }
        
        return formatted_sources
    
    async def name_chat(self, chat_id: str, username: str) -> dict:
        """Generate and save a title for a chat based on its first interaction."""
        chat = await self.chat_repo.get_by_id(chat_id, username)
        if not chat:
            from app.core.exceptions import ChatNotFoundError
            raise ChatNotFoundError(chat_id)
            
        if chat.title:
            return {"title": chat.title}
            
        first_user_msg = next((m.content for m in chat.messages if m.role == "user"), None)
        first_ai_msg = next((m.content for m in chat.messages if m.role == "assistant"), None)
        
        if first_user_msg and first_ai_msg:
            title = await self.llm.generate_chat_title(
                first_user_message=first_user_msg,
                first_assistant_reply=first_ai_msg
            )
        elif first_user_msg:
            title = first_user_msg[:30] + "..." if len(first_user_msg) > 30 else first_user_msg
        else:
            title = "New Chat"
            
        success = await self.chat_repo.update_title(chat_id, username, title)
        if not success:
            logger.warning(f"Failed to update title for chat {chat_id}")
            
        return {"title": title}

    def _build_chat_context(self, messages: List[ChatMessage]) -> str:
        """Build context from chat history."""
        context_parts = []
        for msg in messages:
            role = "User" if msg.role == "user" else "Assistant"
            context_parts.append(f"{role}: {msg.content}")
            if msg.image_paths:
                context_parts.append(f"  [Attached {len(msg.image_paths)} image(s)]")
        return "\n".join(context_parts)
    
    async def get_chat(self, chat_id: str, username: str) -> ChatSession:
        """Get a chat session by ID."""
        chat = await self.chat_repo.get_by_id(chat_id, username)
        if not chat:
            raise ChatNotFoundError(chat_id)
        return chat
    
    async def list_chats(self, username: str, limit: int = 50) -> List[ChatSession]:
        """List all chat sessions for a user."""
        return await self.chat_repo.get_all_by_user(username, limit=limit)
    
    async def delete_chat(self, chat_id: str, username: str) -> bool:
        """Delete a chat session and its images."""
        chat = await self.chat_repo.get_by_id(chat_id, username)
        if not chat:
            raise ChatNotFoundError(chat_id)
        
        chat_dir = self.settings.chat_images_dir / chat_id
        if chat_dir.exists():
            import shutil
            shutil.rmtree(chat_dir)
            logger.info(f"Deleted chat images: {chat_dir}")
        
        return await self.chat_repo.delete(chat_id, username)
    
    async def save_uploaded_images(
        self,
        images: list,
        chat_id: str
    ) -> List[str]:
        """Save uploaded images and return paths."""
        saved_paths = []
        chat_dir = self.settings.chat_images_dir / chat_id
        chat_dir.mkdir(parents=True, exist_ok=True)
        
        for img in images:
            if not img.filename:
                continue
            
            ext = Path(img.filename).suffix or ".jpg"
            filename = f"{uuid.uuid4().hex}{ext}"
            file_path = chat_dir / filename
            
            content = await img.read()
            with open(file_path, "wb") as f:
                f.write(content)
            
            saved_paths.append(str(file_path))
            logger.info(f"Saved chat image: {file_path}")
        
        return saved_paths