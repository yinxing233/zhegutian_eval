"""
大语言模型生成层（支持多 Provider）
通过环境变量配置，可切换 Gemini / DeepSeek / GLM。
"""

import abc
import os
from typing import Optional, Tuple

from dotenv import load_dotenv
from google import genai
from google.genai import types
from openai import OpenAI

load_dotenv()


class BaseGenerator(abc.ABC):
    """生成器抽象基类"""

    def __init__(
        self,
        model_name: str,
        temperature: float,
        max_output_tokens: int,
        top_p: float,
        top_k: Optional[int] = None,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.top_p = top_p
        self.top_k = top_k

        self.last_finish_reason = None
        self.last_raw_response = None
        self.last_content_source = None
        self.last_reasoning_content = None

    @abc.abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        pass


# =========================================================
# Gemini
# =========================================================


class GeminiGenerator(BaseGenerator):
    def __init__(
        self,
        api_key,
        model_name,
        temperature,
        max_output_tokens,
        top_p,
        top_k=None,
    ):
        super().__init__(model_name, temperature, max_output_tokens, top_p, top_k)
        self.client = genai.Client(api_key=api_key)
        self.safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                threshold=types.HarmBlockThreshold.BLOCK_NONE,
            ),
        ]
        # 停止序列：仅通过 API 控制，prompt 不再提及 [END]
        self.stop_sequences = ["[END]"]
        self.generation_config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            top_p=top_p,
            top_k=top_k,
            safety_settings=self.safety_settings,
            stop_sequences=self.stop_sequences,
        )

    def generate(self, prompt: str, **kwargs) -> str:
        if kwargs:
            config = types.GenerateContentConfig(
                temperature=kwargs.get("temperature", self.temperature),
                max_output_tokens=kwargs.get(
                    "max_output_tokens", self.max_output_tokens
                ),
                top_p=kwargs.get("top_p", self.top_p),
                top_k=kwargs.get("top_k", self.top_k),
                safety_settings=self.safety_settings,
                stop_sequences=self.stop_sequences,
            )
        else:
            config = self.generation_config

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )
            self.last_raw_response = str(response)
            self.last_content_source = "content"
            self.last_reasoning_content = None

            if response.candidates:
                candidate = response.candidates[0]
                self.last_finish_reason = (
                    str(candidate.finish_reason) if candidate.finish_reason else None
                )
            else:
                self.last_finish_reason = "NO_CANDIDATES"

            if not response.candidates:
                return "[Error: No candidates returned]"

            candidate = response.candidates[0]
            if not candidate.content or not candidate.content.parts:
                reason = (
                    str(candidate.finish_reason)
                    if candidate.finish_reason
                    else "Unknown"
                )
                return f"[Error: No content generated. Reason: {reason}]"

            try:
                text = response.text or ""
                return text
            except ValueError:
                reason = (
                    str(candidate.finish_reason)
                    if candidate.finish_reason
                    else "Unknown"
                )
                return f"[Error: Candidate blocked by safety. Reason: {reason}]"

        except Exception as e:
            self.last_finish_reason = "EXCEPTION"
            self.last_raw_response = str(e)
            return f"[API Error: {str(e)}]"


# =========================================================
# DeepSeek
# =========================================================


