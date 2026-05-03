"""
舆情监控Agent配置
"""

GUBA_BASE_URL = "https://guba.eastmoney.com"

# URL 模板
HOT_POSTS_URL = GUBA_BASE_URL + "/list,{code},99_{page}.html"
LATEST_POSTS_URL = GUBA_BASE_URL + "/list,{code}_{page}.html"

# 抓取配置
DEFAULT_PAGES = 2
REQUEST_TIMEOUT = 10

# 请求头
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://guba.eastmoney.com/",
}

# 情绪分析关键词
BULLISH_KEYWORDS = [
    "利好", "大涨", "牛", "突破", "加仓", "看好", "买入",
    "反弹", "低估", "抄底", "龙头", "强势", "放量", "涨停",
    "新高", "主力", "加码", "上涨", "翻倍", "暴涨", "启动",
    "涨", "增持", "回购", "绩优", "白马", "价值", "分红",
    "业绩超预期", "订单", "扩产", "供不应求", "景气",
]

BEARISH_KEYWORDS = [
    "利空", "大跌", "熊", "破位", "减仓", "看空", "卖出",
    "暴跌", "高估", "泡沫", "跌停", "破发", "减持", "暴雷",
    "做空", "恐慌", "下跌", "腰斩", "崩盘", "套牢", "割肉",
    "跌", "亏损", "退市", "风险", "违规", "处罚", "造假",
    "暴亏", "资金链", "违约", "ST", "退",
]

# 热门帖子权重倍数
HOT_POST_WEIGHT = 1.5
# 高阅读量阈值
HIGH_READS_THRESHOLD = 1000
HIGH_READS_WEIGHT = 1.2

# 置信度配置
MAX_CONFIDENCE = 0.8
BULLISH_THRESHOLD = 0.6
BEARISH_THRESHOLD = 0.4
