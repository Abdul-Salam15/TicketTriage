from abc import ABC, abstractmethod
from schemas import TriageResult


class LLMProvider(ABC):
    '''base class for all LLM providers. the rest of the app doesn't care which provider is active — it just calls triage_ticket() and gets back a TriageResult. this makes swapping providers = config change, not code change.'''

    @abstractmethod
    async def triage_ticket(self, subject: str, description: str) -> TriageResult:
        raise NotImplementedError
