# YouTube Watch History Scraper

鑒於Google takeout有匯出資料不完整的BUG，製作一個土法煉鋼的爬蟲工具，能夠批次擷取 Google myactivity YouTube 觀看紀錄，並將資料儲存為 JSON 檔案。

目前僅支援Windows Edge瀏覽器 + Google繁體中文介面使用，其他平台一律沒測試過。

有任何問題與建議都可以在issue上通知我。

## 使用方式

### 1. 安裝依賴
```bash
pip install selenium webdriver-manager
```

### 2. 取得 cookies
- 以Chrome瀏覽器插件（如 Get cookies.txt LOCALLY）匯出此網頁 myactivity.google.com 的 cookies，存為 `myactivity.google.com_cookies.txt`

### 3. 執行爬蟲
```bash
python watch-history-scraper.py --start-date 2025/06/27 --end-date 2025/06/20 --output my_output.json
```
- `--start-date`：指定爬取的起始日期（格式：YYYY/MM/DD）
- `--end-date`：指定爬取的停止日期(包含)（格式：YYYY/MM/DD）
- `--output`：輸出檔案名稱，預設為 `youtube_watch_history.json`

### 4. 自動開啟瀏覽器並登入
- 執行時會自動開啟瀏覽器，請確認Google帳號登入成功，程式會在短時間停頓後開始執行。

## 輸出格式
每一筆紀錄都會已以下格式儲存
```json
{
    "header": "YouTube",
    "title": "<影片標題>",
    "titleUrl": "https://www.youtube.com/watch?v=<video_id>",
    "subtitles": [
      {
        "name": "<頻道名稱>",
        "url": "https://www.youtube.com/channel/<channel_id>"
      }
    ],
    "time": "YYYY-MM-DDTHH:MM:SSZ"
    "products": ["YouTube"],
    "activityControls": ["YouTube watch history"]
}
```

## 注意事項
- 本工具僅供個人備份與學術研究，請勿用於商業或違反 Google 條款之用途。
- 若遇到 Google 反爬蟲，建議適當調整等待時間。

---

Made by Haha4ni
