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

# ★ 指定你安裝的 tesseract.exe 路徑
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
        config = '--psm 8 -c tessedit_char_whitelist=0123456789'
        code = pytesseract.image_to_string(bw, config=config).strip()
        print(f"[嘗試 {attempt}] OCR 辨識：'{code}'")
        # 3. 輸入並提交
        inp = driver.find_element(By.ID, "TicketForm_verifyCode")
        inp.clear()
        inp.send_keys(code)
        submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        driver.execute_script("arguments[0].click();", submit_btn)
        # 4. 檢查結果
        try:
            # 如果跳出 alert，代表錯誤
            alert = driver.switch_to.alert
            text = alert.text
            alert.accept()
            print(f"❌ 收到 Alert：{text}，重試…")
            time.sleep(0.5)
            continue
        except:
            # 沒有 alert，檢查輸入框是否消失
            try:
                waiter.until(EC.invisibility_of_element_located((By.ID, "TicketForm_verifyCode")))
                print("✔️ OCR 成功，最終使用：", code)
                return code
            except TimeoutException:
                print("❌ 驗證碼輸入框依然存在，重試…")
                time.sleep(0.5)
                continue
    # 全部重試失敗 → 手動輸入
    manual = input("🚨 OCR 連續失敗，請手動輸入驗證碼：")
    inp = driver.find_element(By.ID, "TicketForm_verifyCode")
    inp.clear()
    inp.send_keys(manual)
    submit_btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
    driver.execute_script("arguments[0].click();", submit_btn)
    return manual

def main():
    # 1. 使用者輸入
    url = input("輸入「搶票連結」：")
    choose_times = int(input("輸入「第 x 場次 (從 1 開始)」："))
    groups = [g.strip() for g in input("輸入要嘗試的 group 區域（逗號分隔）：").split(',') if g.strip()]
    ticket_num = input("輸入「張數」：")

    # 2. 啟動 undetected-chromedriver
    opts = uc.ChromeOptions()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--start-maximized")
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    driver = uc.Chrome(options=opts)
    waiter = WebDriverWait(driver, 15)

    try:
        # 3. 登入並關閉 cookie overlay
        driver.get(url)
        input("❗️ 請先完成登入並保持在購票頁面，按 Enter 繼續…")
        try:
            cook_btn = waiter.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            driver.execute_script("arguments[0].click();", cook_btn)
            print("✔️ 已關閉 cookie 提示")
        except:
            driver.execute_script("document.querySelectorAll('.ot-sdk-container').forEach(el=>el.remove())")
            print("✔️ 已移除 cookie overlay")

        # 4. 點擊「立即購票」
        print("等待並點擊「立即購票」…")
        buy_btn = waiter.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "li.buy a > div")))
        driver.execute_script("arguments[0].click();", buy_btn)

        # 5. 選擇場次
        scene_btns = waiter.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#gameList button.btn-primary")))
        idx = choose_times - 1
        if not (0 <= idx < len(scene_btns)):
            print("❌ 場次錯誤，結束程式")
            return
        driver.execute_script("arguments[0].click();", scene_btns[idx])

        # 6. 選位
        while True:
            for grp in groups:
                try:
                    area = driver.find_element(By.ID, grp)
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", area)
                    time.sleep(0.3)
                    seats = area.find_elements(By.TAG_NAME, "a")
                    if seats:
                        driver.execute_script("arguments[0].click();", seats[0])
                        raise StopIteration
                except StopIteration:
                    break
                except:
                    pass
            else:
                driver.refresh()
                buy_btn = waiter.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "li.buy a > div")))
                driver.execute_script("arguments[0].click();", buy_btn)
                scene_btns = waiter.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#gameList button.btn-primary")))
                driver.execute_script("arguments[0].click();", scene_btns[idx])
                continue
            break

        # 7. 選張數 & 同意
        for sel in driver.find_elements(By.TAG_NAME, "select"):
            s = Select(sel)
            vs = [o.get_attribute('value') for o in s.options if o.get_attribute('value')]
            if ticket_num in vs:
                s.select_by_value(ticket_num)
                break
        agree = driver.find_element(By.ID, "TicketForm_agree")
        driver.execute_script("arguments[0].click();", agree)

        # 8. OCR 辨識並提交驗證碼
        final_code = recognize_and_submit_captcha(driver)
        print(f"🎉 最終使用的驗證碼：{final_code}")

        # 9. 等待使用者輸入銀行帳號
        input("請在網頁中輸入銀行帳號與付款資訊，完成後按 Enter 結束…")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
