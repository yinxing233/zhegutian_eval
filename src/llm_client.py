"""
统一 LLM 调用客户端（支持多 Provider）
为对仗、语义等评估模块提供轻量级封装。
通过环境变量 EVAL_PROVIDER 切换 Gemini / DeepSeek / GLM 等。
"""

import json
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from openai import OpenAI

load_dotenv()


class BaseEvalClient(ABC):
    """评测客户端抽象基类"""

    def __init__(self, model: Optional[str] = None):
        self.model = model or self.default_model()
        self.temperature = 0.3

    @staticmethod
    @abstractmethod
    def default_model() -> str:
        pass

    @abstractmethod
    def _call_api(self, prompt: str, response_schema: Optional[Dict] = None) -> str:
        """各 Provider 实现具体的 API 调用，返回原始文本"""
        pass

    def ask(self, prompt: str, response_schema: Optional[Dict] = None) -> str:
        """发送 Prompt，返回文本响应"""
        return self._call_api(prompt, response_schema)

    def ask_json(self, prompt: str, retries: int = 3) -> Dict[str, Any]:
        """发送 Prompt 并尝试解析为 JSON，内置重试、清理逻辑、降级重试和降温"""
        last_raw = ""
        current_prompt = prompt
        original_temp = self.temperature
        for attempt in range(retries + 1):
            raw = self.ask(current_prompt)

            if (
                not raw
                or len(raw.strip()) == 0
                or raw.startswith("[Error")
                or raw.startswith("[API Error")
            ):
                print(
                    f"[WARN ask_json] attempt {attempt}, raw: {raw[:200] if raw else 'EMPTY'}"
                )

            # API 层错误：重试
            if raw.startswith("[API Error:") or raw.startswith("[Error"):
                last_raw = raw
                if attempt < retries:
                    time.sleep(2)
                    continue
                return {"error": "API failed after retries", "raw": raw}

            # 空响应：降级重试（缩短 prompt 并降温）
            if not raw or len(raw.strip()) == 0:
                last_raw = raw
                if attempt < retries:
                    time.sleep(2)
                    # 第二次及以后：缩短 prompt + 降温
                    if attempt >= 1:
                        current_prompt = (
                            "请只输出一个 JSON 对象，格式为 "
                            '{"score": <0到1之间的浮点数>, "reason": "<一句话中文理由>"}。'
                            "不要输出任何其他内容。\n\n"
                        ) + prompt[-500:]
                        self.temperature = max(0.0, self.temperature - 0.2)
                    continue
                # 恢复温度
                self.temperature = original_temp
                return {"error": "EMPTY_RESPONSE", "raw": raw}

            # 清理 markdown
            cleaned = raw.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                parts = cleaned.split("\n", 1)
                if len(parts) > 1:
                    cleaned = parts[1]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            try:
                result = json.loads(cleaned)
                result["raw"] = raw
                self.temperature = original_temp  # 成功后恢复
                return result
            except json.JSONDecodeError:
                last_raw = cleaned
                if attempt < retries:
                    time.sleep(2)
                    continue
                self.temperature = original_temp
                return {"error": "JSON_PARSE_FAILED", "raw": raw}

        self.temperature = original_temp
        return {"error": "Max retries exceeded", "raw": last_raw}


# ---------- Gemini 评测客户端 ----------
class GeminiEvalClient(BaseEvalClient):
    @staticmethod
    def default_model() -> str:
        return os.getenv("EVAL_MODEL", "gemini-2.0-flash")

    def __init__(self, model: Optional[str] = None):
        super().__init__(model)
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY 未设置")
        self.client = genai.Client(api_key=api_key)

    def _call_api(self, prompt: str, response_schema: Optional[Dict] = None) -> str:
        config = types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=512,
            response_mime_type="application/json" if response_schema else None,
            response_schema=response_schema if response_schema else None,
        )
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
            return response.text or ""
        except Exception as e:
            return f"[API Error: {str(e)}]"


# ---------- DeepSeek 评测客户端 ----------
class DeepSeekEvalClient(BaseEvalClient):
    @staticmethod
    def default_model() -> str:
        return os.getenv("EVAL_MODEL", "deepseek-chat")

    def __init__(self, model: Optional[str] = None):
        super().__init__(model)
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY 未设置")
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
        )

    def _call_api(self, prompt: str, response_schema: Optional[Dict] = None) -> str:
        system_msg = (
            "你是一个严格的 JSON 输出机。"
            "你必须只输出一个合法的 JSON 对象，不能有任何额外的文字、解释、标记或代码块符号。"
            "如果你无法给出有效评估，也必须输出 JSON："
            '{"score": 0.0, "reason": "无法评估的原因"}'
        )
        full_prompt = prompt
        if response_schema:
            schema_str = json.dumps(response_schema, ensure_ascii=False)
            full_prompt += f"\n\n请严格按照以下 JSON Schema 输出：\n{schema_str}"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": full_prompt},
                ],
                temperature=self.temperature,
                max_tokens=512,
            )
            if response.choices and response.choices[0].message.content is not None:
                return response.choices[0].message.content
            elif response.choices:
                reason = response.choices[0].finish_reason
                return f"[Error: 模型返回空 content，finish_reason={reason}]"
            else:
                return "[Error: API 返回了空的 choices 列表]"
        except Exception as e:
            return f"[API Error: {str(e)}]"


# ---------- GLM 评测客户端 ----------
class GLMEvalClient(BaseEvalClient):
    @staticmethod
    def default_model() -> str:
        return os.getenv("EVAL_MODEL", "glm-4-flash")

    def __init__(self, model: Optional[str] = None):
        super().__init__(model)
        api_key = os.getenv("GLM_API_KEY")
        if not api_key:
            raise ValueError("GLM_API_KEY 未设置")
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://open.bigmodel.cn/api/paas/v4/",
        )

    def _call_api(self, prompt: str, response_schema: Optional[Dict] = None) -> str:
        system_msg = (
            "你是一个严格的 JSON 输出机。"
            "你必须只输出一个合法的 JSON 对象，不能有任何额外的文字、解释、标记或代码块符号。"
            "如果你无法给出有效评估，也必须输出 JSON："
            '{"score": 0.0, "reason": "无法评估的原因"}'
        )
        full_prompt = prompt
        if response_schema:
            schema_str = json.dumps(response_schema, ensure_ascii=False)
            full_prompt += f"\n\n请严格按照以下 JSON Schema 输出：\n{schema_str}"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": full_prompt},
                ],
                temperature=self.temperature,
                max_tokens=512,
            )
            if response.choices and response.choices[0].message.content is not None:
                return response.choices[0].message.content
            elif response.choices:
                reason = response.choices[0].finish_reason
                return f"[Error: 模型返回空 content，finish_reason={reason}]"
            else:
                return "[Error: API 返回了空的 choices 列表]"
        except Exception as e:
            return f"[API Error: {str(e)}]"


# ---------- 工厂入口 ----------
class LLMClient:
    """评测客户端统一入口，根据 EVAL_PROVIDER 返回对应实现"""

    def __new__(cls, model: Optional[str] = None):
        provider = os.getenv("EVAL_PROVIDER", "gemini").lower()
        if provider == "gemini":
            return GeminiEvalClient(model)
        elif provider == "deepseek":
            return DeepSeekEvalClient(model)
        elif provider == "glm":
            return GLMEvalClient(model)
        else:
            raise ValueError(f"不支持的评测 Provider: {provider}")
