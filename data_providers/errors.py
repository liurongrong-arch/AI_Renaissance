class DataError(Exception):
    """数据层通用异常基类。"""


class MissingDependencyError(DataError):
    """缺少可选依赖（例如 akshare 未安装）。"""


class ProviderError(DataError):
    """数据源 Provider 调用失败。"""


class DatasetNotSupportedError(DataError):
    """Provider 不支持该数据集类型。"""


class DataNotFoundError(DataError):
    """数据不存在或为空。"""
