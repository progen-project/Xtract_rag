"""
LLM Service using an OpenAI-compatible provider (DeepInfra by default).
Images sent as vision API format, NOT as base64 text in context.
Uses the OpenAI SDK pointed at the configured LLM_BASE_URL.
"""
from openai import AsyncOpenAI
from typing import List, Optional, Dict, Any
import logging
import base64
from pathlib import Path

from app.config.settings import get_settings
from app.schemas import Chunk, ExtractedImage, RetrievedChunk

logger = logging.getLogger(__name__)


# ============================================================
# CENTRALISED PROMPT TEMPLATES
# All prompt changes live here — no hunting across methods.
# ============================================================

_BASE_RAG_SYSTEM = """\
You are a highly accurate document-analysis assistant specializing in petroleum engineering documents.

## THINKING (MANDATORY)
Before writing your final answer, reason step-by-step inside a <think>…</think> block.
In that block: identify which context chunks are relevant, note key data points, plan the answer structure.
After </think>, write only the polished answer — the user will only see content AFTER the think block.

## CONTEXT FORMAT (JSON)
The provided context is a structured JSON array containing text chunks, tables, and image descriptions.
Each element contains a `source_file`, `page`, `section_title`, and the core `content`.
When citing, you must strictly use the `source_file` and `page` attributes from the specific JSON object where you found the information.

## LANGUAGE RULE (HIGHEST PRIORITY)
Detect the language of the user's question and **always respond in that exact language**.
- If the question is in Arabic → answer fully in Arabic.
- If the question is in English → answer fully in English.
- If the question mixes languages → match the dominant language.
- Document content may differ in language from the question; that is fine — translate relevant findings into the answer language.

## SCOPE & RELEVANCE
- Answer ONLY from the provided context chunks.
- If the question is **completely unrelated** to petroleum engineering or the document content (e.g., cooking, sports, general trivia), politely decline and explain that you are scoped to document-based petroleum engineering queries.
- If the context exists but does **not contain enough information** to answer confidently, clearly say so and indicate which aspect is missing — do NOT fabricate data.
- If **no context chunks** are provided at all (empty JSON array), explicitly state: "No relevant information was found in the selected documents."
- If the question is **ambiguous**, address the most likely intended interpretation and note the assumption made.

## CONFIDENCE SIGNALS
- When information is explicit in the source: state it directly.
- When you are inferring or the source is indirect: prefix with "Based on the available context, …" or "This appears to suggest …".
- Never present inferences as confirmed facts.

## FORMATTING RULES
- Start with a **1–2 sentence executive summary**.
- Use `##` headers to separate major sections (avoid excessive sub-headers).
- Use **bold** for key terms, values, and critical findings.
- Use bullet points (`-`) for lists of 3+ unordered items.
- Use numbered lists for sequential steps or ranked items.
- Use markdown tables for comparative or structured data.
- Keep paragraphs ≤ 3 sentences.
- Avoid filler phrases like "Certainly!", "Great question!", or "As an AI…".

## CITATION RULES (MANDATORY)
1. Cite EVERY factual claim inline immediately after the claim.
2. Use the **exact document filename** provided in the `source_file` key of the JSON object, NOT a generic "Source N".
3. Format: `[filename.pdf, Page X–Y]` — use en-dash for page ranges.
4. Multiple sources for one claim: `[report.pdf, Page 3–4][manual.pdf, Page 7]`.
5. Never group all citations at the end; they must be inline.
6. Do NOT cite for general knowledge statements (e.g., definitions of basic physics).

## EXAMPLE OUTPUT
"The wellbore pressure was recorded at 3,450 psi during the test period [Well_Test_Report.pdf, Page 12–13]. \
Casing integrity was confirmed via a pressure build-up analysis [Completion_Manual.pdf, Page 7]."
"""

