import time
import json
import re
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.service import Service as EdgeService
from webdriver_manager.microsoft import EdgeChromiumDriverManager

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
        return hour, minute

    # 1. 2023年3月5日 上午10:20
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日\s+(凌晨|上午|下午|晚上)(\d{1,2}):(\d{2})", text)
    if m:
        year, month, day, period, hour, minute = m.groups()
        hour, minute = parse_hour(period, hour, minute)
        dt = datetime(int(year), int(month), int(day), hour, minute)
        return dt.isoformat() + "Z"

    # 2. 3月5日 上午10:20
    m = re.match(r"(\d{1,2})月(\d{1,2})日\s+(凌晨|上午|下午|晚上)(\d{1,2}):(\d{2})", text)
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
        m = re.match(r"(凌晨|上午|下午|晚上)(\d{1,2}):(\d{2})", time_part)
        if not m:
            return None
        period, hour, minute = m.groups()
        hour, minute = parse_hour(period, hour, minute)
        return base_date.replace(hour=hour, minute=minute).isoformat() + "Z"

    return None

def scroll_to_bottom(driver, pause=2, max_idle=3):
    last_height = driver.execute_script("return document.documentElement.scrollHeight")
    idle_rounds = 0
    while idle_rounds < max_idle:
        driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
        time.sleep(pause)
        new_height = driver.execute_script("return document.documentElement.scrollHeight")
        if new_height == last_height:
            idle_rounds += 1
        else:
            idle_rounds = 0
            last_height = new_height

def scroll_one_step(driver, pause=2):
    driver.execute_script("window.scrollBy(0, window.innerHeight);")
    time.sleep(pause)

def scroll_one_step_to_bottom(driver, pause=2):
    last_height = driver.execute_script("return document.documentElement.scrollHeight")
    driver.execute_script("window.scrollTo(0, document.documentElement.scrollHeight);")
    time.sleep(pause)
    new_height = driver.execute_script("return document.documentElement.scrollHeight")
    return new_height > last_height

def main():
    cookies = load_cookies_from_file("myactivity.google.com_cookies.txt")
    today_str = datetime.today().strftime("%Y-%m-%d")

    options = webdriver.EdgeOptions()
    options.add_argument("--start-maximized")
    driver = webdriver.Edge(service=EdgeService(EdgeChromiumDriverManager().install()), options=options)

    driver.get("https://myactivity.google.com/product/youtube")
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
        except:
            pass
    driver.refresh()
    time.sleep(5)
    input("✅ 手動確認已登入並顯示活動後，按 Enter 繼續...")

    seen_urls = set()
    seen_logs = set()
    results = []

    MAX_SCROLL_ROUNDS = 1
    EMPTY_ROUND_THRESHOLD = 3
    rounds = 0
    empty_rounds = 0
    last_header = None

    while rounds < MAX_SCROLL_ROUNDS:
        print(f"\n[SCROLL] 第 {rounds + 1} 次捲動 🔽")
        scroll_one_step_to_bottom(driver, pause=3)

        activities = driver.find_elements(By.CSS_SELECTOR, "div[role='listitem'], div.CW0isc")
        print(f"[INFO] 活動+日期區塊數量：{len(activities)}")
        new_found = 0

        for act in activities:
            try:
                headers = act.find_elements(By.CSS_SELECTOR, "div.MCZgpb > h2.rp10kf")
                if headers:
                    latest = headers[-1].text.strip()
                    if latest and latest != last_header:
                        last_header = latest
                        print(f"[📅 日期更新] 現在使用：{last_header}")
                
                title_elems = act.find_elements(By.CSS_SELECTOR, "div.QTGV3c a.l8sGWb")
                if not title_elems:
                    continue  # 沒有連結的活動略過
                title_elem = title_elems[0]
                title = title_elem.text.strip()
                title_url = title_elem.get_attribute("href")

                # 檢查是否為搜尋活動
                if title_url and "search_query=" in title_url:
                    if title_url in seen_urls:
                        continue
                    seen_urls.add(title_url)
                    print(f"[LOG] 搜尋活動偵測到：{title}", flush=True)
                    continue  # 目前不處理搜尋活動

                # 檢查是否為已查看活動
                qtgv3c_text = act.find_element(By.CSS_SELECTOR, "div.QTGV3c").text.strip()
                if qtgv3c_text.startswith("已查看「"):
                    if qtgv3c_text in seen_logs:
                        continue
                    seen_logs.add(qtgv3c_text)
                    print(f"[LOG] 已查看活動偵測到：{qtgv3c_text}", flush=True)
                    continue  # 目前不處理已查看活動

                if title_url in seen_urls or not title:
                    continue
                seen_urls.add(title_url)

                time_text = act.find_element(By.CSS_SELECTOR, "div.H3Q9vf.XTnvW").text
                time_label = time_text.split("•")[0].strip()

                if not last_header:
                    continue  # skip if no header yet

                full_time = f"{last_header} {time_label}"
                time_iso = parse_time(full_time, today_str)
                if not time_iso:
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
                with open("youtube_watch_history_stream.json", "w", encoding="utf-8") as f:
                    text = json.dumps(results, ensure_ascii=False, indent=2)
                    text = text.replace('},\n  {', '},{')
                    # 處理只有一個元素的陣列（subtitles/products/activityControls等）壓成一行，陣列後面可接逗號或右大括號
                    text = re.sub(r'\[\n\s+({.*?})\n\s+\](,?)', r'[\1]\2', text)
                    text = re.sub(r'\[\n\s+(".*?")\n\s+\](,?)', r'[\1]\2', text)
                    f.write(text)

                new_found += 1
                print(f"[✓] 新增：{title} @ {time_iso}")

            except Exception as e:
                print(f"[ERR] 活動處理失敗：{e}")
                continue

        if new_found == 0:
            empty_rounds += 1
            print(f"[INFO] 無新增（{empty_rounds}/{EMPTY_ROUND_THRESHOLD}）")
            if empty_rounds >= EMPTY_ROUND_THRESHOLD:
                print("[STOP] 無新活動，自動結束")
                break
        else:
            empty_rounds = 0

        rounds += 1

    print(f"\n✅ 共儲存 {len(results)} 筆活動至 youtube_watch_history_stream.json")
    driver.quit()

if __name__ == "__main__":
    main()
