from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Literal
from dataclasses import asdict, is_dataclass

@dataclass
class ExchangeSubjects:
    subject_id: str
    subject_uri: str = ""
    subject_metadata: Dict[str, Any] = field(default_factory=dict)
    subject_urls: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "ExchangeSubjects":
        return ExchangeSubjects(
            subject_id=str(data.get("subject_id")),
            subject_uri=data.get("subject_uri", ""),
            subject_metadata=data.get("subject_metadata", {}) or {},
            subject_urls=data.get("subject_urls", {}) or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)