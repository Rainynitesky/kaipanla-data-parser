#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开盘啦数据爬虫 - 爬取指数和板块数据
只负责抓取数据，不做解析
数据保存到 debug 文件夹
"""
import os
os.environ['PYTHONWARNINGS'] = 'ignore'

import re
import json
import time
import requests
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEVICE_ID = "80ca7d1b-2a24-3cd0-a915-99b61f6f88aa"
VERSION = "5.23.0.4"
API_VERSION = "w44"
PHONE_OS_NEW = "1"
USER_ID = "7079210"
TOKEN = "8a553e54a7fba11665f33d745f30e204"

# 请求头
HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 12; ALN-AL00 Build/W528JS)",
    "Host": "apphis.longhuvip.com",
    "Connection": "Keep-Alive",
    "Accept-Encoding": "gzip"
}

# API 端点
API_URL = "https://apphis.longhuvip.com/w1/api/index.php"


js_real_ranking_info = {}
js_plate_info_qj = {}
js_pan_kou = {}
js_boomreason = {'boomreason': []}
js_son_plate_info = {}
js_zhishu_stock_list = ()

for date in ['2026-05-08', '2026-05-11']:
    for i in range(30):
        # get_real_ranking_info
        params = {"Order": "1", "a": "RealRankingInfo", "st": "30", "c": "ZhiShuRanking", "PhoneOSNew": PHONE_OS_NEW, "DeviceID": DEVICE_ID, "VerSion": VERSION, "Index": f"{i*30}", "Date": date, "apiv": API_VERSION, "Type": "1", "ZSType": "7"}
        body = "&".join([f"{k}={v}" for k, v in params.items()]) + "&"
        response = requests.post(API_URL, data=body, headers=HEADERS)

        decoded_text = response.text.encode('utf-8').decode('raw_unicode_escape')
        cleaned_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', decoded_text)
        res_i = json.loads(cleaned_text)
        # res_i = json.loads(response.text.encode('utf-8').decode('raw_unicode_escape'))

        if len(res_i["list"])==0:
            break
        else:
            for item in res_i["list"]:
                # get_plate_info_qj
                plate_id = item[0]
                params = {"a": "GetPlate_Info_QJ", "c": "ZhiShuRanking", "PhoneOSNew": PHONE_OS_NEW, "DeviceID": DEVICE_ID, "VerSion": VERSION, "Date": date, "apiv": API_VERSION, "PlateID": plate_id, "RStart": "0925", "REnd": "1500"}  
                body = "&".join([f"{k}={v}" for k, v in params.items()]) + "&"
                response = requests.post(API_URL, data=body, headers=HEADERS)
                decoded_text = response.text.encode('utf-8').decode('raw_unicode_escape')
                cleaned_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', decoded_text)
                res_i_j = json.loads(cleaned_text)
                # res_i_j = json.loads(response.text.encode('utf-8').decode('raw_unicode_escape'))
                res_i_j['List'].insert(0, plate_id)
                if js_plate_info_qj:
                    js_plate_info_qj['List'].append(res_i_j['List'])
                else:
                    js_plate_info_qj = {k: v for k, v in res_i_j.items()}
                    js_plate_info_qj["List"] = [js_plate_info_qj["List"]]

                # get_pan_kou
                params = {"a": "GetPanKou","c": "ZhiShuL2Data","PhoneOSNew": PHONE_OS_NEW,"DeviceID": DEVICE_ID,"VerSion": VERSION,"Token": TOKEN,"apiv": API_VERSION,"StockID": plate_id,"UserID": USER_ID,"Day": date}
                body = "&".join([f"{k}={v}" for k, v in params.items()]) + "&"
                response = requests.post(API_URL, data=body, headers=HEADERS)
                decoded_text = response.text.encode('utf-8').decode('raw_unicode_escape')
                cleaned_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', decoded_text)
                res_i_k = json.loads(cleaned_text)
                # res_i_k = json.loads(response.text.encode('utf-8').decode('raw_unicode_escape'))
                res_i_k['pankou'].insert(0, res_i_k['code'])
                poped = res_i_k.pop('code')

                if js_pan_kou:
                    js_pan_kou['pankou'].append(res_i_k['pankou'])
                else:
                    js_pan_kou = {k: v for k, v in res_i_k.items()}
                    js_pan_kou["pankou"] = [js_pan_kou["pankou"]]


                # GetDayBaseFaceListZDEvnArt
                params = {"a": "GetDayBaseFaceListZDEvnArt","c": "ZhiShuKLine","PhoneOSNew": PHONE_OS_NEW,"DeviceID": DEVICE_ID,"VerSion": VERSION,"Token": TOKEN,"apiv": API_VERSION, "StockID": plate_id, "UserID": USER_ID, 'Index': '0', 'st': '10', 'Type': '0', 'IsBoom': '0'}
                body = "&".join([f"{k}={v}" for k, v in params.items()]) + "&"
                response = requests.post(API_URL, data=body, headers=HEADERS)
                decoded_text = response.text.encode('utf-8').decode('raw_unicode_escape')
                cleaned_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', decoded_text)
                res_i_o = json.loads(cleaned_text)
                # res_i_o = json.loads(response.text.encode('utf-8').decode('raw_unicode_escape'))
                for item in res_i_o.get('List', []):
                    if item.get('Date') == date:
                        js_boomreason['boomreason'].append([plate_id, item.get('BoomReason').strip(), item.get('IsBoom')])
                        break

                # get_son_plate_info
                params = {"a": "SonPlate_Info", "c": "ZhiShuRanking", "PhoneOSNew": PHONE_OS_NEW, "DeviceID": DEVICE_ID, "VerSion": VERSION, "IsShow": "1", "Date": date, "apiv": API_VERSION, "PlateID": plate_id}
                body = "&".join([f"{k}={v}" for k, v in params.items()]) + "&"
                response = requests.post(API_URL, data=body, headers=HEADERS)
                decoded_text = response.text.encode('utf-8').decode('raw_unicode_escape')
                cleaned_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', decoded_text)
                res_i_m = json.loads(cleaned_text)
                # res_i_m = json.loads(response.text.encode('utf-8').decode('raw_unicode_escape'))
                if len(res_i_m["List"])==0:
                    a, b = None, None
                    for item in res_i['list']:
                        if item[0]=='801159':
                            a, b = item[1:3]
                    res_i_m["List"] = [[plate_id, a, b]]

                for item in res_i_m["List"]:
                    item.insert(0, plate_id)

                if js_son_plate_info:
                    js_son_plate_info['List'].extend(res_i_m['List'])
                else:
                    js_son_plate_info = {k: v for k, v in res_i_m.items()}
                    js_son_plate_info["List"] = js_son_plate_info["List"]

                # get_zhishu_stock_list
                for lst_i in res_i_m["List"]:
                    son_plate_id = lst_i[1]
                    params = {"Order": "1", "TSZB": "0", "a": "ZhiShuStockList_W8", "st": "30", "c": "ZhiShuRanking", "PhoneOSNew": PHONE_OS_NEW, "old": "1", "DeviceID": DEVICE_ID, "VerSion": VERSION, "IsZZ": "0", "Token": TOKEN, "Index": "0", "Date": date, "apiv": API_VERSION, "Type": "6", "IsKZZType": "0", "UserID": USER_ID, "PlateID": son_plate_id, "TSZB_Type": "0", "filterType": "0"}
                    body = "&".join([f"{k}={v}" for k, v in params.items()]) + "&"
                    response = requests.post(API_URL, data=body, headers=HEADERS)
                    decoded_text = response.text.encode('utf-8').decode('raw_unicode_escape')
                    cleaned_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', decoded_text)
                    res_i_n = json.loads(cleaned_text)
                    # res_i_n = json.loads(response.text.encode('utf-8').decode('raw_unicode_escape'))
                    for item in res_i_n["list"]:
                        item.insert(0, plate_id)
                        item.insert(1, son_plate_id)

                    if js_zhishu_stock_list:
                        js_zhishu_stock_list['list'].extend(res_i_n['list'])
                    else:
                        js_zhishu_stock_list = {k: v for k, v in res_i_n.items()}

            if (js_real_ranking_info and (res_i["list"][0][0] in js_real_ranking_info["list"][0][0])):
                break
            elif js_real_ranking_info:
                js_real_ranking_info['list'].extend(res_i['list'])
            else:
                js_real_ranking_info = {k: v for k, v in res_i.items()}
            time.sleep(1)

    lst_col = ['父代码', '父板块', '强度', '涨幅', '涨速', '成交额', '主力净额', '主力买', '主力卖', '量比', '流通市值', 'x1', '300万大单净额', '总市值', '第一季度机构增仓', '2026年平均PE', '2027年平均PE', 'x2', 'x3']
    df_real_ranking_info = pd.DataFrame(js_real_ranking_info["list"], columns=lst_col)
    df_real_ranking_info = df_real_ranking_info[[v for v in df_real_ranking_info.columns if v.find('x')!=0]]

    lst_col = ['父代码', '排名', '强度', '成交额', '主力净额', '涨幅', '涨停数', '涨停封单', '大额封单']
    df_plate_info_qj = pd.DataFrame(js_plate_info_qj["List"], columns=lst_col)
    df_plate_info_qj = df_plate_info_qj[['父代码', '排名', '涨停数', '涨停封单', '大额封单']]

    lst_col = ['父代码', '成交额', '换手率', '市盈率', '主力买', '主力卖', '主力净额', '上涨', '下跌', '平盘', '流通市值', '总市值']
    df_pan_kou = pd.DataFrame(js_pan_kou["pankou"], columns=lst_col)
    df_pan_kou = df_pan_kou[['父代码', '换手率', '市盈率', '上涨', '下跌', '平盘']]

    lst_col = ['父代码', '爆发原因', '是否爆发']
    df_boomreason = pd.DataFrame(js_boomreason["boomreason"], columns=lst_col)

    lst_col = ['父代码', '子代码', '子板块', '子板块强度']
    df_son_plate_info = pd.DataFrame(js_son_plate_info["List"], columns=lst_col)

    lst_col = ['父代码', '子代码', '代码', '名称', 'x3', 'x3', '所属板块标签', '价格', '涨幅', '成交额', '实际换手率', '涨速', '实际流通', '主力买', '主力卖', '主力净额', 'x15', 'x16', 'x17', 'x18', '卖流占比', '净流占比', '区间涨幅', '量比', 'x23', '几天几板', 'x8', '换手率', 'x27', 'x28', '收盘封单', '最大封单', 'x31', 'x32', 'x33', '振幅', 'x35', 'x36', 'x37', '总市值', '流通市值', 'x40', '领涨次数', 'x42', '机构增仓Q1', 'x44', 'x45', 'x46', 'x47', 'x48', 'x49', 'x50', '300万以上大单净额', 'x52', 'x53', '市净率', 'x55', 'x56', 'x57', 'x58', '人气值', '人气排名变化', '市盈率动', '市盈率TTM', 'PE静']
    df_zhishu_stock_list = pd.DataFrame(js_zhishu_stock_list['list'], columns=lst_col)
    df_zhishu_stock_list = df_zhishu_stock_list[[v for v in df_zhishu_stock_list.columns if v.find('x')!=0]]

    df_plate_info = df_real_ranking_info.merge(df_plate_info_qj, how='left', on='父代码')
    df_plate_info = df_plate_info.merge(df_pan_kou, how='left', on='父代码')
    df_plate_info = df_plate_info.merge(df_boomreason, how='left', on='父代码')

    df_plate_info.to_csv(f'{BASE_DIR}/data/main_plate_info_{date}.csv')
    df_son_plate_info.to_csv(f'{BASE_DIR}/data/sub_plate_info_{date}.csv')
    df_zhishu_stock_list.to_csv(f'{BASE_DIR}/data/stock_info_{date}.csv')


##############################################


##############################################
# # GetVolTurIncremental 分时成交额
# # GetTrendIncremental  分时指数
# plate_id = '801159'
# date = '2026-05-08'

# params = {"a": "GetVolTurIncremental","c": "ZhiShuL2Data","PhoneOSNew": PHONE_OS_NEW,"DeviceID": DEVICE_ID,"VerSion": VERSION,"apiv": API_VERSION,"StockID": plate_id,"Day": date}
# body = "&".join([f"{k}={v}" for k, v in params.items()]) + "&"
# response = requests.post(API_URL, data=body, headers=HEADERS)
# res_i_l1 = json.loads(response.text.encode('utf-8').decode('raw_unicode_escape'))

# params['a'] = 'GetTrendIncremental'
# body = "&".join([f"{k}={v}" for k, v in params.items()]) + "&"
# response = requests.post(API_URL, data=body, headers=HEADERS)
# res_i_l2 = json.loads(response.text.encode('utf-8').decode('raw_unicode_escape'))

# # GetKLineDay_W14
# stock_id="SH000001"
# stock_type="d"
# index="0"
# params = {"st": "135","a": "GetKLineDay_W14", "c": "StockLineData", "PhoneOSNew": PHONE_OS_NEW, "DeviceID": DEVICE_ID, "VerSion": VERSION, "Token": TOKEN, "Index": index, "apiv": API_VERSION, "Type": stock_type, "StockID": stock_id, "UserID": USER_ID, "Is_FS": "1" }
# body = "&".join([f"{k}={v}" for k, v in params.items()]) + "&"
# response = requests.post(API_URL, data=body, headers=HEADERS)

# # GetPlateZF
# stock_id="801001"
# day=None
# params = {"a": "GetPlateZF", "apiv": API_VERSION, "c": "ZhiShuL2Data", "StockID": stock_id, "PhoneOSNew": PHONE_OS_NEW, "DeviceID": DEVICE_ID, "VerSion": VERSION, "Day": day}
# body = "&".join([f"{k}={v}" for k, v in params.items()]) + "&"
# response = requests.post(API_URL, data=body, headers=HEADERS)

# # get_bk_fenshi_zhibo
# plate_id="801159"
# date='2026-05-15'
# params = {"a": "BKFenShiZhiBo", "c": "HisConceptionPoint", "PhoneOSNew": PHONE_OS_NEW, "DeviceID": DEVICE_ID, "VerSion": VERSION, "Date": date, "apiv": API_VERSION, "PlateID": plate_id}

# body = "&".join([f"{k}={v}" for k, v in params.items()]) + "&"

# response = requests.post(API_URL, data=body, headers=HEADERS)
# res_i_o = json.loads(response.text.encode('utf-8').decode('raw_unicode_escape'))