_BASE_MULTIMODAL_SYSTEM = """\
You are a highly accurate document-analysis assistant specializing in petroleum engineering documents.
You can read text, tables, and images (diagrams, charts, photos, schematics).

## THINKING (MANDATORY)
Before writing your final answer, reason step-by-step inside a <think>…</think> block.
In that block: identify relevant chunks, images, and tables; note key data; plan the answer.
After </think>, write only the polished answer.

## CONTEXT FORMAT (JSON)
The provided context is a structured JSON array containing text chunks, tables, and image descriptions.
Each element contains a `source_file`, `page`, `section_title`, and the core `content` (or `analysis` for images).
When citing, you must strictly use the `source_file` and `page` attributes from the specific JSON object where you found the information.

## LANGUAGE RULE (HIGHEST PRIORITY)
Detect the language of the user's question and **always respond in that exact language**.
- If the question is in Arabic → answer fully in Arabic.
- If the question is in English → answer fully in English.
- Document content or image labels may differ in language; still respond in the question's language.

## SCOPE & RELEVANCE
- Answer ONLY from the provided JSON context (text chunks, tables, and images).
- If the question is completely unrelated to the documents or petroleum engineering, politely decline.
- If context is insufficient, clearly state what is missing — never fabricate.
- If no context is provided, state: "No relevant information was found in the selected documents."

## CONFIDENCE SIGNALS
- Explicit source data → state directly.
- Visual inference from image → prefix with "The image appears to show …".
- Do not present visual interpretations as confirmed facts.

## IMAGE HANDLING
- Examine every provided image object in the JSON carefully before answering.
- Reference images with `[Image N, Page X]` immediately after any image-based claim.
- If an image is unclear or irrelevant to the question, note that briefly and continue.
- Combine textual and visual evidence for the most complete answer.

## FORMATTING RULES
- 1–2 sentence executive summary first.
- `##` headers for major sections; **bold** for key values.
- Bullet points for unordered lists; numbered lists for sequences.
- Markdown tables for structured/comparative data.
- Paragraphs ≤ 3 sentences. No filler phrases.

## CITATION RULES (MANDATORY)
1. Cite every factual claim inline using the **exact document filename** from the `source_file` key.
2. Format: `[filename.pdf, Page X–Y]` — use en-dash for page ranges.
3. Image-based claims: `[Image N, Page X]`.
4. Multiple sources: `[report.pdf, Page 3–4][manual.pdf, Page 7]`.
5. Citations must be inline, not grouped at the end.
6. No citation needed for basic definitional statements.

## EXAMPLE OUTPUT
"The separator efficiency reached 94.3% under test conditions [Production_Report.pdf, Page 5–6]. \
The P&ID diagram confirms the bypass valve location upstream of the separator [Image 2, Page 8]."
"""

_DIRECT_RESPONSE_SYSTEM = """\
You are a senior Petroleum Engineer with 20+ years of experience across upstream, midstream, and downstream operations.

## LANGUAGE RULE (HIGHEST PRIORITY)
Always respond in the **same language as the user's question**.
- Arabic question → Arabic answer.
- English question → English answer.

## SCOPE
- You answer general petroleum engineering questions from your expertise.
- If a question is completely unrelated to petroleum engineering (e.g., cooking, sports), politely clarify your scope.
- If a question was expected to be answered from specific documents but none were provided or matched, clearly say: \
  "I could not find this in the selected documents, but based on general petroleum engineering knowledge: …"

## FORMATTING RULES
- Use `##` headers, **bold** for key terms, and bullet points where appropriate.
- Keep answers technically precise and concise.
- No filler phrases.
"""

_IMAGE_ANALYSIS_SYSTEM = """\
You are a technical image analyst specializing in petroleum engineering diagrams, charts, schematics, and figures.

## TASK
Carefully examine the provided image and produce a structured technical description.

## LANGUAGE RULE
If a specific question is asked, respond in the language of that question.
Otherwise, respond in English by default.

## OUTPUT STRUCTURE
1. **Image Type**: (e.g., P&ID, well log, production chart, geological cross-section, equipment photo)
2. **Key Visual Elements**: List all significant components, labels, axes, legends, or annotations visible.
3. **Data / Values**: Extract any numeric values, units, dates, or thresholds shown.
4. **Technical Interpretation**: What does this image communicate in the context of petroleum engineering?
5. **Limitations**: Note anything unclear, cut off, low-resolution, or ambiguous.

## RULES
- Prioritize what is explicitly visible; do not invent details.
- Use context text (if provided) to clarify ambiguous elements, but label inferences clearly.
- Be concise but thorough — downstream RAG will use this analysis for retrieval.
"""


