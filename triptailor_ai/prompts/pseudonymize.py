"""Participant pseudonymisation for prompts.

Display names never reach a model provider.  Participant ids are replaced with
``P1``/``P2``/... as well, so that neither a hosted API nor a prompt log can be
joined back to the backend's user records.
"""

from __future__ import annotations

from triptailor_ai.schemas.preference import NormalizedPreference
from triptailor_ai.schemas.trip import TripPlanningRequest


class Pseudonymizer:
    """Bidirectional ``participantId <-> P{n}`` mapping."""

    def __init__(self, participant_ids: list[str], *, enabled: bool = True) -> None:
        self.enabled = enabled
        self._to_alias: dict[str, str] = {}
        self._to_real: dict[str, str] = {}
        for index, participant_id in enumerate(participant_ids, start=1):
            alias = f"P{index}" if enabled else participant_id
            self._to_alias[participant_id] = alias
            self._to_real[alias] = participant_id

    @classmethod
    def for_request(
        cls, request: TripPlanningRequest, *, enabled: bool = True
    ) -> "Pseudonymizer":
        return cls([p.participant_id for p in request.participants], enabled=enabled)

    @property
    def aliases(self) -> list[str]:
        return list(self._to_real)

    def alias(self, participant_id: str) -> str:
        return self._to_alias.get(participant_id, participant_id)

    def real(self, alias: str) -> str | None:
        """Real id for ``alias``; ``None`` when the model invented one."""

        return self._to_real.get(alias)

    def restore(self, preferences: list[NormalizedPreference]) -> list[NormalizedPreference]:
        """Map aliases back to real ids, dropping preferences we cannot place.

        A preference attributed to a participant who does not exist is a
        hallucination and is discarded rather than guessed at.
        """

        restored: list[NormalizedPreference] = []
        for preference in preferences:
            real_id = self.real(preference.participant_id)
            if real_id is None:
                if preference.participant_id in self._to_alias:
                    real_id = preference.participant_id  # already a real id
                else:
                    continue
            restored.append(preference.model_copy(update={"participant_id": real_id}))
        return restored

    def restore_id_list(self, ids: list[str]) -> list[str]:
        resolved = [self.real(i) or (i if i in self._to_alias else None) for i in ids]
        return [i for i in resolved if i]
