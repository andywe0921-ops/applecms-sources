#!/usr/bin/env python3
"""
苹果CMS 采集接口可用性检测 & 自动更新脚本
同时生成：
1. applecms_sources.json          （原始源列表）
2. yingshicang_sites.json         （影视仓/TVBox 格式）
3. general_sites.json             （通用 sites 格式）
"""

import json
import urllib.request
import urllib.error
import ssl
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

INPUT_JSON = "applecms_sources.json"
TIMEOUT = 8
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AppleCMS-Checker/1.1)"}

def test_url(name, url):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            data = resp.read(1500).decode("utf-8", errors="ignore")
            if '"code"' in data and (":1" in data or ": 1" in data):
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

def make_key(name):
    """简单生成 key"""
    mapping = {
        "巨量资源": "juliang", "暴风资源": "baofeng", "量子资源": "liangzi",
        "索尼资源": "suoni", "闪电资源": "shandian", "无尽资源": "wujin",
        "光速资源": "guangsu", "金鹰资源": "jinying", "素博资源": "subo",
        "红牛资源": "hongniu", "豪华资源": "haohua", "虎牙资源": "huya",
        "极速资源": "jisu", "优质资源": "youzhi", "非凡资源": "feifan",
        "魔都资源": "modu", "如意资源": "ruyi", "电影天堂资源": "dytt",
        "360资源": "zy360", "天涯资源": "tianya", "爱奇艺资源": "iqiyi",
        "U酷资源": "uku", "百度资源": "baidu"
    }
    return mapping.get(name, name[:6])

def main():
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    sources = data.get("sources", [])
    xml_sources = data.get("xml_sources", [])

    print(f"正在测试 {len(sources)} 个 JSON 源 + {len(xml_sources)} 个 XML 源...")
    results = []
    failed = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(test_url, s["name"], s["url"]): s for s in sources}
        for future in as_completed(futures):
            old = futures[future]
            res = future.result()
            if res["status"] == "ok":
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

    xml_ok = []
    for s in xml_sources:
        res = test_url(s["name"], s["url"])
        if res["status"] in ("ok", "ok_xml"):
            xml_ok.append(s)
            print(f"✅ {s['name']} (XML)")
        else:
            failed.append(f"{s['name']} | {s['url']} | {res['error']}")
            print(f"❌ {s['name']}")

    results.sort(key=lambda x: x.get("total_approx") or 0, reverse=True)

    tz = timezone(timedelta(hours=8))
    now_str = datetime.now(tz).strftime("%Y-%m-%dT%H:%M:%S+08:00")

    # 1. 更新原始 applecms_sources.json
    data["updated_at"] = now_str
    data["sources"] = results
    data["xml_sources"] = xml_ok
    data["failed_at_test"] = failed
    data["notes"] = [
        f"测试时间: {now_str}",
        "total_approx 为接口返回的大致资源总量，仅供参考",
        "建议在苹果CMS后台「采集 → 自定义接口」中添加，接口类型选 json（XML源选 xml）",
        "部分站支持 /from/线路名/ 优化，例如量子: .../vod/from/lzm3u8/",
        "资源站随时可能变更，请定期重新运行本脚本更新",
        "本脚本会同时生成 yingshicang_sites.json 和 general_sites.json"
    ]

    with open("applecms_sources.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("\n已更新 applecms_sources.json")

    # 2. 生成影视仓格式
    yingshi = {"sites": []}
    for s in results:
        yingshi["sites"].append({
            "key": make_key(s["name"]),
            "name": s["name"],
            "type": 1,
            "api": s["url"],
            "searchable": 1,
            "quickSearch": 1,
            "filterable": 1
        })
    with open("yingshicang_sites.json", "w", encoding="utf-8") as f:
        json.dump(yingshi, f, ensure_ascii=False, indent=2)
    print("已生成 yingshicang_sites.json")

    # 3. 生成通用格式
    general = {"sites": []}
    for s in results:
        general["sites"].append({
            "key": make_key(s["name"]),
            "name": s["name"],
            "type": 1,
            "api": s["url"],
            "searchable": 1,
            "quickSearch": 1,
            "filterable": 1,
            "changeable": 1
        })
    with open("general_sites.json", "w", encoding="utf-8") as f:
        json.dump(general, f, ensure_ascii=False, indent=2)
    print("已生成 general_sites.json")

    print(f"\n完成！可用源: {len(results)}，XML源: {len(xml_ok)}")

if __name__ == "__main__":
    main()
