"""
IMA 笔记搜索 Demo — 按标题 / 按正文搜索
使用方法：
  export IMA_CLIENT_ID="你的ClientID"
  export IMA_API_KEY="你的APIKey"
  python3 search_notes_demo.py
"""

import os
import json
import sys
from datetime import datetime

import requests

# 优先从环境变量读取，如果没有则使用硬编码的值（仅用于测试）
# 容
# CLIENT_ID = os.environ.get("IMA_CLIENT_ID", "7be938688d7154e6a25043b56cc4b83e")
# API_KEY = os.environ.get("IMA_API_KEY", "KnmuqTJyQZj8xeqVeZr/sF7F1dr50Trez36zLMhq8egMgwW48rDXCwSmjeGL8STJlc5LKPvfLQ==")
# 华
CLIENT_ID = os.environ.get("IMA_CLIENT_ID", "d556cd55031a51d0b287ba25fc82adf2")
API_KEY = os.environ.get("IMA_API_KEY", "p5j55ryVAVJEA1OK3Xz7kxgrmTw+466QHFYrWIX4yVRESfcBYhkwOw0xH6nDtifi/Y0grNOKFA==")
BASE_URL = "https://ima.qq.com"


def call_api(path: str, body: dict) -> dict:
    """调用IMA API，包含详细的错误信息"""
    url = f"{BASE_URL}{path}"
    headers = {
        "ima-openapi-clientid": CLIENT_ID,
        "ima-openapi-apikey": API_KEY,
        "Content-Type": "application/json",
    }
    
    print(f"\n📤 请求信息:")
    print(f"  URL: {url}")
    print(f"  Headers: { {k: v[:20] + '...' if len(v) > 20 else v for k, v in headers.items()} }")
    print(f"  Body: {json.dumps(body, ensure_ascii=False)[:200]}...")
    
    try:
        resp = requests.post(url, json=body, headers=headers, timeout=30)
        print(f"  HTTP状态码: {resp.status_code}")
        print(f"  响应头: {dict(resp.headers)}")
        
        # 打印原始响应文本，便于调试
        print(f"  原始响应: {resp.text[:500]}")
        
        resp.raise_for_status()
        result = resp.json()
        print(f"  解析后的JSON响应: {json.dumps(result, ensure_ascii=False)[:500]}...")
        
        # 检查可能的错误码字段
        retcode = result.get("retcode")
        if retcode is None:
            # 尝试其他可能的错误码字段
            retcode = result.get("code", result.get("error_code", 0))
        
        if retcode != 0:
            errmsg = result.get("errmsg") or result.get("message") or result.get("error_msg") or "未知错误"
            raise Exception(f"[{retcode}] {errmsg}")
        
        return result.get("data", result)
        
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败: {e}")
        raise
    except json.JSONDecodeError as e:
        print(f"❌ 响应不是有效的JSON: {e}")
        print(f"  响应内容: {resp.text[:200]}")
        raise


def ts_to_str(ts_ms: str) -> str:
    """将毫秒时间戳转为可读日期"""
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000).strftime("%Y-%m-%d %H:%M")
    except (ValueError, OSError):
        return ts_ms

def search_knowledge_bases(query: str = "", cursor: str = "", limit: int = 20):
    """搜索/列出知识库（修复：移除了self参数）"""
    result = call_api("/openapi/wiki/v1/search_knowledge_base", {
        "query": query,
        "cursor": cursor,
        "limit": limit,
    })
    # 根据实际API响应结构调整返回格式
    # 有些API返回 "docs"，有些返回 "info_list"
    docs = result.get("docs", [])
    if not docs:
        docs = result.get("info_list", [])
    return docs, result.get("cursor", "")

def get_knowledge_list(kb_id: str, folder_id: str = "", cursor: str = "", limit: int = 20) -> dict:
    """
    浏览知识库内容

    参数:
      kb_id:     知识库 ID（必填）
      folder_id: 文件夹 ID，传空字符串表示根目录
      cursor:    游标，首次传 ""
      limit:     每页数量 (1-200)
    """
    body = {
        "knowledge_base_id": kb_id,
        "cursor": cursor,
        "limit": limit,
    }
    if folder_id:
        body["folder_id"] = folder_id
    return call_api("/openapi/wiki/v1/get_knowledge_list", body)  

def list_all_knowledge_bases(max_items: int = 50):
    """列出所有知识库（支持翻页）"""
    all_kbs = []
    cursor = ""
    count = 0
    
    while count < max_items:
        kbs, cursor = search_knowledge_bases(cursor=cursor, limit=20)
        if not kbs:
            break
        all_kbs.extend(kbs)
        count += len(kbs)
        if not cursor:
            break
    
    return all_kbs        

def print_note(item: dict, index: int = 1):
    """格式化输出一条笔记"""
    doc = item.get("doc", item)
    info = doc.get("basic_info", doc)
    title = info.get("title", "无标题")
    note_id = info.get("docid", info.get("note_id", "?"))
    summary = info.get("summary", "")
    modified = ts_to_str(info.get("modify_time", "0"))
    folder = info.get("folder_name", "")

    print(f"\n  ┌─ {'=' * 55}")
    print(f"  │ [{index}] {title}")
    print(f"  │ ├─ ID:       {note_id}")
    print(f"  │ ├─ 更新:     {modified}")
    if folder:
        print(f"  │ ├─ 笔记本:   {folder}")
    if summary:
        short_summary = summary.replace("\n", " ").strip()[:120]
        print(f"  │ └─ 摘要:     {short_summary}")
    print(f"  └─ {'=' * 55}")


