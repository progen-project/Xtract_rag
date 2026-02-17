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


class LLMService:
    """
    LLM service using GROQ API with Qwen models.
    Supports text generation and multimodal (vision) queries.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[AsyncGroq] = None
        self.text_model = self.settings.qwen_text_model
        self.vision_model = self.settings.groq_vision_model  # Configured vision model
    
    def initialize(self) -> None:
        """Initialize the GROQ client."""
        if not self.settings.groq_api_key:
            logger.warning("GROQ API key not configured")
            return
        
        import os
        os.environ["GROQ_API_KEY"] = self.settings.groq_api_key
        
        self.client = AsyncGroq()
        logger.info(f"Initialized GROQ client (text: {self.text_model}, vision: {self.vision_model})")
    
    async def generate_response(
        self,
        query: str,
        context_chunks: List[RetrievedChunk],
        system_prompt: Optional[str] = None
    ) -> str:
        """
        Generate a TEXT-ONLY response (no images).
        Use generate_multimodal_response() when images are involved.
        """
        if not self.client:
            raise ValueError("GROQ client not initialized. Check API key.")
        
        # Build context from chunks (TEXT ONLY)
        context_parts = []
        for i, chunk in enumerate(context_chunks, 1):
            # Mention if images exist but DON'T include base64
            image_note = ""
            if hasattr(chunk, 'image_ids') and chunk.image_ids:
                image_note = f" [Contains {len(chunk.image_ids)} image(s)]"
            
            context_parts.append(
                f"[Source {i} - {chunk.section_title} (Pages {chunk.page_start}-{chunk.page_end}){image_note}]\n"
                f"{chunk.content}\n"
            )
        
        context = "\n".join(context_parts)
        
        if system_prompt is None:
            system_prompt = """You are a helpful assistant that answers questions based on the provided context.
Use only the information from the context to answer questions.
If the context doesn't contain relevant information, say so.

CITATION RULES (CRITICAL - YOU MUST FOLLOW THESE EXACTLY):
1. After EVERY claim, fact, or piece of information in your answer, you MUST add an inline citation.
2. Use this EXACT format: [Source N, Page X-Y] where N is the source number and X-Y is the page range.
3. If a sentence combines information from multiple sources, cite all of them: [Source 1, Page 3-4][Source 2, Page 7]
4. NEVER make a factual statement without a citation.
5. If the context doesn't contain relevant information, say so clearly.

