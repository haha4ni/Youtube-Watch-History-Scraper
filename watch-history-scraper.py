import time
import json
import re
import sys
import argparse
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager

class Tee:
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()

def setup_logging(debug_mode):
    if debug_mode:
        log_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"output_log_{log_time}.txt"
        sys.stdout = Tee(sys.stdout, open(log_filename, 'a', encoding='utf-8'))

def load_cookies_from_file(filename):
    cookies = []
    with open(filename, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            parts = line.split("\t")
            if len(parts) != 7:
                continue
            domain, flag, path, secure, expiration, name, value = parts
            cookie = {
                "domain": domain,
                "name": name,
                "value": value,
                "path": path,
                "secure": secure.upper() == "TRUE",
                "expiry": int(expiration) if expiration.isdigit() else None,
            }
            cookies.append(cookie)
    return cookies

def parse_time(text, today_str):
    today = datetime.strptime(today_str, "%Y-%m-%d")

    def parse_hour(period, hour, minute):
        hour, minute = int(hour), int(minute)
        if period in ("下午", "晚上") and hour != 12:
            hour += 12
        elif period == "凌晨":
            hour = 0 if hour == 12 else hour
        elif period == "上午" and hour == 12:
            hour = 0
        elif period == "清晨":
            # 清晨通常指 5~7 點，這裡直接用原始 hour
            pass
        return hour, minute

    # 1. 2023年3月5日 上午10:20
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s+(凌晨|清晨|上午|下午|晚上)(\d{1,2}):(\d{2})", text)
    if m:
        year, month, day, period, hour, minute = m.groups()
        hour, minute = parse_hour(period, hour, minute)
        dt = datetime(int(year), int(month), int(day), hour, minute)
        return dt.isoformat() + "Z"

    # 2. 3月5日 上午10:20
    m = re.match(r"(\d{1,2})月(\d{1,2})日\s+(凌晨|清晨|上午|下午|晚上)(\d{1,2}):(\d{2})", text)
    if m:
        month, day, period, hour, minute = m.groups()
        hour, minute = parse_hour(period, hour, minute)
        dt = datetime(today.year, int(month), int(day), hour, minute)
        if dt > today:
            dt = dt.replace(year=today.year - 1)
        return dt.isoformat() + "Z"

    # 3. 今天/昨天 上午10:20
    if text.startswith("今天 ") or text.startswith("昨天 "):
        day_part, time_part = text.split()
        base_date = today if day_part == "今天" else today - timedelta(days=1)
        m = re.match(r"(凌晨|清晨|上午|下午|晚上)(\d{1,2}):(\d{2})", time_part)
        if not m:
            return None
        period, hour, minute = m.groups()
        hour, minute = parse_hour(period, hour, minute)
        return base_date.replace(hour=hour, minute=minute).isoformat() + "Z"

    return None

def scroll_one_step_to_bottom(driver, pause=2):
    last_height = driver.execute_script("return document.documentElement.scrollHeight")
    driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
    time.sleep(pause)
    new_height = driver.execute_script("return document.documentElement.scrollHeight")
    return new_height > last_height

def date_to_timestamp(date_str):
    dt = datetime.strptime(date_str, "%Y/%m/%d")
    end_of_day = dt.replace(hour=23, minute=59, second=59, microsecond=999000)
    return int(end_of_day.timestamp() * 1e6)

def get_youtube_history_url(date_str=None):
    base_url = "https://myactivity.google.com/product/youtube?restrict=youtube"
    if date_str:
        max_timestamp = date_to_timestamp(date_str)
        return f"{base_url}&max={max_timestamp}"
    return base_url

def main(start_date=None, end_date=None, output_file="youtube_watch_history.json"):
    start_time = time.time()
    cookies = load_cookies_from_file("myactivity.google.com_cookies.txt")
    today_str = datetime.today().strftime("%Y-%m-%d")
    end_dt = None
    if end_date:
        end_dt = datetime.strptime(end_date, "%Y/%m/%d")

    options = webdriver.EdgeOptions()
    options.add_argument("--start-maximized")
    driver = webdriver.Edge(service=EdgeService(EdgeChromiumDriverManager().install()), options=options)

    # start_date 對應 max= 參數，end_date 為結束條件
    url = get_youtube_history_url(start_date)
    driver.get(url)
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except:
            pass
    driver.refresh()
    time.sleep(5)
    for i in range(5, 0, -1):
        print(f"\r請確認Cookie登入成功與否，會在 {i} 秒後繼續執行...", end="", flush=True)
        time.sleep(1)
    print()  # 換行，避免覆蓋後續 log

    seen_headers = set()      # 日期 header 卡池
    seen_search_urls = set()  # 搜尋活動 url 卡池
    seen_unique_ids = set()   # 活動卡片 unique_id 卡池
    seen_logs = set()
    results = []

    MAX_SCROLL_ROUNDS = float('inf')
    EMPTY_ROUND_THRESHOLD = 3
    rounds = 0
    empty_rounds = 0
    last_header = None
    last_processed_idx = 0  # 新增：記錄上一輪處理到的 index

    while rounds < MAX_SCROLL_ROUNDS:
        print(f"\n[SCROLL] 第 {rounds + 1} 次捲動 🔽")
        for _ in range(2):
            scroll_one_step_to_bottom(driver, pause=5)

        # 搜索所有 c-wiz[class*='xDtZAf'] 以涵蓋所有活動卡片
        activities = driver.find_elements(By.CSS_SELECTOR, "c-wiz.xDtZAf, div.CW0isc")
        print(f"[INFO] 活動+日期區塊總數量：{len(activities)}")
        elapsed = time.time() - start_time
        print(f"[INFO] 程式已執行 {elapsed:.1f} 秒")
        new_found = 0

        skip_count = 0
        processed_count = 0
        for idx, act in enumerate(activities):
            if idx < last_processed_idx:
                skip_count += 1
                print(f"\r[LOG] index={idx+1}/{len(activities)} | 處理: {processed_count} | skip: {skip_count}", end="", flush=True)
                continue  # 跳過前面已處理過的
            processed_count += 1
            print(f"\r[LOG] index={idx+1}/{len(activities)} | 處理: {processed_count} | skip: {skip_count}", end="", flush=True)
            try:
                # LOG 
                headers = act.find_elements(By.CSS_SELECTOR, "div.MCZgpb > h2.rp10kf")
                if headers:
                    latest = headers[-1].text.strip()
                    if latest in seen_headers:
                        continue
                    seen_headers.add(latest)
                    if latest and latest != last_header:
                        last_header = latest
                        print(f"[📅 日期更新] 現在使用：{last_header}")
                        # 檢查日期是否早於 end_date，若是則終止
                        if end_dt:
                            try:
                                # 支援有年份、無年份、今天、昨天格式
                                if "年" in last_header:
                                    header_dt = datetime.strptime(last_header, "%Y年%m月%d日")
                                elif "今天" in last_header:
                                    header_dt = datetime.today()
                                elif "昨天" in last_header:
                                    header_dt = datetime.today() - timedelta(days=1)
                                else:
                                    header_dt = datetime.strptime(f"{datetime.today().year}年" + last_header, "%Y年%m月%d日")
                                if header_dt < end_dt:
                                    print(f"[STOP] 已達結束日期 {end_date}，終止爬蟲")
                                    elapsed = time.time() - start_time
                                    print(f"[INFO] 程式總執行時間：{elapsed:.1f} 秒")
                                    driver.quit()
                                    print(f"\n✅ 共儲存 {len(results)} 筆活動至 {output_file}")
                                    return
                            except Exception as e:
                                print(f"[WARN] 日期解析失敗: {e}")
                    continue

                qtgv3c_text = act.find_element(By.CSS_SELECTOR, "div.QTGV3c").text.strip()

                # 檢查是否為搜尋活動
                if qtgv3c_text.startswith("搜尋「"):
                    if qtgv3c_text in seen_search_urls:
                        continue
                    seen_search_urls.add(qtgv3c_text)
                    print(f"[LOG] 搜尋活動：{qtgv3c_text}", flush=True)
                    continue  # 目前不處理搜尋活動

                # 檢查是否為已查看活動
                if qtgv3c_text.startswith("已查看「"):
                    if qtgv3c_text in seen_logs:
                        continue
                    seen_logs.add(qtgv3c_text)
                    print(f"[LOG] 已查看活動：{qtgv3c_text}", flush=True)
                    continue  # 目前不處理已查看活動

                # 取得唯一ID（c-wiz 內 c-data 的 id 屬性）
                try:
                    cdata = act.find_element(By.CSS_SELECTOR, "c-data")
                    unique_id = cdata.get_attribute('id')
                except Exception:
                    unique_id = None
                if not unique_id:
                    continue

                # 取得 title 與 title_url（從 QTGV3c 內的 a.l8sGWb 取得）
                qtgv3c_elem = act.find_element(By.CSS_SELECTOR, "div.QTGV3c")
                a_elem = qtgv3c_elem.find_element(By.CSS_SELECTOR, "a.l8sGWb")
                title = a_elem.text.strip()
                title_url = a_elem.get_attribute("href")

                time_text = act.find_element(By.CSS_SELECTOR, "div.H3Q9vf.XTnvW").text
                time_label = time_text.split("•")[0].strip()

                full_time = f"{last_header} {time_label}"
                time_iso = parse_time(full_time, today_str)
                if not time_iso:
                    # print(f"[WARN] 活動卡片缺少 unique_id={unique_id}，index={idx+1}，HTML：\n{act.get_attribute('outerHTML')}")
                    continue

                subtitles = []
                try:
                    ch_elem = act.find_element(By.CSS_SELECTOR, "div.SiEggd a")
                    channel_name = ch_elem.text.strip()
                    channel_url = ch_elem.get_attribute("href")
                    subtitles.append({"name": channel_name, "url": channel_url})
                except:
                    pass

                results.append({
                    "header": "YouTube",
                    "title": title,
                    "titleUrl": title_url,
                    "subtitles": subtitles,
                    "time": time_iso,
                    "products": ["YouTube"],
                    "activityControls": ["YouTube watch history"]
                })

                # 每新增一筆就即時寫入 json 檔案
                with open(output_file, "w", encoding="utf-8") as f:
                    text = json.dumps(results, ensure_ascii=False, indent=2)
                    text = text.replace('},\n  {', '},{')
                    # 處理只有一個元素的陣列（subtitles/products/activityControls等）壓成一行，陣列後面可接逗號或右大括號
                    text = re.sub(r'\[\n\s+({.*?})\n\s+\](,?)', r'[\1]\2', text)
                    text = re.sub(r'\[\n\s+(".*?")\n\s+\](,?)', r'[\1]\2', text)
                    f.write(text)

                new_found += 1
                # 取得頻道名稱（若有）
                channel_display = ""
                if subtitles and isinstance(subtitles, list) and len(subtitles) > 0:
                    channel_display = f" | 頻道：{subtitles[0]['name']}"
                print(f"[✓] 新增：{title} @ {time_iso}{channel_display}")

            except Exception as e:
                print(f"[ERR] 活動處理失敗：{e}")
                continue
        print()  # 換行，避免進度條覆蓋後續 log
        last_processed_idx = len(activities)  # 記錄本輪最後一筆 index

        if new_found == 0:
            empty_rounds += 1
            print(f"[INFO] 無新增（{empty_rounds}/{EMPTY_ROUND_THRESHOLD}）")
            if empty_rounds >= EMPTY_ROUND_THRESHOLD:
                print("[STOP] 無新活動，自動結束")
                break
        else:
            empty_rounds = 0

        rounds += 1

    elapsed = time.time() - start_time
    print(f"[INFO] 程式總執行時間：{elapsed:.1f} 秒")
    print(f"\n✅ 共儲存 {len(results)} 筆活動至 {output_file}")
    driver.quit()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--start-date', type=str, help='指定 max= 參數 (格式: YYYY/MM/DD)', default=None)
    parser.add_argument('--end-date', type=str, help='結束條件，遇到小於這天的活動就停止 (格式: YYYY/MM/DD)', default=None)
    parser.add_argument('--output', type=str, help='輸出檔案名稱', default='youtube_watch_history.json')
    parser.add_argument('--debug', action='store_true', help='啟用 debug log 輸出到檔案')
    args = parser.parse_args()
    setup_logging(args.debug)
    main(args.start_date, args.end_date, args.output)