class DeepSeekGenerator(BaseGenerator):
    def __init__(
        self,
        api_key,
        model_name,
        temperature,
        max_output_tokens,
        top_p,
        top_k=None,
    ):
        super().__init__(model_name, temperature, max_output_tokens, top_p, top_k)
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
        )

    def _safe_extract_content(self, choice) -> Tuple[str, str]:
        """
        多 schema 容错提取，返回 (text, source)。
        source ∈ {"content", "reasoning_content", "fallback_dict"}
        重要：reasoning_content 只作为观测信号保留，不回退为正文。
        """
        if not choice:
            return "", "empty_choice"

        message = getattr(choice, "message", None)
        if not message:
            return "", "empty_message"

        # ---------- 尝试 1：content ----------
        content = getattr(message, "content", None)
        if content and isinstance(content, str) and content.strip():
            return content.strip(), "content"

        # ---------- 尝试 2：reasoning_content ----------
        reasoning = getattr(message, "reasoning_content", None)
        if reasoning and isinstance(reasoning, str) and reasoning.strip():
            # 记录推理链作为观测信号，但正文返回空
            self.last_reasoning_content = reasoning.strip()
            return "", "reasoning_content"

        # ---------- 尝试 3：dict fallback ----------
        try:
            msg_dict = (
                message.model_dump()
                if hasattr(message, "model_dump")
                else vars(message)
            )
            if isinstance(msg_dict, dict):
                for key in ("content", "reasoning_content", "text", "output"):
                    val = msg_dict.get(key)
                    if val and isinstance(val, str) and val.strip():
                        return val.strip(), f"fallback_dict.{key}"
        except Exception:
            pass

        return "", "exhausted"

    def generate(self, prompt: str, **kwargs) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", self.temperature),
                max_tokens=kwargs.get("max_output_tokens", self.max_output_tokens),
                top_p=kwargs.get("top_p", self.top_p),
                stop=["[END]"],
            )

            # 保存原始响应
            try:
                self.last_raw_response = response.model_dump_json(
                    indent=2, exclude_none=False
                )
            except Exception:
                self.last_raw_response = str(response)

            if not response.choices:
                self.last_finish_reason = "NO_CHOICES"
                self.last_content_source = None
                return "[Error: No choices returned]"

            choice = response.choices[0]
            self.last_finish_reason = (
                str(choice.finish_reason) if choice.finish_reason else None
            )

            text, source = self._safe_extract_content(choice)
            self.last_content_source = source

            # 如果正文为空且是 reasoning_content 导致的，返回空串（观测信号）
            if not text.strip():
                if source == "reasoning_content":
                    return ""
                else:
                    return (
                        "[Error: Empty completion returned by provider. "
                        f"finish_reason={self.last_finish_reason}]"
                    )

            return text.strip()

        except Exception as e:
            self.last_finish_reason = "EXCEPTION"
            self.last_raw_response = str(e)
            self.last_content_source = None
            return f"[API Error: {str(e)}]"


# =========================================================
# GLM
# =========================================================


class GLMGenerator(BaseGenerator):
    def __init__(
        self,
        api_key,
        model_name,
        temperature,
        max_output_tokens,
        top_p,
        top_k=None,
    ):
        super().__init__(model_name, temperature, max_output_tokens, top_p, top_k)
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4/",
        )

    def generate(self, prompt: str, **kwargs) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get(
                    "temperature", self.temperature
                ),  # ← 修复：原为 self.max_output_tokens
                max_tokens=kwargs.get("max_output_tokens", self.max_output_tokens),
                top_p=kwargs.get("top_p", self.top_p),
            )

            try:
                self.last_raw_response = response.model_dump_json(
                    indent=2, exclude_none=False
                )
            except Exception:
                self.last_raw_response = str(response)

            self.last_content_source = "content"
            self.last_reasoning_content = None

            if not response.choices:
                self.last_finish_reason = "NO_CHOICES"
                return "[Error: No choices returned]"

            choice = response.choices[0]
            self.last_finish_reason = (
                str(choice.finish_reason) if choice.finish_reason else None
            )

            content = choice.message.content or ""

            if not content.strip():
                return (
                    "[Error: Empty completion returned by provider. "
                    f"finish_reason={self.last_finish_reason}]"
                )

            return content.strip()

        except Exception as e:
            self.last_finish_reason = "EXCEPTION"
            self.last_raw_response = str(e)
            return f"[API Error: {str(e)}]"


# =========================================================
# Factory
# =========================================================


def create_generator(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
) -> BaseGenerator:

    provider = provider or os.getenv("LLM_PROVIDER", "gemini")

    temperature = (
        temperature
        if temperature is not None
        else float(os.getenv("GENERATION_TEMPERATURE", "0.9"))
    )
    max_output_tokens = (
        max_output_tokens
        if max_output_tokens is not None
        else int(os.getenv("GENERATION_MAX_OUTPUT_TOKENS", "2048"))
    )
    top_p = top_p if top_p is not None else float(os.getenv("GENERATION_TOP_P", "0.95"))

    if top_k is None:
        top_k_val = os.getenv("GENERATION_TOP_K")
        top_k = int(top_k_val) if top_k_val else None

    if provider.lower() == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY 未设置")
        model_name = model or os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        return GeminiGenerator(
            api_key, model_name, temperature, max_output_tokens, top_p, top_k
        )

    elif provider.lower() == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY 未设置")
        model_name = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        return DeepSeekGenerator(
            api_key, model_name, temperature, max_output_tokens, top_p, top_k
        )

    elif provider.lower() == "glm":
        api_key = os.getenv("GLM_API_KEY")
        if not api_key:
            raise ValueError("GLM_API_KEY 未设置")
        model_name = model or os.getenv("GLM_MODEL", "glm-4.5-air")
        return GLMGenerator(
            api_key, model_name, temperature, max_output_tokens, top_p, top_k
        )

    else:
        raise ValueError(f"不支持的 provider: {provider}")