Example format:
"The production rate increased by 15% in Q3 [Source 1, Page 5-6], while operational costs decreased due to automation [Source 2, Page 12]."""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user", 
                "content": f"Context:\n{context}\n\nQuestion: {query}"
            }
        ]
        
        try:
            response = await self.client.chat.completions.create(
                model=self.text_model,
                messages=messages,
                temperature=0.7,
                max_tokens=2000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            raise
    
    async def generate_multimodal_response(
        self,
        query: str,
        context_chunks: List[RetrievedChunk],
        tables: Optional[List[Any]] = None,
        retrieved_images: Optional[List[Any]] = None,  # Changed: List of ExtractedImage
        user_uploaded_images: Optional[List[str]] = None,
        max_retrieved_images: int = 3,
        max_user_images: int = 5
    ) -> str:
        """
        Generate response with PROPER multimodal handling.
        
        KEY POINTS:
        - Text context does NOT contain base64
        - Images sent separately as vision API objects
        - User images get priority and high detail
        - Retrieved images use low detail to save tokens
        - INCLUDES image analysis text in context
        
        Args:
            query: User question
            context_chunks: Text chunks (NO BASE64 INSIDE)
            tables: List of table objects to include in context
            retrieved_images: List of ExtractedImage objects (contains analysis)
            user_uploaded_images: User's uploaded query images
            max_retrieved_images: Limit retrieved images (token management)
            max_user_images: Limit user images
            
        Returns:
            Generated response mentioning images when relevant
        """
        if not self.client:
            raise ValueError("GROQ client not initialized")
        
        # ==========================================
        # 1. Build TEXT-ONLY context
        # ==========================================
        context_parts = []
        image_metadata = []  # Track which chunks have images
        
        for i, chunk in enumerate(context_chunks, 1):
            image_mention = ""
            if hasattr(chunk, 'image_ids') and chunk.image_ids:
                image_mention = f" [Contains {len(chunk.image_ids)} image(s)]"
                image_metadata.append({
                    'source_num': i,
                    'section': chunk.section_title,
                    'page_range': f"{chunk.page_start}-{chunk.page_end}",
                    'num_images': len(chunk.image_ids)
                })
            
            context_parts.append(
                f"[Source {i} - {chunk.section_title} "
                f"(Pages {chunk.page_start}-{chunk.page_end})"
                f"{image_mention}]\n{chunk.content}\n"
            )
        
        # Add tables to context
        if tables:
            context_parts.append("\n=== RELEVANT TABLES ===\n")
            for i, table in enumerate(tables, 1):
                # Handle both dicts and objects (ExtractedTable)
                if hasattr(table, 'markdown_content'):
                    content = table.markdown_content
                    page = table.page_number
                    title = table.section_title
                else:
                    content = table.get('markdown', '') or str(table)
                    page = table.get('page_number', '?')
                    title = table.get('section_title', '')
                
                context_parts.append(
                    f"[Table {i} - Section: {title} (Page {page})]\n{content}\n"
                )

        # Add image analysis to context
        if retrieved_images:
            context_parts.append("\n=== RELEVANT IMAGES ANALYSIS ===\n")
            for i, img in enumerate(retrieved_images[:max_retrieved_images], 1):
                # Handle both objects and dicts if necessary, assuming ExtractedImage
                analysis = getattr(img, 'analysis', '')
                caption = getattr(img, 'caption', '') or "No caption"
                title = getattr(img, 'section_title', '') or "No title"
                page = getattr(img, 'page_number', '?')
                
                info_parts = [f"Image {i}: {Path(img.image_path).name} (Page {page}, Section: {title})"]
                if caption:
                    info_parts.append(f"Caption: {caption}")
                if analysis:
                    info_parts.append(f"Analysis: {analysis}")
                elif not caption:
                    info_parts.append("No textual analysis available.")
                    
                context_parts.append("\n".join(info_parts) + "\n")
        
        context_text = "\n".join(context_parts)
        
        # ==========================================
        # 2. Prepare system prompt for multimodal
        # ==========================================
        system_content = """You are a helpful assistant that answers questions based on both text context and images.

CITATION RULES (CRITICAL - YOU MUST FOLLOW THESE EXACTLY):
1. After EVERY claim, fact, or piece of information in your answer, you MUST add an inline citation.
2. Use this EXACT format: [Source N, Page X-Y] where N is the source number and X-Y is the page range.
3. If a sentence combines information from multiple sources, cite all of them: [Source 1, Page 3-4][Source 2, Page 7]
4. NEVER make a factual statement without a citation.
5. When images are provided, examine them carefully and reference them: [Image N, Page X]
6. Describe what you see in images when relevant to the question.
7. Combine information from both text and images for comprehensive answers.

Example format:
"The production rate increased by 15% in Q3 [Source 1, Page 5-6]. The flow diagram shows the updated pipeline layout [Image 1, Page 8]."""
        
        # ==========================================
        # 3. Build user message with text + images
        # ==========================================
        user_content = []
        
        # Add text context first
        user_content.append({
            "type": "text",
            "text": f"Context:\n{context_text}\n\nQuestion: {query}"
        })
        
        # ==========================================
        # 4. Add RETRIEVED images (low detail)
        # ==========================================
        if retrieved_images:
            logger.info(f"Adding {len(retrieved_images)} retrieved images to request")
            
            for idx, img_obj in enumerate(retrieved_images[:max_retrieved_images]):
                img_path = getattr(img_obj, 'image_path', '')
                if not img_path:
                    continue
                try:
                    img_b64 = self._resize_image(img_path)
                    
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_b64}",
                            "detail": "low"  # Save tokens for retrieved images
                        }
                    })
                    logger.debug(f"Added retrieved image {idx+1}: {Path(img_path).name}")
                    
                except Exception as e:
                    logger.warning(f"Could not load retrieved image {img_path}: {e}")
        
        # ==========================================
        # 5. Add USER uploaded images (high detail)
        # ==========================================
        if user_uploaded_images:
            logger.info(f"Adding {len(user_uploaded_images)} user-uploaded images to request")
            
            for idx, img_path in enumerate(user_uploaded_images[:max_user_images]):
                try:
                    img_b64 = self._resize_image(img_path)
                    
                    user_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img_b64}",
                            "detail": "high"  # High detail for user images
                        }
                    })
                    logger.debug(f"Added user image {idx+1}: {Path(img_path).name}")
                    
                except Exception as e:
                    logger.warning(f"Could not load user image {img_path}: {e}")
        
        # ==========================================
        # 6. Build final messages
        # ==========================================
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]
        
        # ==========================================
        # 7. Try VISION model first
        # ==========================================
        if retrieved_images or user_uploaded_images:
            try:
                logger.info(f"Calling vision model: {self.vision_model}")
                
                response = await self.client.chat.completions.create(
                    model=self.vision_model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2000
                )
                
                answer = response.choices[0].message.content
                logger.info("Vision model response generated successfully")
                return answer
                
            except Exception as e:
                logger.warning(f"Vision model failed: {e}")
                logger.info("Falling back to text-only model with image descriptions")
        
        # ==========================================
        # 8. FALLBACK: Text-only with descriptions
        # ==========================================
        try:
            # Build fallback context with image filenames
            fallback_parts = [context_text]
            
            if retrieved_images or user_uploaded_images:
                fallback_parts.append("\n\n=== RELEVANT IMAGES ===")
                
                if retrieved_images:
                    fallback_parts.append("Retrieved from document:")
                    for img in retrieved_images[:max_retrieved_images]:
                        path = getattr(img, 'image_path', 'unknown')
                        fallback_parts.append(f"  • {Path(path).name}")
                
                if user_uploaded_images:
                    fallback_parts.append("\nUser uploaded:")
                    for img_path in user_uploaded_images[:max_user_images]:
                        fallback_parts.append(f"  • {Path(img_path).name}")
            
            fallback_context = "\n".join(fallback_parts)
            
            response = await self.client.chat.completions.create(
                model=self.text_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Answer based on context. Mention that images are referenced but you cannot view them directly."
                    },
                    {
                        "role": "user",
                        "content": f"{fallback_context}\n\nQuestion: {query}"
                    }
                ],
                temperature=0.7,
                max_tokens=2000
            )
            
            answer = response.choices[0].message.content
            logger.info("Fallback text model response generated")
            return answer
            
        except Exception as fallback_error:
            logger.error(f"Fallback also failed: {fallback_error}")
            raise

    # ====================================================
    # STREAMING GENERATORS (for word-by-word SSE output)
    # ====================================================

    async def generate_response_stream(
        self,
        query: str,
        context_chunks: List[RetrievedChunk],
        system_prompt: Optional[str] = None
    ):
        """
        Stream a TEXT-ONLY response token-by-token.
        Yields each content delta string.
        """
        if not self.client:
            raise ValueError("GROQ client not initialized. Check API key.")

        # Build context — same as generate_response
        context_parts = []
        for i, chunk in enumerate(context_chunks, 1):
            image_note = ""
            if hasattr(chunk, 'image_ids') and chunk.image_ids:
                image_note = f" [Contains {len(chunk.image_ids)} image(s)]"
            context_parts.append(
                f"[Source {i} - {chunk.section_title} (Pages {chunk.page_start}-{chunk.page_end}){image_note}]\n"
                f"{chunk.content}\n"
            )
        context = "\n".join(context_parts)

        if system_prompt is None:
            system_prompt = """You are a helpful assistant that answers questions based on the provided context.
Use only the information from the context to answer questions.
If the context doesn't contain relevant information, say so.

CITATION RULES (CRITICAL - YOU MUST FOLLOW THESE EXACTLY):
1. After EVERY claim, fact, or piece of information in your answer, you MUST add an inline citation.
2. Use this EXACT format: [Source N, Page X-Y] where N is the source number and X-Y is the page range.
3. If a sentence combines information from multiple sources, cite all of them: [Source 1, Page 3-4][Source 2, Page 7]
4. NEVER make a factual statement without a citation.
5. If the context doesn't contain relevant information, say so clearly.

Example format:
"The production rate increased by 15% in Q3 [Source 1, Page 5-6], while operational costs decreased due to automation [Source 2, Page 12].\""""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"}
        ]

        try:
            stream = await self.client.chat.completions.create(
                model=self.text_model,
                messages=messages,
                temperature=0.7,
                max_tokens=2000,
                stream=True
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as e:
            logger.error(f"Error streaming response: {e}")
            raise

    async def generate_multimodal_response_stream(
        self,
        query: str,
        context_chunks: List[RetrievedChunk],
        tables: Optional[List[Any]] = None,
        retrieved_images: Optional[List[Any]] = None,
        user_uploaded_images: Optional[List[str]] = None,
        max_retrieved_images: int = 3,
        max_user_images: int = 5
    ):
        """
        Stream a multimodal response token-by-token.
        Yields each content delta string.
        Builds messages the same way as generate_multimodal_response.
        """
        if not self.client:
            raise ValueError("GROQ client not initialized")

        # Build context — same as generate_multimodal_response
        context_parts = []
        for i, chunk in enumerate(context_chunks, 1):
            image_mention = ""
            if hasattr(chunk, 'image_ids') and chunk.image_ids:
                image_mention = f" [Contains {len(chunk.image_ids)} image(s)]"
            context_parts.append(
                f"[Source {i} - {chunk.section_title} "
                f"(Pages {chunk.page_start}-{chunk.page_end})"
                f"{image_mention}]\n{chunk.content}\n"
            )

        if tables:
            context_parts.append("\n=== RELEVANT TABLES ===\n")
            for i, table in enumerate(tables, 1):
                if hasattr(table, 'markdown_content'):
                    content = table.markdown_content
                    page = table.page_number
                    title = table.section_title
                else:
                    content = table.get('markdown', '') or str(table)
                    page = table.get('page_number', '?')
                    title = table.get('section_title', '')
                context_parts.append(f"[Table {i} - Section: {title} (Page {page})]\n{content}\n")

        if retrieved_images:
            context_parts.append("\n=== RELEVANT IMAGES ANALYSIS ===\n")
            for i, img in enumerate(retrieved_images[:max_retrieved_images], 1):
                analysis = getattr(img, 'analysis', '')
                caption = getattr(img, 'caption', '') or "No caption"
                title = getattr(img, 'section_title', '') or "No title"
                page = getattr(img, 'page_number', '?')
                info_parts = [f"Image {i}: {Path(img.image_path).name} (Page {page}, Section: {title})"]
                if caption:
                    info_parts.append(f"Caption: {caption}")
                if analysis:
                    info_parts.append(f"Analysis: {analysis}")
                context_parts.append("\n".join(info_parts) + "\n")

        context_text = "\n".join(context_parts)

        system_content = """You are a helpful assistant that answers questions based on both text context and images.

CITATION RULES (CRITICAL - YOU MUST FOLLOW THESE EXACTLY):
1. After EVERY claim, fact, or piece of information in your answer, you MUST add an inline citation.
2. Use this EXACT format: [Source N, Page X-Y] where N is the source number and X-Y is the page range.
3. If a sentence combines information from multiple sources, cite all of them: [Source 1, Page 3-4][Source 2, Page 7]
4. NEVER make a factual statement without a citation.
5. When images are provided, examine them carefully and reference them: [Image N, Page X]
6. Describe what you see in images when relevant to the question.
7. Combine information from both text and images for comprehensive answers.

Example format:
"The production rate increased by 15% in Q3 [Source 1, Page 5-6]. The flow diagram shows the updated pipeline layout [Image 1, Page 8].\""""

        user_content = [{"type": "text", "text": f"Context:\n{context_text}\n\nQuestion: {query}"}]

        # Add retrieved images
        if retrieved_images:
            for img_obj in retrieved_images[:max_retrieved_images]:
                img_path = getattr(img_obj, 'image_path', '')
                if not img_path:
                    continue
                try:
                    img_b64 = self._resize_image(img_path)
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "low"}
                    })
                except Exception as e:
                    logger.warning(f"Could not load retrieved image {img_path}: {e}")

        # Add user uploaded images
        if user_uploaded_images:
            for img_path in user_uploaded_images[:max_user_images]:
                try:
                    img_b64 = self._resize_image(img_path)
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "high"}
                    })
                except Exception as e:
                    logger.warning(f"Could not load user image {img_path}: {e}")

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]

        # Try vision model first
        if retrieved_images or user_uploaded_images:
            try:
                logger.info(f"Streaming vision model: {self.vision_model}")
                stream = await self.client.chat.completions.create(
                    model=self.vision_model,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2000,
                    stream=True
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        yield delta.content
                return  # Vision model succeeded
            except Exception as e:
                logger.warning(f"Vision stream failed: {e}, falling back to text-only")

        # Fallback: text-only stream
        try:
            stream = await self.client.chat.completions.create(
                model=self.text_model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion: {query}"}
                ],
                temperature=0.7,
                max_tokens=2000,
                stream=True
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
        except Exception as e:
            logger.error(f"Fallback stream also failed: {e}")
            raise
    
    def _resize_image(self, image_path: str) -> str:
        """
        Load and resize image if needed, return base64 string.
        """
        try:
            from PIL import Image
            import io
            
            with Image.open(image_path) as img:
                # Convert to RGB if needed
                if img.mode in ('RGBA', 'P'):
                    img = img.convert('RGB')
                
                # Resize if too large
                max_width = self.settings.max_image_width
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                    logger.debug(f"Resized image {Path(image_path).name} to {max_width}x{new_height}")
                
                # Save to buffer
                buf = io.BytesIO()
                img.save(buf, format="png", quality=85)
                return base64.b64encode(buf.getvalue()).decode()
                
        except Exception as e:
            logger.warning(f"Error resizing image {image_path}: {e}")
            # Fallback to original
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode()

    async def analyze_image(
        self,
        image: ExtractedImage,
        query: Optional[str] = None,
        context_text: Optional[str] = None
    ) -> str:
        """
        Analyze a single image using vision model.
        
        Args:
            image: ExtractedImage object with path
            query: Optional specific question about the image
            context_text: Optional surrounding text from document
            
        Returns:
            Image analysis/description
        """
        if not self.client:
            raise ValueError("GROQ client not initialized")
        
        if not Path(image.image_path).exists():
            return f"Image not available: {image.image_path}"
        
        # Load and resize image
        image_data = self._resize_image(image.image_path)
        
        # Build prompt
        context_part = ""
        if context_text:
            context_part = f"Context from document regarding this image:\n{context_text}\n\n"
            
        if query:
            prompt = f"{context_part}Analyze this image and answer: {query}"
        else:
            prompt = (
                f"{context_part}Describe this image in detail, including any text, charts, diagrams, or figures present. "
                "Use the provided context to improve accuracy if relevant, but prioritize visual observations."
            )
        
        # Prepare messages
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_data}",
                            "detail": "high"
                        }
                    }
                ]
            }
        ]
        
        try:
            response = await self.client.chat.completions.create(
                model=self.vision_model,
                messages=messages,
                temperature=0.5,
                max_tokens=1000
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.warning(f"Vision analysis failed: {e}")
            if image.caption:
                return f"Image caption: {image.caption}"
            return f"Image on page {image.page_number} ({image.width}x{image.height} {image.image_format})"


# Global LLM service instance
llm_service = LLMService()


def get_llm_service() -> LLMService:
    """Dependency for getting LLM service."""
    return llm_service