# -*- coding: utf-8 -*-
import os
import time
import certifi
import requests
import ddddocr
from urllib.parse import urljoin
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    NoAlertPresentException
)
import undetected_chromedriver as uc

os.environ['SSL_CERT_FILE'] = certifi.where()
uc.Chrome.__del__ = lambda self: None    # 避免析構子錯誤
ocr = ddddocr.DdddOcr()                  # 載入一次模型

# 驗證碼圖片備份資料夾（方便校正）
CAPTCHA_DIR = r'C:\Users\boyce\Desktop\verify'
os.makedirs(CAPTCHA_DIR, exist_ok=True)

def wait_start(driver,th,tm):
    while True: #不斷刷新直到可以訂票
        nt=time.localtime() 
        if nt.tm_hour>=th and nt.tm_min>=tm:
            driver.refresh()
            while True:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, "li.buy a > div")
                    if btn.is_displayed() and btn.is_enabled():
                        return btn
                except :
                    pass
                #time.sleep(1)
                driver.refresh()
    
def recognize(driver, ticket_num, max_attempts=10):
    wait = WebDriverWait(driver, 5)
    for attempt in range(1, max_attempts + 1):
        print(f"\n--- 辨識第{attempt} 次嘗試 ---")

        # 1. 重選張數
        for sel in driver.find_elements(By.TAG_NAME, "select"):
            s = Select(sel)
            vals = [o.get_attribute("value") for o in s.options if o.get_attribute("value")]
            if ticket_num in vals:
                s.select_by_value(ticket_num)
                break

        # 2. 勾選同意條款
        chk = driver.find_element(By.ID, "TicketForm_agree")
        if not chk.is_selected():
            driver.execute_script("arguments[0].click()", chk)

        # 3. 找驗證碼路徑
        img_elem = wait.until(EC.presence_of_element_located((By.ID, "TicketForm_verifyCode-image")))

        # 4. 儲存驗證碼，測試用
        png_bytes = img_elem.screenshot_as_png
        ts = int(time.time() * 1000)
        path = os.path.join(CAPTCHA_DIR, f"cap_{ts}.png")
        with open(path, "wb") as f:
            f.write(png_bytes)

        # 5. 驗證
        code = ocr.classification(png_bytes).strip()
        print(f"[{attempt}]辨識: '{code}'")
        if not code:
            print("無法辨識 重試…")
            #time.sleep(1)
            continue

        # 6. 輸入並提交
        inp = driver.find_element(By.ID, "TicketForm_verifyCode")
        inp.clear(); inp.send_keys(code)
        btn = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        driver.execute_script("arguments[0].click()", btn)

        # 7. 檢查辨識結果
        #time.sleep(0.5)
        try:
            alert = driver.switch_to.alert
            print(f"收到辨識失敗：{alert.text}，重試…")
            alert.accept()
            #time.sleep(0.5)
            continue
        except NoAlertPresentException:
            try:
                wait.until(EC.invisibility_of_element_located((By.ID, "TicketForm_verifyCode")))
                print("驗證成功，使用驗證碼：", code)
                return code
            except TimeoutException:
                print("辨識錯誤，重試…")
                #time.sleep(0.5)
                continue

    # 多次失敗後手動
    manual = input("手動輸入驗證碼：")
    inp = driver.find_element(By.ID, "TicketForm_verifyCode")
    inp.clear(); inp.send_keys(manual)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    return manual

def main():
    # 使用者輸入

    url          = input("輸入「搶票連結」：")
    th,tm        = map(int,input("輸入搶票時間(例:18:00)):").split(":"))
    choose_times = int(input("輸入「第 x 場次 (從 1 開始)」：")) - 1
    start_group  = int(input("輸入位置編號 (從 1 開始)："))-1
    ticket_num   = input("輸入「張數」：")
    # 啟動瀏覽器
    opts   = uc.ChromeOptions()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--start-maximized")
    driver = uc.Chrome(options=opts)
    wait   = WebDriverWait(driver, 15)
    
    # 前往並登入
    driver.get(url)
    input("請先登入並保持在購票頁面，按 Enter 繼續…")
    t=time.time()
    # 關閉 cookie 提示
    try:
        cb = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
        cb.click()
    except:
        driver.execute_script("document.querySelectorAll('.ot-sdk-container').forEach(el=>el.remove())")

    # 等開賣並點「立即購票」
    print("刷新中等待開賣…")
    btn = wait_start(driver,th,tm)
    t=time.time()
    driver.execute_script("arguments[0].click()", btn)
    # 選場次
    scene_btns = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#gameList button.btn-primary")))
    if choose_times < 0 or choose_times >= len(scene_btns):
        print("場次錯誤")
        return
    driver.execute_script("arguments[0].click()", scene_btns[choose_times])
    
    while True:
        flag=False
        # 先移除可能攔截的 overlay
        driver.execute_script("document.querySelectorAll('.ot-sdk-container').forEach(el=>el.remove());")
        driver.execute_script("document.querySelectorAll('.modal-backdrop').forEach(el=>el.remove());")

        # 掃描並點選座位
        group_elems = driver.find_elements(By.CSS_SELECTOR, "ul[id^='group_']")
        group_ids   = sorted(int(e.get_attribute("id").split("_")[1]) for e in group_elems)
        order       = [i for i in group_ids if i >= start_group] + [i for i in group_ids if i < start_group]

        for idx in order:
            try:
                ul = driver.find_element(By.ID, f"group_{idx}")
                # 等待可見
                wait.until(EC.visibility_of(ul))
                # 找第一個可點 <a>
                a = ul.find_element(By.CSS_SELECTOR, "li.select_form_b a")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", a)
                # 用 JS click
                driver.execute_script("arguments[0].click();", a)
                print(f"在區域{idx} 點選座位")
                flag=True
                break
            except Exception as e:
                print(f"區域{idx} 無票，或點擊被攔截 ({e})，繼續…")
                #time.sleep(0.1)
        else:
            print("全部都無座位")
            #return
        if flag:
            break
        driver.refresh()
    
    #time.sleep(0.1)  # 等待張數/條款載入

    #辨識和提交驗證碼
    final_code = recognize(driver, ticket_num)
    print(f"\n最終驗證碼：{final_code}")
    print(f"花了{int(time.time()-t)}秒")
    input(" 驗證碼送出，請在瀏覽器完成付款資訊後按 Enter 結束…")

main()

