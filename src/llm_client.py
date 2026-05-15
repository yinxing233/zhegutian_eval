# src/llm_client.py
"""
统一 LLM 调用客户端
为对仗、语义等评估模块提供轻量级 Gemini API 封装。
"""

import json
import os
import time
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


class LLMClient:
    """轻量级 LLM 客户端，用于评测模块（非生成）"""

    def __init__(self, model: Optional[str] = None):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY 未设置")
        self.client = genai.Client(api_key=api_key)
        self.model = model or os.getenv("EVAL_MODEL", "gemini-2.0-flash")
        # 评测用低温度，保证评分稳定
        self.temperature = 0.3

    def ask(self, prompt: str, response_schema: Optional[Dict] = None) -> str:
        """
        发送 Prompt，返回文本响应。
        若提供 response_schema，启用结构化输出（Gemini 支持 JSON mode）。
        """

        config = types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=256,
            response_mime_type="application/json" if response_schema else None,
            response_schema=response_schema if response_schema else None,
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config,
        )
        return response.text or ""

    def ask_json(self, prompt: str, retries: int = 2) -> Dict[str, Any]:
        for attempt in range(retries + 1):
            raw = self.ask(prompt)
            if raw.startswith("[Error") or raw.startswith("[API Error"):
                if attempt < retries:
                    time.sleep(2)
                    continue
                return {"error": "API failed after retries", "raw": raw}
            # 清理代码块
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                parts = cleaned.split("\n", 1)
                if len(parts) > 1:
                    cleaned = parts[1]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                if attempt < retries:
                    continue
                return {"error": "JSON_PARSE_FAILED", "raw": raw}
        return {"error": "Max retries exceeded"}
