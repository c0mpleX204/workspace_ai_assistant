from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from orchestration.intent_router import IntentDecision, IntentRouter, RouteTarget


class RouteMode(str, Enum):
	AUTO = "auto"
	CHAT_ONLY = "chat_only"
	FORCE_HEAVY = "force_heavy"


@dataclass(slots=True)
class TurnContext:
	user_text: str
	route_mode: RouteMode = RouteMode.AUTO
	use_retrieval: bool = False
	use_web_search: bool = False
	has_attachments: bool = False


@dataclass(slots=True)
class TurnDecision:
	route: RouteTarget
	intent: str
	reason: str
	confidence: float
	matched_rule: str = ""

	@property
	def go_light(self) -> bool:
		return self.route == RouteTarget.LIGHT_CHAT


class DecisionEngine:
	"""High-level route resolver for chat entrypoints.

	Current version uses deterministic rule-based routing and exposes a clean
	contract for future LLM fallback.
	"""

	def __init__(self, intent_router: IntentRouter | None = None) -> None:
		self._intent_router = intent_router or IntentRouter()

	def decide(self, context: TurnContext) -> TurnDecision:
		if context.route_mode == RouteMode.CHAT_ONLY:
			return TurnDecision(
				route=RouteTarget.LIGHT_CHAT,
				intent="forced_light_dialogue",
				reason="route_mode_chat_only",
				confidence=1.0,
				matched_rule="route_mode",
			)

		if context.route_mode == RouteMode.FORCE_HEAVY:
			return TurnDecision(
				route=RouteTarget.HEAVY_PIPELINE,
				intent="forced_heavy_task",
				reason="route_mode_force_heavy",
				confidence=1.0,
				matched_rule="route_mode",
			)

		intent: IntentDecision = self._intent_router.classify(
			context.user_text,
			use_retrieval=context.use_retrieval,
			use_web_search=context.use_web_search,
			has_attachments=context.has_attachments,
		)
		return TurnDecision(
			route=intent.route,
			intent=intent.intent.value,
			reason=intent.reason,
			confidence=intent.confidence,
			matched_rule=intent.matched_rule,
		)
