"""
FIXED LLM Service for GROQ API with proper multimodal support.
Images sent as vision API format, NOT as base64 text in context.
"""
from groq import Groq, AsyncGroq
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
- If **no context chunks** are provided at all, explicitly state: "No relevant information was found in the selected documents."
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
2. Format: `[Source N, Page X–Y]` — use en-dash, not hyphen.
3. Multiple sources for one claim: `[Source 1, Page 3–4][Source 2, Page 7]`.
4. Never group all citations at the end; they must be inline.
5. Do NOT cite for general knowledge statements (e.g., definitions of basic physics).

## EXAMPLE OUTPUT
"The wellbore pressure was recorded at 3,450 psi during the test period [Source 1, Page 12–13]. \
Casing integrity was confirmed via a pressure build-up analysis [Source 2, Page 7]."
"""

_BASE_MULTIMODAL_SYSTEM = """\
You are a highly accurate document-analysis assistant specializing in petroleum engineering documents.
You can read text, tables, and images (diagrams, charts, photos, schematics).

## LANGUAGE RULE (HIGHEST PRIORITY)
Detect the language of the user's question and **always respond in that exact language**.
- If the question is in Arabic → answer fully in Arabic.
- If the question is in English → answer fully in English.
- Document content or image labels may differ in language; still respond in the question's language.

## SCOPE & RELEVANCE
- Answer ONLY from the provided context (text chunks, tables, and images).
- If the question is completely unrelated to the documents or petroleum engineering, politely decline.
- If context is insufficient, clearly state what is missing — never fabricate.
- If no context is provided, state: "No relevant information was found in the selected documents."

## CONFIDENCE SIGNALS
- Explicit source data → state directly.
- Visual inference from image → prefix with "The image appears to show …".
- Do not present visual interpretations as confirmed facts.

## IMAGE HANDLING
- Examine every provided image carefully before answering.
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
1. Cite every factual claim inline: `[Source N, Page X–Y]`.
2. Image-based claims: `[Image N, Page X]`.
3. Multiple sources: `[Source 1, Page 3–4][Source 2, Page 7]`.
4. Citations must be inline, not grouped at the end.
5. No citation needed for basic definitional statements.

