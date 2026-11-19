"""Judge model client (layer 2). Calls Claude through the official Anthropic SDK; local models
keep using LLMClient (docs/tasarim.md, Puanlama)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
import yaml
from pydantic import BaseModel


@dataclass(frozen=True)
class JudgeSettings:
    model: str
    effort: str
    max_tokens: int
    rubric_version: str
    concurrency: int
    api_key_env: str
    cache_dir: str

    @classmethod
    def load(cls, config_dir: str | Path = "config") -> JudgeSettings:
        raw = yaml.safe_load((Path(config_dir) / "judge.yaml").read_text(encoding="utf-8"))
        return cls(**raw)


class JudgeUnavailable(RuntimeError):
    pass


@dataclass
class JudgeReply:
    parsed: BaseModel | None
    stop_reason: str | None
    usage: dict[str, Any]


class JudgeClient:
    def __init__(self, settings: JudgeSettings, client: anthropic.AsyncAnthropic | None = None):
        self.settings = settings
        if client is None:
            if not os.environ.get(settings.api_key_env):
                raise JudgeUnavailable(
                    f"{settings.api_key_env} tanımlı değil: hakem Claude API anahtarı ister"
                )
            client = anthropic.AsyncAnthropic(api_key=os.environ[settings.api_key_env])
        self.client = client

    async def judge(self, system: str, user: str, output: type[BaseModel]) -> JudgeReply:
        msg = await self.client.messages.parse(
            model=self.settings.model,
            max_tokens=self.settings.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.settings.effort},
            output_format=output,
        )
        usage = msg.usage.to_dict() if msg.usage else {}
        # A refusal is recorded as unscored; falling back to another model would change the judge.
        parsed = msg.parsed_output if msg.stop_reason != "refusal" else None
        return JudgeReply(parsed=parsed, stop_reason=msg.stop_reason, usage=usage)

    async def aclose(self) -> None:
        await self.client.close()
