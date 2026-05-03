"""
舆情监控Agent - 从东方财富股吧抓取帖子，分析市场情绪

数据源：东方财富股吧 (guba.eastmoney.com)
输出：标准 Signal 对象，signal_type="news"
"""

import re
from datetime import datetime
from typing import Dict, Any, List

import requests
from loguru import logger

from agents.base import BaseAgent
from agents.signal import Signal, bullish_signal, bearish_signal, neutral_signal
from agents.perception.sentiment import config as cfg


class SentimentAgent(BaseAgent):
    """
    舆情监控Agent

    从东方财富股吧抓取帖子标题，通过关键词匹配分析市场情绪。
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(name="舆情监控Agent", config=config or {})

    def analyze(self, stock_code: str) -> Signal:
        """
        分析指定股票的股吧舆情

        Args:
            stock_code: 股票代码，如 "600519"、"sz300757"

        Returns:
            Signal: 标准化舆情信号
        """
        code = self._normalize_code(stock_code)
        self.log(f"开始分析 {code} 的股吧舆情")

        try:
            posts = self._fetch_guba_posts(code)
        except Exception as e:
            self.log(f"抓取股吧数据失败: {e}", level="error")
            return neutral_signal(
                confidence=0.3,
                reasoning=f"抓取股吧数据失败: {e}",
                source=self.name,
                stock_code=code,
                signal_type="news",
                meta={
                    "output_version": "0.1",
                    "skill_name": "sentiment_monitoring",
                    "owner_group": "专家6组（舆情）",
                    "target": code,
                    "needs_human_review": True,
                    "uncertainties": [f"数据抓取失败: {e}"],
                },
            )

        if not posts:
            self.log(f"未获取到 {code} 的股吧帖子", level="warning")
            return neutral_signal(
                confidence=0.3,
                reasoning=f"未获取到 {code} 的股吧帖子数据",
                source=self.name,
                stock_code=code,
                signal_type="news",
                meta={
                    "output_version": "0.1",
                    "skill_name": "sentiment_monitoring",
                    "owner_group": "专家6组（舆情）",
                    "target": code,
                    "needs_human_review": True,
                    "uncertainties": ["未获取到帖子数据"],
                },
            )

        self.log(f"共获取 {len(posts)} 条帖子")
        analysis = self._analyze_sentiment(posts)
        return self._build_signal(code, analysis)

    def _normalize_code(self, code: str) -> str:
        """标准化股票代码，去除市场前缀"""
        code = code.strip().upper()
        for prefix in ("SH", "SZ", "BJ"):
            if code.startswith(prefix):
                code = code[len(prefix):]
                break
        return code

    def _fetch_guba_posts(self, code: str) -> List[Dict[str, Any]]:
        """从东方财富股吧抓取帖子"""
        posts = []
        seen_ids = set()
        pages = self.config.get("pages", cfg.DEFAULT_PAGES)

        # 第一优先：热门帖子（含阅读数和回复数）
        for page in range(1, pages + 1):
            url = cfg.HOT_POSTS_URL.format(code=code, page=page)
            self.log(f"抓取热门帖子: {url}")
            try:
                page_posts = self._fetch_and_parse_page(url, is_hot=True)
                for post in page_posts:
                    if post["post_id"] not in seen_ids:
                        seen_ids.add(post["post_id"])
                        posts.append(post)
            except Exception as e:
                self.log(f"抓取热门帖子第{page}页失败: {e}", level="warning")

        # 第二优先：最新帖子（补充样本量）
        for page in range(1, pages + 1):
            url = cfg.LATEST_POSTS_URL.format(code=code, page=page)
            self.log(f"抓取最新帖子: {url}")
            try:
                page_posts = self._fetch_and_parse_page(url, is_hot=False)
                for post in page_posts:
                    if post["post_id"] not in seen_ids:
                        seen_ids.add(post["post_id"])
                        posts.append(post)
            except Exception as e:
                self.log(f"抓取最新帖子第{page}页失败: {e}", level="warning")

        return posts

    def _fetch_and_parse_page(
        self, url: str, is_hot: bool
    ) -> List[Dict[str, Any]]:
        """抓取并解析单个页面"""
        resp = requests.get(
            url, headers=cfg.HEADERS, timeout=cfg.REQUEST_TIMEOUT
        )
        resp.raise_for_status()
        html = resp.text

        # 提取帖子信息
        # HTML 结构: postid="..." data-posttype="..." href="...">标题</a>
        title_pattern = re.compile(
            r'postid="(\d+)"\s+data-posttype="\d+"\s+href="([^"]*)">([^<]+)</a>'
        )
        title_matches = title_pattern.findall(html)

        # 提取作者
        author_pattern = re.compile(
            r'class="author"><a\s+href="[^"]*">([^<]+)</a>'
        )
        author_matches = author_pattern.findall(html)

        # 提取阅读数和回复数
        read_pattern = re.compile(r'class="read">(\d+)')
        reply_pattern = re.compile(r'class="reply">(\d+)')
        read_values = [int(v) for v in read_pattern.findall(html)]
        reply_values = [int(v) for v in reply_pattern.findall(html)]

        # 提取帖子发布时间（格式: MM-DD HH:mm）
        time_pattern = re.compile(r'class="update">(\d{2}-\d{2}\s+\d{2}:\d{2})')
        time_values = time_pattern.findall(html)

        posts = []
        for i, (post_id, href, title) in enumerate(title_matches):
            title = title.strip()
            if not title:
                continue

            author = author_matches[i] if i < len(author_matches) else ""
            reads = read_values[i] if i < len(read_values) else 0
            replies = reply_values[i] if i < len(reply_values) else 0
            post_time = time_values[i] if i < len(time_values) else ""

            # 构建完整 URL
            if href.startswith("//"):
                full_url = "https:" + href
            elif href.startswith("/"):
                full_url = cfg.GUBA_BASE_URL + href
            else:
                full_url = href

            posts.append({
                "post_id": post_id,
                "title": title,
                "author": author,
                "reads": reads,
                "replies": replies,
                "post_time": post_time,
                "url": full_url,
                "source_type": "hot" if is_hot else "latest",
            })

        return posts

    def _fetch_post_content(self, url: str) -> str:
        """抓取单条帖子的正文内容，支持 guba 和 caifuhao 两种页面"""
        try:
            resp = requests.get(url, headers=cfg.HEADERS, timeout=cfg.REQUEST_TIMEOUT)
            resp.raise_for_status()
            html = resp.text

            # guba 帖子页: class="newstext ...">
            content_pattern = re.compile(
                r'class="newstext[^"]*">(.*?)</div>', re.DOTALL
            )
            match = content_pattern.search(html)
            if not match:
                # caifuhao 文章页: class="xeditor_content ...">
                content_pattern = re.compile(
                    r'xeditor_content[^>]*>(.*?)</div>', re.DOTALL
                )
                match = content_pattern.search(html)
            if not match:
                return ""

            text = match.group(1)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:500]
        except Exception:
            return ""

    def _analyze_sentiment(self, posts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        基于关键词的情绪分析

        对每条帖子的标题和正文进行看多/看空关键词匹配，加权统计情绪方向。
        热门帖子会抓取正文以提高分析准确度。
        """
        bullish_keywords = set(cfg.BULLISH_KEYWORDS)
        bearish_keywords = set(cfg.BEARISH_KEYWORDS)

        # 对热门帖子抓取正文
        hot_posts = [p for p in posts if p["source_type"] == "hot"]
        for p in hot_posts:
            content = self._fetch_post_content(p["url"])
            if content:
                p["content"] = content
                self.log(f"抓取正文成功: {p['title'][:20]}...")

        weighted_bullish = 0.0
        weighted_bearish = 0.0
        bullish_posts = []
        bearish_posts = []
        neutral_posts = []

        for post in posts:
            # 合并标题和正文进行分析
            text = post["title"]
            if post.get("content"):
                text = text + " " + post["content"]

            # 计算权重
            weight = 1.0
            if post["source_type"] == "hot":
                weight *= cfg.HOT_POST_WEIGHT
            if post["reads"] >= cfg.HIGH_READS_THRESHOLD:
                weight *= cfg.HIGH_READS_WEIGHT
            # 有正文的帖子额外加权
            if post.get("content"):
                weight *= 1.3

            # 关键词匹配
            bull_hits = sum(1 for kw in bullish_keywords if kw in text)
            bear_hits = sum(1 for kw in bearish_keywords if kw in text)

            if bull_hits > bear_hits:
                weighted_bullish += weight
                bullish_posts.append(post)
            elif bear_hits > bull_hits:
                weighted_bearish += weight
                bearish_posts.append(post)
            else:
                neutral_posts.append(post)

        # 计算情绪比例
        total = weighted_bullish + weighted_bearish
        if total == 0:
            bullish_ratio = 0.5
        else:
            bullish_ratio = weighted_bullish / total

        # 判断方向和置信度
        if bullish_ratio > cfg.BULLISH_THRESHOLD:
            direction = "bullish"
            confidence = 0.5 + 0.3 * (bullish_ratio - cfg.BULLISH_THRESHOLD) / (
                1.0 - cfg.BULLISH_THRESHOLD
            )
        elif bullish_ratio < cfg.BEARISH_THRESHOLD:
            direction = "bearish"
            confidence = 0.5 + 0.3 * (cfg.BEARISH_THRESHOLD - bullish_ratio) / cfg.BEARISH_THRESHOLD
        else:
            direction = "neutral"
            confidence = 0.3 + 0.2 * (1.0 - abs(bullish_ratio - 0.5) / 0.1)

        confidence = min(round(confidence, 2), cfg.MAX_CONFIDENCE)

        # 构建信号列表（取 top 帖子标题）
        signals = []
        for p in bullish_posts[:3]:
            signals.append(f"[看多] {p['title'][:40]}")
        for p in bearish_posts[:3]:
            signals.append(f"[看空] {p['title'][:40]}")

        # 构建 reasoning
        content_count = sum(1 for p in posts if p.get("content"))
        reasoning = (
            f"共分析 {len(posts)} 条帖子"
            f"（其中 {content_count} 条含正文），"
            f"看多 {len(bullish_posts)} 条，"
            f"看空 {len(bearish_posts)} 条，"
            f"中性 {len(neutral_posts)} 条。"
            f"看多比例 {bullish_ratio:.1%}，"
            f"情绪方向: {direction}。"
        )

        # 判断风险等级
        if confidence >= 0.7 and direction != "neutral":
            risk_level = "medium"
        else:
            risk_level = "low"

        needs_human_review = (
            confidence < 0.4
            or len(posts) < 5
            or abs(bullish_ratio - 0.5) < 0.05
        )

        # 构建 evidence
        evidence = []
        for p in sorted(
            bullish_posts + bearish_posts, key=lambda x: x["reads"], reverse=True
        )[:5]:
            sentiment = "bullish" if p in bullish_posts else "bearish"
            ev = {
                "title": p["title"],
                "reads": p["reads"],
                "replies": p["replies"],
                "author": p["author"],
                "post_time": p.get("post_time", ""),
                "sentiment": sentiment,
                "source": f"东财股吧·{p['source_type']}",
            }
            if p.get("content"):
                ev["content_summary"] = p["content"][:80] + "..."
            evidence.append(ev)

        # 计算数据时间范围
        time_range = self._calc_time_range(posts)

        return {
            "direction": direction,
            "confidence": confidence,
            "reasoning": reasoning,
            "signals": signals,
            "bullish_ratio": bullish_ratio,
            "risk_level": risk_level,
            "needs_human_review": needs_human_review,
            "total_posts": len(posts),
            "bullish_count": len(bullish_posts),
            "bearish_count": len(bearish_posts),
            "neutral_count": len(neutral_posts),
            "evidence": evidence,
            "time_range": time_range,
        }

    def _build_signal(self, stock_code: str, analysis: Dict[str, Any]) -> Signal:
        """构建标准 Signal 对象"""
        direction = analysis["direction"]
        confidence = analysis["confidence"]
        reasoning = analysis["reasoning"]
        signals = analysis["signals"]

        meta = {
            "output_version": "0.1",
            "skill_name": "sentiment_monitoring",
            "owner_group": "专家6组（舆情）",
            "target": stock_code,
            "period": "实时",
            "data_time_range": analysis.get("time_range", ""),
            "time_horizon": "short",
            "risk_level": analysis["risk_level"],
            "key_findings": [
                f"看多帖子 {analysis['bullish_count']} 条",
                f"看空帖子 {analysis['bearish_count']} 条",
                f"中性帖子 {analysis['neutral_count']} 条",
                f"看多比例 {analysis['bullish_ratio']:.1%}",
            ],
            "evidence": analysis["evidence"],
            "risk_notes": [
                "基于标题+正文的关键词分析，置信度上限0.8",
                "热门帖子已抓取正文，最新帖子仅分析标题",
            ],
            "uncertainties": [
                "部分帖子仅基于标题分析，未抓取正文",
                "无法分析图片/视频内容",
                "关键词匹配可能遗漏隐含情绪",
            ],
            "needs_human_review": analysis["needs_human_review"],
            "total_posts_analyzed": analysis["total_posts"],
            "bullish_count": analysis["bullish_count"],
            "bearish_count": analysis["bearish_count"],
            "neutral_count": analysis["neutral_count"],
        }

        if direction == "bullish":
            return bullish_signal(
                confidence=confidence,
                reasoning=reasoning,
                signals=signals,
                source=self.name,
                stock_code=stock_code,
                signal_type="news",
                meta=meta,
            )
        elif direction == "bearish":
            return bearish_signal(
                confidence=confidence,
                reasoning=reasoning,
                signals=signals,
                source=self.name,
                stock_code=stock_code,
                signal_type="news",
                meta=meta,
            )
        else:
            return neutral_signal(
                confidence=confidence,
                reasoning=reasoning,
                source=self.name,
                stock_code=stock_code,
                signal_type="news",
                meta=meta,
            )

    def _calc_time_range(self, posts: List[Dict[str, Any]]) -> str:
        """根据帖子时间计算数据覆盖的时间范围"""
        now = datetime.now()
        year = now.year
        parsed_times = []
        for p in posts:
            t = p.get("post_time", "").strip()
            if not t:
                continue
            try:
                dt = datetime.strptime(t.strip(), "%m-%d %H:%M")
                dt = dt.replace(year=year)
                # 如果解析出的时间在未来，说明是去年的帖子
                if dt > now:
                    dt = dt.replace(year=year - 1)
                parsed_times.append(dt)
            except ValueError:
                continue

        if not parsed_times:
            return "未知"

        earliest = min(parsed_times)
        latest = max(parsed_times)
        fmt = "%m-%d %H:%M"
        return f"{earliest.strftime(fmt)} ~ {latest.strftime(fmt)}"
