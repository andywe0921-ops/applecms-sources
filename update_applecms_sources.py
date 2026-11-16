#!/usr/bin/env python3
"""
苹果CMS 采集接口可用性检测 & 自动更新脚本
用法: python3 update_applecms_sources.py
会重新测试 sources 列表，更新 status / total，并写出新的 JSON。
可配合 cron 定时运行实现“自动更新可用地址”。
"""

import json
import urllib.request
import urllib.error
import ssl
import time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# 忽略部分证书问题（部分资源站证书不规范）
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

INPUT_JSON = "applecms_sources.json"
OUTPUT_JSON = "applecms_sources.json"  # 覆盖更新，也可改成带时间戳

TIMEOUT = 8
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AppleCMS-Checker/1.0)"}

def test_url(name, url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            data = resp.read(1200).decode("utf-8", errors="ignore")
            if '"code"' in data and (":1" in data or ": 1" in data):
                # 尝试提取 total
                total = None
                for key in ['"total":', '"total" :']:
                    if key in data:
                        try:
                            start = data.find(key) + len(key)
                            num = ""
                            for c in data[start:start+12]:
                                if c.isdigit():
                                    num += c
                                elif num:
                                    break
                            if num:
                                total = int(num)
                        except:
                            pass
                return {"name": name, "url": url, "status": "ok", "total_approx": total, "error": None}
            elif "<rss" in data or "<list" in data.lower():
                return {"name": name, "url": url, "status": "ok_xml", "total_approx": None, "error": None}
            else:
                return {"name": name, "url": url, "status": "fail", "total_approx": None, "error": "unexpected response"}
    except Exception as e:
        return {"name": name, "url": url, "status": "fail", "total_approx": None, "error": str(e)[:80]}

def main():
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    sources = data.get("sources", [])
    xml_sources = data.get("xml_sources", [])

    print(f"正在测试 {len(sources)} 个 JSON 源 + {len(xml_sources)} 个 XML 源...")
    results = []
    failed = []

    # 并行测试
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(test_url, s["name"], s["url"]): s for s in sources}
        for future in as_completed(futures):
            old = futures[future]
            res = future.result()
            if res["status"] == "ok":
                # 保留原有 from 等字段
                new_item = {
                    "name": res["name"],
                    "url": res["url"],
                    "from": old.get("from"),
                    "total_approx": res["total_approx"] or old.get("total_approx"),
                    "status": "ok"
                }
                results.append(new_item)
                print(f"✅ {res['name']}  total={res['total_approx']}")
            else:
                failed.append(f"{res['name']} | {res['url']} | {res['error']}")
                print(f"❌ {res['name']}  {res['error']}")

    # XML 也测一下
    xml_ok = []
    for s in xml_sources:
        res = test_url(s["name"], s["url"])
        if res["status"] in ("ok", "ok_xml"):
            xml_ok.append(s)
            print(f"✅ {s['name']} (XML)")
        else:
            failed.append(f"{s['name']} | {s['url']} | {res['error']}")
            print(f"❌ {s['name']}")

    # 按资源量大致排序
    results.sort(key=lambda x: x.get("total_approx") or 0, reverse=True)

    # 更新数据
    tz = timezone(timedelta(hours=8))
    data["updated_at"] = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")
    data["sources"] = results
    data["xml_sources"] = xml_ok
    data["failed_at_test"] = failed
    data["notes"] = [
        f"测试时间: {data['updated_at']}",
        "total_approx 为接口返回的大致资源总量，仅供参考",
        "建议在苹果CMS后台「采集 → 自定义接口」中添加，接口类型选 json（XML源选 xml）",
        "部分站支持 /from/线路名/ 优化，例如量子: .../vod/from/lzm3u8/",
        "资源站随时可能变更，请定期重新运行本脚本更新",
        "本脚本可配合 cron 实现自动更新：0 */6 * * * cd /path && python3 update_applecms_sources.py"
    ]

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n完成！可用 JSON 源: {len(results)}，XML 源: {len(xml_ok)}")
    print(f"已写入 {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