## EXAMPLE OUTPUT
"The separator efficiency reached 94.3% under test conditions [Source 1, Page 5–6]. \
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
    LLM service using GROQ API with Qwen models.
    Supports text generation and multimodal (vision) queries.
    """

    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[AsyncGroq] = None
        self.text_model = self.settings.qwen_text_model
        self.vision_model = self.settings.groq_vision_model

    def initialize(self) -> None:
        """Initialize the GROQ client."""
        if not self.settings.groq_api_key:
            logger.warning("GROQ API key not configured")
            return

        import os
        os.environ["GROQ_API_KEY"] = self.settings.groq_api_key

        self.client = AsyncGroq()
        logger.info(f"Initialized GROQ client (text: {self.text_model}, vision: {self.vision_model})")

    # ----------------------------------------------------------
    # HELPER: build text-only context string from chunks
    # ----------------------------------------------------------
    @staticmethod
    def _build_context(context_chunks: List[RetrievedChunk]) -> str:
        parts = []
        for i, chunk in enumerate(context_chunks, 1):
            image_note = ""
            if hasattr(chunk, "image_ids") and chunk.image_ids:
                image_note = f" [Contains {len(chunk.image_ids)} image(s)]"
            parts.append(
                f"[Source {i} - {chunk.section_title} "
                f"(Pages {chunk.page_start}–{chunk.page_end}){image_note}]\n"
                f"{chunk.content}\n"
            )
        return "\n".join(parts) if parts else "[NO CONTEXT AVAILABLE]"

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
        parts = []

        # Text chunks
        for i, chunk in enumerate(context_chunks, 1):
            image_mention = ""
            if hasattr(chunk, "image_ids") and chunk.image_ids:
                image_mention = f" [Contains {len(chunk.image_ids)} image(s)]"
            parts.append(
                f"[Source {i} - {chunk.section_title} "
                f"(Pages {chunk.page_start}–{chunk.page_end}){image_mention}]\n"
                f"{chunk.content}\n"
            )

        if not parts:
            parts.append("[NO TEXT CONTEXT AVAILABLE]")

        # Tables
        if tables:
            parts.append("\n=== RELEVANT TABLES ===\n")
            for i, table in enumerate(tables, 1):
                if hasattr(table, "markdown_content"):
                    content, page, title = table.markdown_content, table.page_number, table.section_title
                else:
                    content = table.get("markdown", "") or str(table)
                    page = table.get("page_number", "?")
                    title = table.get("section_title", "")
                parts.append(f"[Table {i} – Section: {title} (Page {page})]\n{content}\n")

        # Image analysis summaries
        if retrieved_images:
            parts.append("\n=== RETRIEVED IMAGE ANALYSES ===\n")
            for i, img in enumerate(retrieved_images[:max_retrieved_images], 1):
                analysis = getattr(img, "analysis", "")
                caption = getattr(img, "caption", "") or ""
                title = getattr(img, "section_title", "") or "Unknown section"
                page = getattr(img, "page_number", "?")

                info = [f"Image {i}: {Path(img.image_path).name} (Page {page}, Section: {title})"]
                if caption:
                    info.append(f"Caption: {caption}")
                if analysis:
                    info.append(f"Analysis: {analysis}")
                elif not caption:
                    info.append("Note: No textual analysis available — refer to the visual below.")
                parts.append("\n".join(info) + "\n")

        return "\n".join(parts)

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
                        "image_url": {"url": f"data:image/png;base64,{self._resize_image(img_path)}", "detail": "low"},
                    })
                except Exception as e:
                    logger.warning(f"Could not load retrieved image {img_path}: {e}")

        if user_uploaded_images:
            for img_path in user_uploaded_images[:max_user_images]:
                try:
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{self._resize_image(img_path)}", "detail": "high"},
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
            raise ValueError("GROQ client not initialized. Check API key.")

        context = self._build_context(context_chunks)
        prompt = system_prompt or _BASE_RAG_SYSTEM

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.text_model,
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
            raise ValueError("GROQ client not initialized")

        messages = [
            {"role": "system", "content": system_prompt or _DIRECT_RESPONSE_SYSTEM},
            {"role": "user", "content": query},
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.text_model,
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
        max_retrieved_images: int = 3,
        max_user_images: int = 5,
    ) -> str:
        """Generate response with PROPER multimodal handling."""
        if not self.client:
            raise ValueError("GROQ client not initialized")

        context_text = self._build_multimodal_context(
            context_chunks, tables, retrieved_images, max_retrieved_images
        )

        user_content: list = [{"type": "text", "text": f"Context:\n{context_text}\n\nQuestion: {query}"}]
        self._append_images(user_content, retrieved_images, user_uploaded_images, max_retrieved_images, max_user_images)

        messages = [
            {"role": "system", "content": _BASE_MULTIMODAL_SYSTEM},
            {"role": "user", "content": user_content},
        ]

        if retrieved_images or user_uploaded_images:
            try:
                logger.info(f"Calling vision model: {self.vision_model}")
                response = await self.client.chat.completions.create(
                    model=self.vision_model,
                    messages=messages,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                )
                logger.info("Vision model response generated successfully")
                return response.choices[0].message.content
            except Exception as e:
                logger.warning(f"Vision model failed: {e}. Falling back to text-only.")

        # Fallback: text-only
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

            response = await self.client.chat.completions.create(
                model=self.text_model,
                messages=[
                    {"role": "system", "content": _BASE_RAG_SYSTEM},
                    {"role": "user", "content": f"Context:\n{fallback_context}\n\nNote: Images are referenced in the context but could not be rendered.\n\nQuestion: {query}"},
                ],
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
            "You are an AI assistant that generates very short, concise titles for chat sessions. "
            "Based on the user's first message and the assistant's reply, provide a title of AT MOST 4-5 words. "
            "Never use quotes. Only output the title string itself."
        )

        prompt = (
            f"User: {first_user_message}\n"
            f"Assistant: {first_assistant_reply}\n\n"
            f"Generate a concise title:"
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.text_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=20
            )
            title = response.choices[0].message.content.strip().strip('"').strip("'")
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
            raise ValueError("GROQ client not initialized. Check API key.")

        context = self._build_context(context_chunks)
        prompt = system_prompt or _BASE_RAG_SYSTEM

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ]

        try:
            stream = await self.client.chat.completions.create(
                model=self.text_model,
                messages=messages,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
                stream=True,
            )
            async for chunk in stream:
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
            raise ValueError("GROQ client not initialized")

        messages = [
            {"role": "system", "content": system_prompt or _DIRECT_RESPONSE_SYSTEM},
            {"role": "user", "content": query},
        ]

        try:
            stream = await self.client.chat.completions.create(
                model=self.text_model,
                messages=messages,
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
                stream=True,
            )
            async for chunk in stream:
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
        max_retrieved_images: int = 3,
        max_user_images: int = 5,
    ):
        """Stream a multimodal response token-by-token."""
        if not self.client:
            raise ValueError("GROQ client not initialized")

        context_text = self._build_multimodal_context(
            context_chunks, tables, retrieved_images, max_retrieved_images
        )

        user_content: list = [{"type": "text", "text": f"Context:\n{context_text}\n\nQuestion: {query}"}]
        self._append_images(user_content, retrieved_images, user_uploaded_images, max_retrieved_images, max_user_images)

        messages = [
            {"role": "system", "content": _BASE_MULTIMODAL_SYSTEM},
            {"role": "user", "content": user_content},
        ]

        if retrieved_images or user_uploaded_images:
            try:
                logger.info(f"Streaming vision model: {self.vision_model}")
                stream = await self.client.chat.completions.create(
                    model=self.vision_model,
                    messages=messages,
                    temperature=self.settings.llm_temperature,
                    max_tokens=self.settings.llm_max_tokens,
                    stream=True,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
                return  # Vision succeeded
            except Exception as e:
                logger.warning(f"Vision stream failed: {e}. Falling back to text-only.")

        # Fallback: text-only stream
        try:
            stream = await self.client.chat.completions.create(
                model=self.text_model,
                messages=[
                    {"role": "system", "content": _BASE_RAG_SYSTEM},
                    {"role": "user", "content": (
                        f"Context:\n{context_text}\n\n"
                        "Note: Images are referenced but could not be rendered in this mode.\n\n"
                        f"Question: {query}"
                    )},
                ],
                temperature=self.settings.llm_temperature,
                max_tokens=self.settings.llm_max_tokens,
                stream=True,
            )
            async for chunk in stream:
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
            raise ValueError("GROQ client not initialized")

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
                        "image_url": {"url": f"data:image/png;base64,{image_data}", "detail": "high"},
                    },
                ],
            },
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.vision_model,
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