# src/generator.py
"""
大模型生成层（支持多 Provider）
通过环境变量配置，可切换 Gemini / DeepSeek / OpenAI 等。
"""

import abc
import os
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

# 自动加载 .env 文件
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

    @abc.abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """生成文本，子类必须实现"""
        pass


class GeminiGenerator(BaseGenerator):
    """Google Gemini 生成器（针对诗词评测优化版）"""

    def __init__(
        self,
        api_key: str,
        model_name: str,
        temperature: float,
        max_output_tokens: int,
        top_p: float,
        top_k: Optional[int] = None,
    ):
        super().__init__(model_name, temperature, max_output_tokens, top_p, top_k)

        self.client = genai.Client(api_key=api_key)
        # 记录最后一次生成的 finish_reason，用于 Bad Case 诊断
        self.last_finish_reason = None

        # 放宽安全设置，防止诗词意象被误拦截
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

        # 定义停止序列（Prompt 中要求模型以 [END] 结尾）
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

            # 记录 finish_reason（用于 Bad Case 分析）
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
                return response.text or ""
            except ValueError:
                reason = (
                    str(candidate.finish_reason)
                    if candidate.finish_reason
                    else "Unknown"
                )
                return f"[Error: Candidate blocked by safety. Reason: {reason}]"

        except Exception as e:
            self.last_finish_reason = "EXCEPTION"
            return f"[API Error: {str(e)}]"


def create_generator(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
) -> BaseGenerator:
    """
    创建生成器实例，参数优先级：函数参数 > 环境变量 > 默认值
    只需修改 LLM_PROVIDER 环境变量（gemini / deepseek / openai），代码无需改动。
    """
    provider = provider or os.getenv("LLM_PROVIDER", "gemini")
    temperature = (
        temperature
        if temperature is not None
        else float(os.getenv("GENERATION_TEMPERATURE", "0.9"))
    )
    max_output_tokens = (
        max_output_tokens
        if max_output_tokens is not None
        else int(os.getenv("GENERATION_MAX_OUTPUT_TOKENS", "512"))
    )
    top_p = top_p if top_p is not None else float(os.getenv("GENERATION_TOP_P", "0.95"))
    # top_k 可选，环境变量不设时传 None（Gemini 会使用其默认值）
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

    # 未来扩展 DeepSeek、OpenAI 等
    raise ValueError(f"不支持的 provider: {provider}")
