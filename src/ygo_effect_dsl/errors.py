from dataclasses import dataclass

@dataclass(frozen=True)
class DslError:
    """CORE全体で共通のエラー表現（構造化）"""
    path: str
    code: str
    message: str
    severity: str = "error"  # "error" | "warn"
