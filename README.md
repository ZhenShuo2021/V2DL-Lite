# V2DL-Lite  
[English](/README.en.md)

超級輕量版本的 [V2PH-Downloader](https://github.com/ZhenShuo2021/V2PH-Downloader)

## Why V2DL-Lite?  
用瀏覽器自動化工具爬蟲覺得心有不甘，於是寫了一個 lite 版本。

此版本移除肥大的自動化工具，沒有麻煩的密碼設定，沒有眼花撩亂的自定義選項，只要準備好 cookie 檔案即可輕鬆下載。

## Usage

```sh  
pip install v2dl-lite  
v2dl-lite <url or urls.txt>  
```  

超方便！

## Cookie 登入  
Cookie 登入是必要的，使用 [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) 以 **Netscape** 格式匯出並且儲存在設定資料夾中 (預設在 `~/.config/v2dl`)。腳本會自動掃描所有包含  "**cookie**" 的 **txt** 檔案。

## 選項  
- `-f`: 不跳過已經存在的相簿  
- `-d`: 設定下載資料夾 (default: `~/Downloads/v2dl`).  
- `-c`: 設定 cookies 資料夾 (default: `~/.config/v2dl`).  
- `-l`: 設定語言，用於命名下載資料夾 (default: `zh-TW`).  
- `-v`: 顯示套件版本  

## Notes  
- 支援多 cookies 檔案  
- 網站的機器人檢查很嚴格，所以此版本可能需要很頻繁的更新 cookies
