"""项目可用模型的最小配置池。"""

from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True, slots=True)
class ModelConfig:
    """描述创建模型客户端所需的稳定配置契约。"""

    model_id: str
    base_url: str
    api_key_env: str


DEFAULT_MODEL = "deepseek-v4-pro"

MODEL_POOL: dict[str, ModelConfig] = {
    DEFAULT_MODEL: ModelConfig(
        model_id="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
    )
}
