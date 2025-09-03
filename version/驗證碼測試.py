# -*- coding: utf-8 -*-
import os
import time
import certifi
import pytesseract
import requests
from urllib.parse import urljoin
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
import undetected_chromedriver as uc
import cv2

# 消除 undetected_chromedriver 解構子錯誤
uc.Chrome.__del__ = lambda self: None

# Tesseract 路徑設定
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
os.environ['SSL_CERT_FILE'] = certifi.where()

# CAPTCHA 圖片儲存資料夾
CAPTCHA_DIR = r'C:\Users\boyce\Desktop\verify'
os.makedirs(CAPTCHA_DIR, exist_ok=True)

def test_captcha(url, ticket_count="1"):
    # 啟動瀏覽器
    opts = uc.ChromeOptions()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--start-maximized")
    driver = uc.Chrome(options=opts)
    wait = WebDriverWait(driver, 15)

    try:
        driver.get(url)
        input("❗️ 請先登入並停留在驗證碼頁面（含張數、同意條款與 CAPTCHA），按 Enter 繼續…")

        # 定位張數、同意條款、CAPTCHA 元素
        select_loc  = (By.TAG_NAME, "select")
        agree_loc   = (By.ID, "TicketForm_agree")
        captcha_loc = (By.ID, "TicketForm_verifyCode-image")

        # 初次定位
        select_elem  = wait.until(EC.element_to_be_clickable(select_loc))
        agree_elem   = driver.find_element(*agree_loc)
        captcha_elem = wait.until(EC.presence_of_element_located(captcha_loc))
        last_src     = captcha_elem.get_attribute("src")

        attempt = 0
        while True:
            attempt += 1
            print(f"\n--- OCR 第 {attempt} 次嘗試 ---")

            # 1. 選張數 + 勾條款（每次重試前做一次）
            select_elem = wait.until(EC.element_to_be_clickable(select_loc))
            Select(select_elem).select_by_value(ticket_count)
            agree_elem = driver.find_element(*agree_loc)
            if not agree_elem.is_selected():
                driver.execute_script("arguments[0].click()", agree_elem)

            print(f"✔️ 已選擇 {ticket_count} 張票，✔️ 已勾選同意條款")

            # 2. 取得當前 CAPTCHA src（第一次用頁面載入的，之後由 server 自動刷新）
            captcha_elem = driver.find_element(*captcha_loc)
            current_src = captcha_elem.get_attribute("src")
            if attempt > 1:
                # server 在上一次 submit 後會自動換圖
                last_src = current_src

            full_url = urljoin(driver.current_url, last_src)
            print(f"[{attempt}] 下載 CAPTCHA：{full_url}")

            # 3. 下載並存檔
            resp = requests.get(full_url, timeout=5)
            ts = int(time.time() * 1000)
            save_path = os.path.join(CAPTCHA_DIR, f"cap_{ts}.png")
            with open(save_path, 'wb') as f:
                f.write(resp.content)
            print(f"[{attempt}] 存檔至：{save_path}")

            # 4. 等待檔案寫入完成
            prev_size = -1
            for _ in range(20):
                if os.path.exists(save_path):
                    size = os.path.getsize(save_path)
                    if size == prev_size and size > 0:
                        break
                    prev_size = size
                time.sleep(0.1)

            # 5. 讀檔並 OCR
            img = cv2.imread(save_path)
            if img is None:
                print("❌ 圖片讀取失敗，將手動輸入驗證碼")
                code = input("手動輸入驗證碼：")
            else:
                code = pytesseract.image_to_string(img).strip()
            print(f"[{attempt}] OCR → '{code}'")

            # 6. 輸入並送出（空字串也送出，讓 server 自動刷新）
            inp = driver.find_element(By.ID, "TicketForm_verifyCode")
            inp.clear()
            inp.send_keys(code)
            submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            driver.execute_script("arguments[0].click()", submit_btn)

            # 7. 判斷結果
            time.sleep(1)
            try:
                alert = driver.switch_to.alert
                print(f"❌ 伺服器回覆：{alert.text}，重試…")
                alert.accept()
                time.sleep(1)
                continue
            except:
                print("✔️ 驗證成功，使用驗證碼：", code)
                break

        print(f"\n🎉 完成！最終驗證碼：{code}")
        input("按 Enter 結束…")

    finally:
        driver.quit()

if __name__ == "__main__":
    test_captcha("https://tixcraft.com/ticket/ticket/25_maydaytp/19568/18/16", ticket_count="1")