class LLMService:
    """
    LLM service using an OpenAI-compatible API (DeepInfra by default).
    Supports text generation and multimodal (vision) queries.
    """

    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[AsyncOpenAI] = None
        self.model = self.settings.llm_model

    def initialize(self) -> None:
        """Initialize the LLM client via OpenAI SDK."""
        if not self.settings.llm_api_key:
            logger.warning("LLM API key not configured (LLM_API_KEY)")
            return

        self.client = AsyncOpenAI(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
        )
        logger.info(f"Initialized LLM client (model: {self.model}, base_url: {self.settings.llm_base_url})")

    # ----------------------------------------------------------
    # HELPER: build text-only context string from chunks
    # ----------------------------------------------------------
    @staticmethod
    def _build_context(context_chunks: List[RetrievedChunk]) -> str:
        """Builds a JSON string representing the textual context."""
        import json
        
        if not context_chunks:
            return json.dumps({"context": []})
            
        context_data = []
        for i, chunk in enumerate(context_chunks, 1):
            image_note = ""
            if hasattr(chunk, "image_ids") and chunk.image_ids:
                image_note = f" [Contains {len(chunk.image_ids)} image(s)]"
                
            context_data.append({
                "type": "text",
                "source_file": chunk.doc_filename or f"Source {i}",
                "section_title": chunk.section_title or "",
                "pages": f"{chunk.page_start}–{chunk.page_end}",
                "content": chunk.content,
                "note": image_note.strip() if image_note else None
            })
            
        return json.dumps({"context": context_data}, ensure_ascii=False, indent=2)

    # ----------------------------------------------------------
    # HELPER: build multimodal context (text + tables + images meta)
    # ----------------------------------------------------------
    @staticmethod
    def _build_multimodal_context(
        context_chunks: List[RetrievedChunk],
        tables: Optional[List[Any]],
        retrieved_images: Optional[List[Any]],
        max_retrieved_images: int,
    ) -> str:
        """Builds a JSON string representing the multimodal context."""
        import json
        
        context_data = {
            "context": [],
            "tables": [],
            "images": []
        }

        # Text chunks
        for i, chunk in enumerate(context_chunks, 1):
            image_note = ""
            if hasattr(chunk, "image_ids") and chunk.image_ids:
                image_note = f" [Contains {len(chunk.image_ids)} image(s)]"
                
            context_data["context"].append({
                "type": "text",
                "source_file": chunk.doc_filename or f"Source {i}",
                "section_title": chunk.section_title or "",
                "pages": f"{chunk.page_start}–{chunk.page_end}",
                "content": chunk.content,
                "note": image_note.strip() if image_note else None
            })

        # Tables
        if tables:
            for i, table in enumerate(tables, 1):
                if hasattr(table, "markdown_content"):
                    content = table.markdown_content
                    page = table.page_number
                    title = table.section_title
                    doc_filename = getattr(table, "doc_filename", f"Table {i}")
                else:
                    content = table.get("markdown", "") or str(table)
                    page = table.get("page_number", "?")
                    title = table.get("section_title", "")
                    doc_filename = table.get("doc_filename", f"Table {i}")
                    
                context_data["tables"].append({
                    "source_file": doc_filename,
                    "section_title": title,
                    "page": page,
                    "content": content
                })

        # Image analysis summaries
        if retrieved_images:
            for i, img in enumerate(retrieved_images[:max_retrieved_images], 1):
                analysis = getattr(img, "analysis", "")
                caption = getattr(img, "caption", "") or ""
                title = getattr(img, "section_title", "") or "Unknown section"
                page = getattr(img, "page_number", "?")
                doc_filename = getattr(img, "doc_filename", Path(getattr(img, "image_path", "")).name)

                img_data = {
                    "source_file": doc_filename,
                    "section_title": title,
                    "page": page,
                    "image_name": Path(getattr(img, "image_path", f"Image_{i}")).name
                }
                
                if caption:
                    img_data["caption"] = caption
                if analysis:
                    img_data["analysis"] = analysis
                elif not caption:
                    img_data["note"] = "No textual analysis available — refer to the visual below."
                    
                context_data["images"].append(img_data)

        return json.dumps(context_data, ensure_ascii=False, indent=2)

    # ----------------------------------------------------------
    # HELPER: Log exact LLM requests and inputs
    # ----------------------------------------------------------
    def _log_llm_request(self, messages: List[Dict[str, Any]]) -> None:
        """Write the exact LLM input payload to a dedicated log file."""
        import json
        import os
        from datetime import datetime
        
        log_dir = self.settings.log_dir if hasattr(self.settings, 'log_dir') else "./logs"
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "llm_inputs.log")
        
        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*50}\n")
                f.write(f"TIMESTAMP: {datetime.utcnow().isoformat()}\n")
                f.write(f"MODEL: {self.model}\n")
                f.write(f"{'-'*50}\n")
                
                # We do a deepcopy or manual extraction to avoid dumping giant base64 image strings into the log
                log_messages = []
                for msg in messages:
                    if isinstance(msg.get("content"), list):
                        # This is a multimodal message
                        safe_content = []
                        for part in msg["content"]:
                            if part.get("type") == "text":
                                safe_content.append(part)
                            elif part.get("type") == "image_url":
                                url_data = part.get("image_url", {}).get("url", "")
                                if url_data.startswith("data:image"):
                                    safe_content.append({"type": "image_url", "image_url": {"url": "<BASE64_IMAGE_DATA>"}})
                                else:
                                    safe_content.append(part)
                        log_messages.append({"role": msg.get("role"), "content": safe_content})
                    else:
                        # Standard text message
                        log_messages.append({"role": msg.get("role"), "content": msg.get("content")})
                
                f.write(json.dumps(log_messages, indent=2, ensure_ascii=False))
                f.write(f"\n{'='*50}\n")
        except Exception as e:
            logger.error(f"Failed to log LLM request: {e}")

    # ----------------------------------------------------------
    # HELPER: append image blobs to user_content list
    # ----------------------------------------------------------
    def _append_images(
        self,
        user_content: list,
        retrieved_images: Optional[List[Any]],
        user_uploaded_images: Optional[List[str]],
        max_retrieved_images: int,
        max_user_images: int,
    ) -> None:
        if retrieved_images:
            for img_obj in retrieved_images[:max_retrieved_images]:
                img_path = getattr(img_obj, "image_path", "")
                if not img_path:
                    continue
                try:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{self._resize_image(img_path)}"},
                    })
                except Exception as e:
                    logger.warning(f"Could not load retrieved image {img_path}: {e}")

        if user_uploaded_images:
            for img_path in user_uploaded_images[:max_user_images]:
                try:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{self._resize_image(img_path)}"},
                    })
                except Exception as e:
                    logger.warning(f"Could not load user image {img_path}: {e}")

    # ==========================================================
    # PUBLIC METHODS
    # ==========================================================

    async def generate_response(
        self,
        query: str,
        context_chunks: List[RetrievedChunk],
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate a TEXT-ONLY response (no images)."""
        if not self.client:
            raise ValueError("LLM client not initialized. Check LLM_API_KEY.")

        context = self._build_context(context_chunks)
        prompt = system_prompt or _BASE_RAG_SYSTEM

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ]

        # --- Logging the exact input sent to LLM ---
        self._log_llm_request(messages)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise

    async def generate_direct_response(
        self,
        query: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """Generate a direct response without RAG context."""
        if not self.client:
            raise ValueError("LLM client not initialized")

        messages = [
            {"role": "system", "content": system_prompt or _DIRECT_RESPONSE_SYSTEM},
            {"role": "user", "content": query},
        ]

        # --- Logging the exact input sent to LLM ---
        self._log_llm_request(messages)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error in direct generation: {e}")
            raise

    async def generate_multimodal_response(
        self,
        query: str,
        context_chunks: List[RetrievedChunk],
        tables: Optional[List[Any]] = None,
        retrieved_images: Optional[List[Any]] = None,
        user_uploaded_images: Optional[List[str]] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
        max_retrieved_images: int = 3,
        max_user_images: int = 5,
    ) -> str:
        """Generate response with PROPER multimodal handling and structured chat history."""
        if not self.client:
            raise ValueError("LLM client not initialized")

        context_text = self._build_multimodal_context(
            context_chunks, tables, retrieved_images, max_retrieved_images
        )

        # Build text content with labeled sections
        text_parts = [f"Context:\n{context_text}"]
        if user_uploaded_images:
            text_parts.append(f"\nThe user has also uploaded {len(user_uploaded_images)} image(s) for analysis (shown below).")
        text_parts.append(f"\nQuestion: {query}")

        user_content: list = [{"type": "text", "text": "\n".join(text_parts)}]
        self._append_images(user_content, retrieved_images, user_uploaded_images, max_retrieved_images, max_user_images)

        # Build messages with proper chat history
        messages = [{"role": "system", "content": _BASE_MULTIMODAL_SYSTEM}]
        if chat_history:
            for msg in chat_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_content})

        # --- Logging the exact input sent to LLM ---
        self._log_llm_request(messages)

        if retrieved_images or user_uploaded_images:
            try:
                logger.info(f"Calling model with vision input: {self.model}")
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                )
                logger.info("Multimodal response generated successfully")
                return response.choices[0].message.content
            except Exception as e:
                logger.warning(f"Multimodal call failed: {e}. Falling back to text-only.")

        # Fallback: text-only (rebuild messages without image blobs)
        try:
            fallback_parts = [context_text]
            if retrieved_images or user_uploaded_images:
                fallback_parts.append("\n\n=== IMAGES (not renderable in fallback mode) ===")
                if retrieved_images:
                    fallback_parts.append("Document images referenced:")
                    for img in retrieved_images[:max_retrieved_images]:
                        path = getattr(img, "image_path", "unknown")
                        fallback_parts.append(f"  • {Path(path).name}")
                if user_uploaded_images:
                    fallback_parts.append("User-uploaded images:")
                    for img_path in user_uploaded_images[:max_user_images]:
                        fallback_parts.append(f"  • {Path(img_path).name}")
            fallback_context = "\n".join(fallback_parts)

            fallback_messages = [{"role": "system", "content": _BASE_RAG_SYSTEM}]
            if chat_history:
                for msg in chat_history:
                    fallback_messages.append({"role": msg["role"], "content": msg["content"]})
            fallback_messages.append({
                "role": "user",
                "content": f"Context:\n{fallback_context}\n\nNote: Images are referenced in the context but could not be rendered.\n\nQuestion: {query}"
            })

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=fallback_messages,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
            )
            return response.choices[0].message.content
        except Exception as fallback_error:
            logger.error(f"Fallback also failed: {fallback_error}")
            raise

    # ==========================================================
    # STREAMING METHODS
    # ==========================================================

    async def generate_chat_title(
        self,
        first_user_message: str,
        first_assistant_reply: str
    ) -> str:
        """Generate a short 4-5 word title based on the first interaction."""
        if not self.client:
            return "New Chat"

        system_prompt = (
            "You are an AI assistant specialized in summarizing conversations into highly concise titles. "
            "Your task is to provide a 3 to 5 word title for the chat based on the user's first message to you. "
            "RULES:\n"
            "- Output ONLY the title itself.\n"
            "- NO quotes, NO punctuation at the end, NO introduction.\n"
            "- Ignore the `<think>` process, just output the final title.\n"
            "- Do not explain your reasoning."
        )
        assistant_reply = ""
        if first_assistant_reply:
            assistant_reply = f"\nAssistant: {first_assistant_reply}"
        prompt = (
            f"User: {first_user_message}\n"
            f"Assistant: {assistant_reply}\n"
            f"Generate a concise 3-5 word title for this topic:"
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=512
            )
            raw_title = response.choices[0].message.content
            
            # Remove any <think>...</think> blocks from reasoning models
            import re
            cleaned_title = re.sub(r'<think>.*?(?:</think>|$)', '', raw_title, flags=re.DOTALL)
            
            title = cleaned_title.strip().strip('"').strip("'").strip()
            # If the model still outputs something like "Title: ...", strip it
            if title.lower().startswith("title:"):
                title = title[6:].strip()
                
            return title if title else "New Chat"
        except Exception as e:
            logger.error(f"Error generating chat title: {str(e)}")
            return "New Chat"


    async def generate_response_stream(
        self,
        query: str,
        context_chunks: List[RetrievedChunk],
        system_prompt: Optional[str] = None,
    ):
        """Stream a TEXT-ONLY response token-by-token."""
        if not self.client:
            raise ValueError("LLM client not initialized. Check LLM_API_KEY.")

        context = self._build_context(context_chunks)
        prompt = system_prompt or _BASE_RAG_SYSTEM

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ]

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
        except Exception as e:
            logger.error(f"Error streaming response: {e}")
            raise

    async def generate_direct_response_stream(
        self,
        query: str,
        system_prompt: Optional[str] = None,
    ):
        """Stream a direct response without RAG context."""
        if not self.client:
            raise ValueError("LLM client not initialized")

        messages = [
            {"role": "system", "content": system_prompt or _DIRECT_RESPONSE_SYSTEM},
            {"role": "user", "content": query},
        ]

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
        except Exception as e:
            logger.error(f"Error in direct streaming: {e}")
            raise

    async def generate_multimodal_response_stream(
        self,
        query: str,
        context_chunks: List[RetrievedChunk],
        tables: Optional[List[Any]] = None,
        retrieved_images: Optional[List[Any]] = None,
        user_uploaded_images: Optional[List[str]] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
        max_retrieved_images: int = 3,
        max_user_images: int = 5,
    ):
        """Stream a multimodal response token-by-token with structured chat history."""
        if not self.client:
            raise ValueError("LLM client not initialized")

        context_text = self._build_multimodal_context(
            context_chunks, tables, retrieved_images, max_retrieved_images
        )

        # Build text content with labeled sections
        text_parts = [f"Context:\n{context_text}"]
        if user_uploaded_images:
            text_parts.append(f"\nThe user has also uploaded {len(user_uploaded_images)} image(s) for analysis (shown below).")
        text_parts.append(f"\nQuestion: {query}")

        user_content: list = [{"type": "text", "text": "\n".join(text_parts)}]
        self._append_images(user_content, retrieved_images, user_uploaded_images, max_retrieved_images, max_user_images)

        # Build messages with proper chat history
        messages = [{"role": "system", "content": _BASE_MULTIMODAL_SYSTEM}]
        if chat_history:
            for msg in chat_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_content})

        # --- Logging the exact input sent to LLM ---
        self._log_llm_request(messages)

        if retrieved_images or user_uploaded_images:
            try:
                logger.info(f"Streaming multimodal response: {self.model}")
                stream = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                    stream=True,
                )
                async for chunk in stream:
                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        if delta.content:
                            yield delta.content
                return  # Vision succeeded
            except Exception as e:
                logger.warning(f"Multimodal stream failed: {e}. Falling back to text-only.")

        # Fallback: text-only stream (rebuild messages without image blobs)
        try:
            fallback_messages = [{"role": "system", "content": _BASE_RAG_SYSTEM}]
            if chat_history:
                for msg in chat_history:
                    fallback_messages.append({"role": msg["role"], "content": msg["content"]})
            fallback_messages.append({
                "role": "user",
                "content": (
                    f"Context:\n{context_text}\n\n"
                    "Note: Images are referenced but could not be rendered in this mode.\n\n"
                    f"Question: {query}"
                )
            })

            # --- Logging the exact input sent to LLM ---
            self._log_llm_request(fallback_messages)

            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=fallback_messages,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
        except Exception as e:
            logger.error(f"Fallback stream also failed: {e}")
            raise

    # ==========================================================
    # IMAGE UTILITIES
    # ==========================================================

    def _resize_image(self, image_path: str) -> str:
        """Load and resize image if needed, return base64 string."""
        try:
            from PIL import Image
            import io

            with Image.open(image_path) as img:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                max_width = self.settings.max_image_width
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                    logger.debug(f"Resized {Path(image_path).name} → {max_width}×{new_height}")

                buf = io.BytesIO()
                img.save(buf, format="png", quality=85)
                return base64.b64encode(buf.getvalue()).decode()

        except Exception as e:
            logger.warning(f"Error resizing image {image_path}: {e}")
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode()

    async def analyze_image(
        self,
        image: ExtractedImage,
        query: Optional[str] = None,
        context_text: Optional[str] = None,
    ) -> str:
        """Analyze a single image using vision model."""
        if not self.client:
            raise ValueError("LLM client not initialized")

        if not Path(image.image_path).exists():
            return f"Image not available: {image.image_path}"

        image_data = self._resize_image(image.image_path)

        context_part = f"Context from surrounding document text:\n{context_text}\n\n" if context_text else ""

        if query:
            # Targeted question: respond in question's language
            prompt = (
                f"{context_part}"
                f"Using the image and any provided context, answer this specific question:\n{query}\n\n"
                "If the image does not contain enough information, state that clearly."
            )
        else:
            # Generic analysis: use structured system prompt
            prompt = (
                f"{context_part}"
                "Produce a structured technical analysis of this image following your system instructions."
            )

        messages = [
            {"role": "system", "content": _IMAGE_ANALYSIS_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_data}"},
                    },
                ],
            },
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"Vision analysis failed: {e}")
            if image.caption:
                return f"Image caption: {image.caption}"
            return f"Image on page {image.page_number} ({image.width}×{image.height} {image.image_format})"


# Global LLM service instance
llm_service = LLMService()


def get_llm_service() -> LLMService:
    """Dependency for getting LLM service."""
    return llm_service