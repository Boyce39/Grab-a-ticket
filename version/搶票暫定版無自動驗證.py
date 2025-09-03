# -*- coding: utf-8 -*-
import os
import time
import certifi
from urllib.parse import urljoin
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
import undetected_chromedriver as uc

# ★ Chrome 相關設定
os.environ['SSL_CERT_FILE'] = certifi.where()
# 防止 undetected_chromedriver 解構子錯誤
uc.Chrome.__del__ = lambda self: None

def wait_for_sale_start(driver):
    """不停刷新直到「立即購票」按鈕可點"""
    while True:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, "li.buy a > div")
            if btn.is_displayed() and btn.is_enabled():
                return btn
        except NoSuchElementException:
            pass
        time.sleep(1)
        driver.refresh()

def main():
    url = input("輸入「搶票連結」：")
    choose_times = int(input("輸入「第 x 場次 (從 1 開始)」：")) - 1
    start_group = int(input("輸入初始 group 編號 (從 0 開始)："))
    ticket_num = input("輸入「張數」：")

    # 啟動 undetected-chromedriver
    opts = uc.ChromeOptions()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--start-maximized")
    driver = uc.Chrome(options=opts)
    wait = WebDriverWait(driver, 15)

    try:
        # 1. 前往並手動登入
        driver.get(url)
        input("❗️ 請先登入並停留在購票頁面，按 Enter 繼續…")

        # 2. 關閉 cookie 提示（如有）
        try:
            cb = wait.until(EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
            cb.click()
        except:
            driver.execute_script("document.querySelectorAll('.ot-sdk-container').forEach(el=>el.remove())")

        # 3. 等待開賣並點擊「立即購票」
        print("等待開賣…")
        buy_btn = wait_for_sale_start(driver)
        driver.execute_script("arguments[0].click();", buy_btn)

        # 4. 選擇場次
        scene_btns = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#gameList button.btn-primary")))
        if choose_times < 0 or choose_times >= len(scene_btns):
            print("❌ 場次錯誤")
            return
        driver.execute_script("arguments[0].click();", scene_btns[choose_times])

        # 5. 選位：動態掃描所有 group_n，從 start_group 開始，掃到尾再掃頭
        # 5.1 取得所有群組編號
        group_elems = driver.find_elements(By.CSS_SELECTOR, "ul[id^='group_']")
        group_indices = sorted(int(e.get_attribute("id").split("_")[1]) for e in group_elems)

        # 5.2 建立掃描順序：先大到尾，再從頭到 start_group-1
        order = [i for i in group_indices if i >= start_group] + \
                [i for i in group_indices if i < start_group]

        found = False
        for idx in order:
            try:
                ul = driver.find_element(By.ID, f"group_{idx}")
                # 該區第一個可選座位
                li = ul.find_element(By.CLASS_NAME, "select_form_b")
                a  = li.find_element(By.TAG_NAME, "a")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", a)
                a.click()
                print(f"✔️ 在 group_{idx} 區域點擊座位")
                found = True
                break
            except NoSuchElementException:
                print(f"⚠️ group_{idx} 無可選座位，跳下一個…")
                time.sleep(0.2)
                continue

        if not found:
            print("❌ 所有區域都無座位可選，請稍後再試")
            return

        # 6. 選張數 & 勾同意
        #   選張數
        for sel in driver.find_elements(By.TAG_NAME, "select"):
            s = Select(sel)
            vals = [o.get_attribute("value") for o in s.options if o.get_attribute("value")]
            if ticket_num in vals:
                s.select_by_value(ticket_num)
                break
        #   勾選同意條款
        agree = driver.find_element(By.ID, "TicketForm_agree")
        if not agree.is_selected():
            driver.execute_script("arguments[0].click();", agree)

        print("✔️ 已選擇張數並勾選同意條款")
        # 7. 停在驗證碼輸入階段，等待使用者手動輸入
        wait.until(EC.presence_of_element_located((By.ID, "TicketForm_verifyCode")))
        input("❗️ 請手動輸入驗證碼後按 Enter 結束…")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()
