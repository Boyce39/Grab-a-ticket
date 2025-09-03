import os
import time
import certifi
import cv2
import numpy as np
import pytesseract
import requests
from io import BytesIO
from urllib.parse import urljoin
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException
import undetected_chromedriver as uc

# ★ 請確認這個路徑下有 tesseract.exe
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
os.environ['SSL_CERT_FILE'] = certifi.where()

def recognize_and_submit_captcha(driver, max_attempts=5):
    waiter = WebDriverWait(driver, 5)
    for attempt in range(1, max_attempts + 1):
        # 1. 下載並處理圖片
        img_elem = driver.find_element(By.ID, "TicketForm_verifyCode-image")
        rel_src = img_elem.get_attribute("src")
        full_url = urljoin(driver.current_url, rel_src)
        resp = requests.get(full_url)
        arr = np.frombuffer(resp.content, np.uint8)
        gray = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        # 放大 + 開運算 + 二值化
        h, w = gray.shape
        big = cv2.resize(gray, (w*2, h*2), interpolation=cv2.INTER_LINEAR)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2,2))
        opened = cv2.morphologyEx(big, cv2.MORPH_OPEN, kernel)
        _, bw = cv2.threshold(opened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # 2. OCR
        code = pytesseract.image_to_string(bw, config='--psm 8 -c tessedit_char_whitelist=0123456789').strip()
        print(f"[嘗試 {attempt}] OCR 辨識：'{code}'")
        # 3. 輸入並提交
        inp = driver.find_element(By.ID, "TicketForm_verifyCode")
        inp.clear()
        inp.send_keys(code)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        # 4. 檢查結果
        try:
            alert = driver.switch_to.alert
            text = alert.text
            alert.accept()
            print(f"❌ 收到 Alert：{text}，重試…")
            time.sleep(0.5)
            continue
        except:
            try:
                waiter.until(EC.invisibility_of_element_located((By.ID, "TicketForm_verifyCode")))
                print("✔️ OCR 成功，最終使用：", code)
                return code
            except TimeoutException:
                print("❌ 驗證碼輸入框依然存在，重試…")
                time.sleep(0.5)
                continue
    # 5. 全部重試失敗 → 手動
    manual = input("🚨 OCR 連續失敗，請手動輸入驗證碼：")
    inp = driver.find_element(By.ID, "TicketForm_verifyCode")
    inp.clear()
    inp.send_keys(manual)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    return manual

def main():
    # 1. 使用者輸入
    url = input("搶票連結：")
    choose_times = int(input("第幾場 (從 1 開始)："))
    groups = [g.strip() for g in input("group 區域 (逗號分隔)：").split(',') if g.strip()]
    ticket_num = input("張數：")

    # 2. 啟動瀏覽器
    opts = uc.ChromeOptions()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--start-maximized")
    opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    driver = uc.Chrome(options=opts)
    waiter = WebDriverWait(driver, 15)

    try:
        # 3. 登入
        driver.get(url)
        input("❗️ 請先登入並停留在購票頁面，按 Enter…")

        # 4. 點擊「立即購票」 (使用 Link Text 或 XPath)
        print("等待「立即購票」按鈕…")
        buy = waiter.until(EC.element_to_be_clickable((By.LINK_TEXT, "立即購票")))
        buy.click()

        # 關閉 cookie 提示 (如有)
        try:
            waiter.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))).click()
        except:
            pass

        # 5. 選場次
        scene_btns = waiter.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#gameList button.btn-primary")))
        idx = choose_times - 1
        if not (0 <= idx < len(scene_btns)):
            print("❌ 場次錯誤，結束")
            return
        scene_btns[idx].click()

        # 6. 選位
        while True:
            for grp in groups:
                try:
                    area = driver.find_element(By.ID, grp)
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", area)
                    time.sleep(0.3)
                    seats = area.find_elements(By.TAG_NAME, "a")
                    if seats:
                        seats[0].click()
                        raise StopIteration
                except StopIteration:
                    break
                except:
                    pass
            else:
                driver.refresh()
                buy = waiter.until(EC.element_to_be_clickable((By.LINK_TEXT, "立即購票")))
                buy.click()
                scene_btns = waiter.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#gameList button.btn-primary")))
                scene_btns[idx].click()
                continue
            break

        # 7. 選張數 & 同意
        for sel in driver.find_elements(By.TAG_NAME, "select"):
            s = Select(sel)
            vs = [o.get_attribute('value') for o in s.options if o.get_attribute('value')]
            if ticket_num in vs:
                s.select_by_value(ticket_num)
                break
        driver.find_element(By.ID, "TicketForm_agree").click()

        # 8. OCR 驗證碼並提交
        final_code = recognize_and_submit_captcha(driver)
        print(f"🎉 最終使用的驗證碼：{final_code}")

        # 9. 等待輸入銀行帳號
        input("請在網頁中輸入銀行帳號與付款資訊，完成後按 Enter…")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