def search_by_title(keyword: str, start: int = 0, end: int = 20) -> list:
    """按标题搜索"""
    result = call_api("/openapi/note/v1/search_note", {
        "search_type": 0,
        "query_info": {"title": keyword},
        "start": start,
        "end": end,
    })
    return result.get("docs", [])


def search_by_content(keyword: str, start: int = 0, end: int = 20) -> list:
    """按正文搜索"""
    result = call_api("/openapi/note/v1/search_note", {
        "search_type": 1,
        "query_info": {"content": keyword},
        "start": start,
        "end": end,
    })
    return result.get("docs", [])


def search_paginated(search_fn, keyword: str, max_pages: int = 1):
    """翻页搜索，合并结果（改为1页便于测试）"""
    all_items = []
    page_size = 20
    for page in range(max_pages):
        start = page * page_size
        end = start + page_size
        items = search_fn(keyword, start=start, end=end)
        all_items.extend(items)
        if len(items) < page_size:
            break
    return all_items


def print_results(items: list, keyword: str, mode: str):
    """统一打印搜索结果"""
    total = len(items)
    mode_label = "标题" if mode == "title" else "正文"
    print(f"\n🔍 按【{mode_label}】搜索「{keyword}」—— 共 {total} 条结果")

    if not items:
        print("   (无匹配笔记)")
        return

    for i, item in enumerate(items, 1):
        print_note(item, i)

        if mode == "content":
            highlight = item.get("highlight_info", {}) or {}
            content_hits = highlight.get("doc_content", "")
            if content_hits:
                pure = content_hits.replace("<em>", "【").replace("</em>", "】")
                print(f"  │   匹配片段: {pure[:200]}")

    print(f"\n  📊 共 {total} 条结果")




def main():
    if not CLIENT_ID or not API_KEY:
        print("❌ 请先设置环境变量或使用有效的凭证：")
        print("   export IMA_CLIENT_ID=\"你的ClientID\"")
        print("   export IMA_API_KEY=\"你的APIKey\"")
        print("   获取：https://ima.qq.com/agent-interface")
        sys.exit(1)

    keyword = sys.argv[1] if len(sys.argv) > 1 else None

    print("=" * 62)
    print("  📝 IMA 笔记搜索 Demo")
    print("  用法: python3 search_notes_demo.py [关键词]")
    print("=" * 62)

    # if keyword:
    #     keywords = [keyword]
    # else:
    #     print("\n📌 未指定关键词，使用默认搜索词演示\n")
    #     keywords = ["会议", "项目", "工作", "ima"]

    # for kw in keywords:
    #     print(f"\n{'─' * 62}")
    #     print(f"  搜索关键词: 「{kw}」")
    #     print(f"{'─' * 62}")

    #     try:
    #         # 按标题搜索
    #         title_items = search_paginated(search_by_title, kw)
    #         print_results(title_items, kw, "title")
    #     except Exception as e:
    #         print(f"❌ 标题搜索失败: {e}")

    #     try:
    #         # 按正文搜索
    #         content_items = search_paginated(search_by_content, kw)
    #         print_results(content_items, kw, "content")
    #     except Exception as e:
    #         print(f"❌ 正文搜索失败: {e}")

    print("\n>>> 列出知识库")
    print("=" * 62)
    try:
        kbs = list_all_knowledge_bases()
        
        if kbs:
            print(f"\n共找到 {len(kbs)} 个知识库:\n")
            for i, kb in enumerate(kbs, 1):
                kb_name = kb.get('kb_name', kb.get('title', '未命名'))
                kb_id = kb.get('id', kb.get('kb_id', '?'))
                kb_desc = kb.get('description', kb.get('desc', ''))
                kb_type = kb.get('base_type', kb.get('type', '未知'))
                
                print(f"  [{i}] 📚 {kb_name}")
                print(f"      ├─ ID: {kb_id}")
                print(f"      ├─ 类型: {kb_type}")
                if kb_desc:
                    print(f"      └─ 描述: {kb_desc[:100]}")
        else:
            print("  (无知识库或获取失败)")
    except Exception as e:
        print(f"  ⚠️ 获取知识库列表失败: {e}")

    try:
        articles = get_knowledge_list("LtqPu1fRJhboTvAu0MGt0jTHrZyDxdFq7GNtXvfuJlI=", limit=5)
        print(f"\n>>> 浏览知识库: {"招财进喵的知识库"} (ID: {kbs[0].get('id', kbs[0].get('kb_id', '?'))})")

        docs = articles.get("knowledge_list", [])
        print(f"  共 {len(docs)} 篇文章")

        for item in docs:
            print(f"  📄 {item['title']}")
    except Exception as e:
        print(f"  ⚠️ 获取知识库下文章列表失败: {e}")
    print(f"\n{'=' * 62}")
    print("  ✅ 搜索完成")


if __name__ == "__main__":
    main()