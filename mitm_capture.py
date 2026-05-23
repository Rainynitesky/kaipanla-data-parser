#!/usr/bin/env python3
"""
开盘啦 mitmproxy 抓包脚本
- 过滤域名：只抓 longhuvip / 523touzi
- 抓包输出到 captures/ 目录
- 可选：劫持 getIPList 响应（将 socket IP 改为代理地址）
用于 crawler_batch.py 的 token 刷新
"""
import os
os.environ['PYTHONWARNINGS'] = 'ignore'

import json
import time
from mitmproxy import http

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "captures")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===== 配置 =====
# 域名过滤白名单
ALLOWED_DOMAINS = ('longhuvip', '523touzi')
# socket IP 劫持开关（MuMu 模拟器需要时开启）
SOCKET_HIJACK = False
SOCKET_PROXY = '10.0.2.2:14000'

seq = 0


def request(flow: http.HTTPFlow):
    global seq
    host = flow.request.pretty_host
    if not any(kw in host for kw in ALLOWED_DOMAINS):
        return

    seq += 1

    body = flow.request.get_text()
    api_controller = api_action = "unknown"
    if body:
        for part in body.split('&'):
            if part.startswith('c='):
                api_controller = part.split('=', 1)[1]
            elif part.startswith('a='):
                api_action = part.split('=', 1)[1]

    flow.metadata['seq'] = seq
    flow.metadata['controller'] = api_controller
    flow.metadata['action'] = api_action
    flow.metadata['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S')


def response(flow: http.HTTPFlow):
    seq = flow.metadata.get('seq', 0)
    if not seq:
        return

    api_controller = flow.metadata['controller']
    api_action = flow.metadata['action']
    timestamp = flow.metadata['timestamp']
    host = flow.request.pretty_host
    body = flow.request.get_text()

    # 可选：劫持 getIPList
    if SOCKET_HIJACK and 'getIPList' in flow.request.url:
        try:
            resp = flow.response.get_json()
            if resp and resp.get('errcode') == 0:
                original = resp.get('defIP', '')
                resp['defIP'] = SOCKET_PROXY
                resp['ipList'] = [SOCKET_PROXY]
                flow.response.set_text(json.dumps(resp))
                print(f"[SOCKET劫持] getIPList: {original} → {SOCKET_PROXY}")
        except Exception:
            pass

    # 保存抓包数据
    resp_raw = flow.response.get_text()
    try:
        resp_body = json.loads(resp_raw)
    except Exception:
        resp_body = None

    filename = f"{seq:04d}_{host.replace('.', '_')}_{api_controller}_{api_action}.json"
    filepath = os.path.join(OUTPUT_DIR, filename)

    data = {
        'seq': seq,
        'timestamp': timestamp,
        'method': flow.request.method,
        'url': flow.request.pretty_url,
        'request_body': body or '',
        'status_code': flow.response.status_code,
        'response_body': resp_body,
    }

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 控制台输出
    lst_len = 0
    if resp_body and isinstance(resp_body, dict):
        lst = resp_body.get('List', resp_body.get('list', []))
        if isinstance(lst, list):
            lst_len = len(lst)

    print(f"[{seq:04d}] {api_controller}/{api_action} → {flow.response.status_code} List={lst_len}")
