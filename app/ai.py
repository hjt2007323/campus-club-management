import logging
import os
from pathlib import Path

import httpx

from .schemas import Plan

logger = logging.getLogger(__name__)
PROMPT = (Path(__file__).parent / "prompts" / "activity.txt").read_text(encoding="utf-8-sig")


class PlanningError(Exception):
    pass


def generate_plan(description: str) -> Plan:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise PlanningError(503, "未配置 DeepSeek API 密钥")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
    try:
        response = httpx.post(
            "https://api.deepseek.com/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model,
                "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"},
                "max_tokens": 1200,
                "messages": [
                    {"role": "system", "content": PROMPT},
                    {"role": "user", "content": description},
                ],
            },
            timeout=25,
        )
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise PlanningError(504, "DeepSeek 请求超时，请稍后重试") from exc
    except httpx.HTTPError as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else "network"
        logger.warning("DeepSeek failure status=%s", status)
        raise PlanningError(502, "DeepSeek 请求失败，请检查服务配置或稍后重试") from exc

    try:
        result = response.json()
        plan = Plan.model_validate_json(result["choices"][0]["message"]["content"])
    except (ValueError, IndexError, KeyError, TypeError) as exc:
        raise PlanningError(502, "DeepSeek 返回的草案格式无效") from exc

    logger.info("DeepSeek validated model=%s response_id=%s usage=%s",
                result.get("model"), result.get("id"), result.get("usage"))
    return plan
