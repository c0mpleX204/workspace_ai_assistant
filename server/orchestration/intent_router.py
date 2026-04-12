from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


class IntentType(str, Enum):
	LIGHT_DIALOGUE = "light_dialogue"
	KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
	HEAVY_TASK = "heavy_task"


class RouteTarget(str, Enum):
	LIGHT_CHAT = "light_chat"
	HEAVY_PIPELINE = "heavy_pipeline"


@dataclass(slots=True)
class IntentDecision:
	intent: IntentType
	route: RouteTarget
	reason: str
	confidence: float
	matched_rule: str = ""

	@property
	def is_heavy(self) -> bool:
		return self.route == RouteTarget.HEAVY_PIPELINE


def _clean_text(text: str) -> str:
	return (text or "").strip().lower()


class IntentRouter:
	"""Rule-first intent classifier for low-latency turn routing.

	The router is intentionally deterministic so it can run on every turn
	without extra model overhead.
	"""

	_HEAVY_PATTERNS = (
		r"修改|重构|修复|排查|部署|发布|重启|执行命令|写代码|跑测试",
		r"open|read|inspect|edit|refactor|fix|debug|run|execute|deploy",
	)
	_RETRIEVAL_PATTERNS = (
		r"根据资料|根据文档|检索|检索一下|总结这份|引用来源|课程材料",
		r"search|retrieve|look up|based on docs|cite source",
	)

	def classify(
		self,
		text: str,
		*,
		use_retrieval: bool = False,
		use_web_search: bool = False,
		has_attachments: bool = False,
	) -> IntentDecision:
		cleaned = _clean_text(text)
		if not cleaned:
			return IntentDecision(
				intent=IntentType.LIGHT_DIALOGUE,
				route=RouteTarget.LIGHT_CHAT,
				reason="empty_input",
				confidence=0.99,
			)

		if has_attachments:
			return IntentDecision(
				intent=IntentType.HEAVY_TASK,
				route=RouteTarget.HEAVY_PIPELINE,
				reason="attachments_present",
				confidence=0.92,
				matched_rule="has_attachments",
			)

		if use_retrieval or use_web_search:
			return IntentDecision(
				intent=IntentType.KNOWLEDGE_RETRIEVAL,
				route=RouteTarget.HEAVY_PIPELINE,
				reason="retrieval_or_websearch_requested",
				confidence=0.9,
				matched_rule="explicit_retrieval_flag",
			)

		for pattern in self._HEAVY_PATTERNS:
			if re.search(pattern, cleaned, flags=re.IGNORECASE):
				return IntentDecision(
					intent=IntentType.HEAVY_TASK,
					route=RouteTarget.HEAVY_PIPELINE,
					reason="matched_heavy_rule",
					confidence=0.88,
					matched_rule=pattern,
				)

		for pattern in self._RETRIEVAL_PATTERNS:
			if re.search(pattern, cleaned, flags=re.IGNORECASE):
				return IntentDecision(
					intent=IntentType.KNOWLEDGE_RETRIEVAL,
					route=RouteTarget.HEAVY_PIPELINE,
					reason="matched_retrieval_rule",
					confidence=0.86,
					matched_rule=pattern,
				)

		return IntentDecision(
			intent=IntentType.LIGHT_DIALOGUE,
			route=RouteTarget.LIGHT_CHAT,
			reason="default_light_dialogue",
			confidence=0.72,
		)
