"""data/api：面向 Agent 的稳定数据接口层。

目标：
- 对外暴露更“业务化”的方法名与参数，避免 Agent 直接依赖 Provider/Hub 的内部细节。
- 仍然复用 `DataHub` 的缓存、限频、symbol 解析、错误归一化能力。
"""

from .client import DataAPI

__all__ = [
    "DataAPI",
]
