"""Claude Sonnet 4.7 streaming agent with tool-use loop."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import AsyncIterator, Optional

from anthropic import AsyncAnthropic, APIError, APIStatusError

from .prompts import system_for
from .tools import TOOL_SCHEMAS, dispatch

logger = logging.getLogger("brain.claude")


class ClaudeAgent:
    def __init__(self, sess, app_state, config: dict) -> None:
        self.sess = sess
        self.app_state = app_state
        self.config = config
        self.client = AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        self.primary = config.get("primary_model", "claude-sonnet-4-7")
        self.fallback = config.get("fallback_model", "claude-sonnet-4-6")
        self.max_tokens = int(config.get("max_tokens", 2000))
        self.max_iters = int(config.get("max_tool_iterations", 5))
        self.keep_turns = int(config.get("history_keep_turns", 30))

    def _trim_history(self) -> None:
        if len(self.sess.history) > self.keep_turns * 2:
            # keep newest keep_turns*2 messages, drop the rest
            self.sess.history = self.sess.history[-self.keep_turns * 2 :]

    async def translate_only(self, text: str, src: str, dst: str) -> str:
        """F2: single-turn translation - no tools, no history, no streaming."""
        system = (
            f"You are a professional interpreter. Translate the following text from {src} to {dst}.\n"
            "Respond with ONLY the translation, no preamble, no explanation, no quotes."
        )
        user_msg = f"Text: {text}"
        for attempt in (self.primary, self.fallback):
            try:
                resp = await self.client.messages.create(
                    model=attempt,
                    max_tokens=min(self.max_tokens, 500),
                    system=system,
                    messages=[{"role": "user", "content": user_msg}],
                )
                out = ""
                for block in getattr(resp, "content", []) or []:
                    if getattr(block, "type", None) == "text":
                        out += getattr(block, "text", "") or ""
                return out.strip()
            except Exception:
                logger.exception("translate_only failed on %s", attempt)
                continue
        return ""

    async def respond(self, user_text: str, lang: str = "de") -> AsyncIterator[str]:
        """Run one agent turn → yield text chunks (already spoken-ready)."""
        self.sess.history.append({"role": "user", "content": user_text})
        self._trim_history()

        contacts = None
        try:
            contacts = self.app_state.contacts.all()
        except Exception:
            contacts = None
        system = system_for(
            self.sess.mode.value,
            self.sess.is_owner,
            lang=lang,
            contacts=contacts,
        )
        if self.sess.mode.value == "interpreter":
            # interpreter stays in simple mode; still supports tools for control commands
            pass

        model = self.primary
        for iteration in range(self.max_iters):
            try:
                async for text in self._stream_one(model, system):
                    if text:
                        yield text
                # _stream_one may populate history with tool_use; if the last assistant
                # message had stop_reason == tool_use we loop; else break.
                last = self.sess.history[-1] if self.sess.history else None
                if last and last.get("_stop_reason") == "tool_use":
                    continue
                break
            except APIStatusError as exc:
                logger.warning('"claude primary failed (%s), trying fallback"', exc.status_code)
                if model == self.primary:
                    model = self.fallback
                    continue
                yield "Ich habe ein technisches Problem. Bitte noch einmal."
                break
            except Exception:
                logger.exception('"claude streaming failed"')
                yield "Entschuldigung, ich hatte eine Störung."
                break

    async def _stream_one(self, model: str, system: str) -> AsyncIterator[str]:
        """One HTTP-streaming Claude turn. If the model decides to use a tool, run
        the tool, append the tool-result message, and signal the outer loop to
        continue by tagging the last assistant message with _stop_reason=tool_use."""
        api_messages = [
            {"role": m["role"], "content": m["content"]} for m in self.sess.history
            if m["role"] in ("user", "assistant")
        ]

        assistant_blocks: list[dict] = []
        text_accum = ""
        current_tool: Optional[dict] = None
        stop_reason: Optional[str] = None

        async with self.client.messages.stream(
            model=model,
            max_tokens=self.max_tokens,
            system=system,
            tools=TOOL_SCHEMAS,
            messages=api_messages,
        ) as stream:
            async for event in stream:
                t = getattr(event, "type", None)
                if t == "content_block_start":
                    blk = event.content_block
                    if blk.type == "tool_use":
                        current_tool = {
                            "type": "tool_use",
                            "id": blk.id,
                            "name": blk.name,
                            "input_json": "",
                        }
                elif t == "content_block_delta":
                    d = event.delta
                    if d.type == "text_delta":
                        text_accum += d.text
                        yield d.text
                    elif d.type == "input_json_delta" and current_tool:
                        current_tool["input_json"] += d.partial_json
                elif t == "content_block_stop":
                    if current_tool:
                        try:
                            current_tool["input"] = json.loads(current_tool.pop("input_json") or "{}")
                        except Exception:
                            current_tool["input"] = {}
                        assistant_blocks.append(
                            {
                                "type": "tool_use",
                                "id": current_tool["id"],
                                "name": current_tool["name"],
                                "input": current_tool["input"],
                            }
                        )
                        current_tool = None
                elif t == "message_stop":
                    stop_reason = getattr(event.message, "stop_reason", None)

        if text_accum.strip():
            assistant_blocks.insert(0, {"type": "text", "text": text_accum})

        # Record assistant message in history
        assistant_msg = {
            "role": "assistant",
            "content": assistant_blocks,
            "_stop_reason": stop_reason,
        }
        self.sess.history.append(assistant_msg)

        # If tool-use, run tools + append tool_result
        tool_uses = [b for b in assistant_blocks if b.get("type") == "tool_use"]
        if stop_reason == "tool_use" and tool_uses:
            tool_results: list[dict] = []
            for tu in tool_uses:
                result = await dispatch(
                    tu["name"], tu.get("input", {}), sess=self.sess, app_state=self.app_state
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tu["id"],
                        "content": json.dumps(result),
                    }
                )
                logger.info(
                    json.dumps(
                        {"event": "tool_result", "pair_id": self.sess.pair_id, "tool": tu["name"], "ok": result.get("ok")}
                    )
                )
            self.sess.history.append({"role": "user", "content": tool_results})
