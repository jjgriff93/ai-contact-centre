
import yaml
from dataclasses import dataclass
from typing import Any, Optional, List, Dict


@dataclass
class EvaluationModels:
    chat_deployment: Optional[str] = None
    stt_deployment: Optional[str] = None
    tts_deployment: Optional[str] = None
    voice: Optional[str] = None


@dataclass
class Thresholds:
    vad_silence_duration: float = 1.0   # seconds
    turn_timeout: float = 30.0          # seconds


@dataclass
class EvalConfig:
    max_turns: int = 8
    exit_terms: Optional[List[str]] = None
    thresholds: Thresholds = Thresholds()


@dataclass
class PathsConfig:
    testcases_dir: str = "testcases"
    eval_dataset_file: str = "eval_dataset.json"


@dataclass
class LoggingConfig:
    level: str = "INFO"


@dataclass
class AppConfig:
    evaluation_models: EvaluationModels = EvaluationModels()
    evaluation: EvalConfig = EvalConfig()
    paths: PathsConfig = PathsConfig()
    logging: LoggingConfig = LoggingConfig()


def load_config(path: str) -> AppConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw: Dict[str, Any] = yaml.safe_load(f) or {}

    raw.setdefault("evaluation_models", {})
    raw.setdefault("evaluation", {})
    raw.setdefault("paths", {})
    raw.setdefault("logging", {})

    eval_raw = raw["evaluation"]
    eval_raw.setdefault("thresholds", {})

    return AppConfig(
        evaluation_models=EvaluationModels(**raw["evaluation_models"]),
        evaluation=EvalConfig(
            max_turns=eval_raw.get("max_turns", 8),
            exit_terms=eval_raw.get("exit_terms"),
            thresholds=Thresholds(**eval_raw.get("thresholds", {})),
        ),
        paths=PathsConfig(**raw["paths"]),
        logging=LoggingConfig(**raw["logging"]),
    )