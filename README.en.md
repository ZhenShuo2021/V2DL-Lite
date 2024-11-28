# V2DL-Lite  
A super lightweight version to [V2PH-Downloader](https://github.com/ZhenShuo2021/V2PH-Downloader).

## Why V2DL-Lite?  
I wanted a simpler way to bypass Cloudflare without relying on heavy browser automation tools. V2DL-Lite uses only cloudscraper and httpx, getting rid of unnecessary complexity.

This version removes bulky automation packages, complicated password setups, and confusing customizations. Just prepare your cookie file and start downloading images easily!

## Usage

```sh  
pip install v2dl-lite  
v2dl-lite <url or urls.txt>  
```  

Just that simple!

### Cookie Login (Required)  
Use [Cookie-Editor](https://chromewebstore.google.com/detail/cookie-editor/hlkenndednhfkekhgcdicdfddnkalmdm) to export your account cookies in **Netscape** format. Save the cookie file in the config directory (`~/.config/v2dl` by default). The script automatically scans for **txt** files with "**cookie**" in the name.

## Options  
- `-f`: Don't Skip already downloaded albums.  
- `-d`: Specify the download directory (default: `~/Downloads/v2dl`).  
- `-c`: Specify the cookies directory (default: `~/.config/v2dl`).  
- `-l`: Choose a preferred language for naming folders (default: `zh-TW`). To find your language code, press F12 on the website, then search for lang="xxx".  
- `-v`: Show the package version.  

## Notes  
- Supports multiple cookie files.  
- This site’s bot detection is strict, so you may need to update cookies frequently.  
