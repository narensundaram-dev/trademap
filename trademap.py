import os
import re
import sys
import time
import math
import json
import string
import shutil
import logging
import argparse
import traceback
from datetime import datetime as dt
from concurrent.futures import as_completed, ThreadPoolExecutor

import requests
import pandas as pd
from bs4 import BeautifulSoup, NavigableString

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


__author__ = "Naren Sundaram"
__email__ = "narensundaram007@gmail.com"
__mobile__ = "+91 8678910063"


TRADE_INDICATORS, Q_TIME_SERIES, COMPANIES = "ti", "qt", "cmp"
REPORT_TYPES = {
    TRADE_INDICATORS: {
        "name": "Trade Indicators",
        "target_id": "ctl00_PageContent_Button_TradeIndicators",
    },
    Q_TIME_SERIES: {
        "name": "Quarterly Time Series",
        "target_id": "ctl00_PageContent_Button_TimeSeries_Q"
    },
    COMPANIES: {
        "name": "Companies",
        "target_id": "ctl00_PageContent_Button_Companies"
    }
}


def get_logger():
    log = logging.getLogger(os.path.split(__file__)[-1])
    log_level = logging.INFO
    log.setLevel(log_level)
    log_handler = logging.StreamHandler()
    log_formatter = logging.Formatter('%(levelname)s: %(asctime)s - %(name)s:%(lineno)d - %(message)s')
    log_handler.setFormatter(log_formatter)
    log.addHandler(log_handler)
    return log

log = get_logger()


class DropDownLoaded:
    
    def __init__(self, target_id):
        self.target_id = target_id
    
    def __call__(self, chrome):
        dropdown_product = chrome.find_element_by_id(self.target_id)
        product = dropdown_product.find_element_by_xpath(".//*").text
        return "loading" not in product.lower()


class TradeMapScraper:

    def __init__(self, count, product_id, country, args, settings):
        self.count = count
        self.product_id = product_id
        self.country = country
        self.args = args
        self.settings = settings

        self.url = "https://www.trademap.org/Index.aspx"
        self.dir_output = self.get_dir_output()
        self.chrome = self.get_chrome_driver()
        self.page_load_timeout = self.settings["page_load_timeout"]["value"]
    
    def get_dir_output(self):
        label = REPORT_TYPES[self.args.type]["name"].lower().replace(" ", "-")
        dirs = [TradeMapManager.dir_output, f"{self.product_id}-{self.country}", label]
        return os.path.join(*dirs)


    def get_chrome_driver(self):
        chrome_options = webdriver.ChromeOptions()
        prefs = {"profile.default_content_settings.popups": 0,
                "download.default_directory": self.dir_output + "/",
                "directory_upgrade": True}
        chrome_options.add_experimental_option("prefs", prefs)
        driver_path = self.settings["driver_path"]["value"]
        return webdriver.Chrome(driver_path, options=chrome_options)

    def setup(self):
        os.makedirs(self.dir_output, exist_ok=True)

    def login(self):
        username, password = self.settings["credentials"]["username"], self.settings["credentials"]["password"]

        self.chrome.get(self.url)
        self.chrome.find_element_by_id("ctl00_MenuControl_marmenu_login").click()

        WebDriverWait(self.chrome, self.page_load_timeout).until(EC.presence_of_element_located((By.ID, "Username")))
        self.chrome.find_element_by_id("Username").send_keys(username)
        self.chrome.find_element_by_id("Password").send_keys(password)
        self.chrome.find_element_by_xpath("/html/body/div[3]/div/div[2]/div/div/div/form/fieldset/div[4]/div/button").click()

    def select_product_id(self):
        input_product_id = "ctl00_PageContent_RadComboBox_Product_Input"
        WebDriverWait(self.chrome, self.page_load_timeout).until(
            EC.presence_of_element_located((By.ID, input_product_id))
        )
        input_product = self.chrome.find_element_by_id(input_product_id)

        while True:
            input_product.clear()
            input_product.send_keys(self.product_id)
            if input_product.get_attribute("value") == self.product_id:
                break
        
        target_id = "ctl00_PageContent_RadComboBox_Product_DropDown"
        WebDriverWait(self.chrome, self.page_load_timeout).until(DropDownLoaded(target_id))
        element_product = self.chrome.find_element_by_id(target_id).find_element_by_xpath(".//*")
        element_product.click()

    def select_country(self):
        input_country_id = "ctl00_PageContent_RadComboBox_Country_Input"
        WebDriverWait(self.chrome, self.page_load_timeout).until(
            EC.presence_of_element_located((By.ID, input_country_id))
        )
        input_country = self.chrome.find_element_by_id(input_country_id)

        while True:
            input_country.clear()
            input_country.send_keys(self.country)
            if input_country.get_attribute("value") == self.country:
                break

        target_id = "ctl00_PageContent_RadComboBox_Country_DropDown"
        dropdown_country = self.chrome.find_element_by_id(target_id)
        WebDriverWait(self.chrome, self.page_load_timeout).until(DropDownLoaded(target_id))
        for element_country in dropdown_country.find_elements_by_xpath(".//*"):
            if element_country.text.lower() == self.country.lower():
                element_country.click()

    def await_downloads(self, dir, timeout):
        seconds, dl_wait = 0, True
        while dl_wait and seconds < timeout:
            time.sleep(1)
            dl_wait = False

            files = os.listdir(dir)
            for fname in files:
                if fname.endswith('.crdownload'):
                    dl_wait = True

            seconds += 1
        return seconds

    def do_download_fa_cmps(self):
        # Store main window
        main_window = self.chrome.current_window_handle

        # Open companies in new tab, Navigate to that new tab
        def open_cmps_in_new_tab():
            btn_companies = self.chrome.find_element_by_id("ctl00_PageContent_Button_Companies")
            ActionChains(self.chrome).key_down(Keys.CONTROL).click(btn_companies).key_up(Keys.CONTROL).perform()
            
            while len(self.chrome.window_handles) > 1:
                self.chrome.switch_to.window(self.chrome.window_handles[1])
                break

        # Set 300 per page
        def set_max_paginate():
            WebDriverWait(self.chrome, self.page_load_timeout).until(
                EC.presence_of_element_located((By.ID, "ctl00_PageContent_MyGridView1"))
            )

            dropdown_pagination = Select(self.chrome.find_element_by_id(
                "ctl00_PageContent_GridViewPanelControl_DropDownList_PageSize"))
            dropdown_pagination.select_by_value("300")

            WebDriverWait(self.chrome, self.page_load_timeout).until(
                EC.presence_of_element_located((By.ID, "ctl00_PageContent_MyGridView1"))
            )
            return self.chrome.find_element_by_id("ctl00_PageContent_MyGridView1")

        open_cmps_in_new_tab()
        table_cmps = set_max_paginate()

        trs = table_cmps.find_elements_by_xpath(".//tr[@align='right']")
        for num in range(len(trs)):
            table_cmps = set_max_paginate()

            # Click the num element, sleep for 1s and close
            tr = table_cmps.find_elements_by_xpath(".//tr[@align='right']")[num]
            company = tr.find_element_by_tag_name("a")
            company.click()
            set_max_paginate()

            self.download_imp_exp_ttype()
            self.chrome.close()

            # Switch to main window, Open companies in new tab, Navigate to that new tab
            self.chrome.switch_to.window(main_window)
            open_cmps_in_new_tab()

    def click_xlsx_icon(self):
        WebDriverWait(self.chrome, self.page_load_timeout).until(
            EC.presence_of_element_located((By.ID, "ctl00_PageContent_MyGridView1"))
        )
        self.chrome.find_element_by_id("ctl00_PageContent_GridViewPanelControl_ImageButton_ExportExcel").click()
        self.await_downloads(self.dir_output, self.page_load_timeout)

    def download_imp_exp_ttype(self):
        # Default trade type is 'import'
        self.click_xlsx_icon()

        # Change trade type to 'export', and then click xlsx icon.
        dropdown_trade_type = Select(self.chrome.find_element_by_id("ctl00_NavigationControl_DropDownList_TradeType"))
        dropdown_trade_type.select_by_value("E")
        self.click_xlsx_icon()

    def download_xlsx(self):
        target_id = REPORT_TYPES[self.args.type]["target_id"]

        if self.args.type in (TRADE_INDICATORS, Q_TIME_SERIES):
            self.chrome.find_element_by_id(target_id).click()
            self.download_imp_exp_ttype()
        
        else:
            self.do_download_fa_cmps()

    def store(self):
        log.info(f"Fetching for {self.product_id}:{self.country} - ({self.count})")
        try:
            self.setup()
            self.login()
            self.select_product_id()
            self.select_country()
            self.download_xlsx()
        except Exception as e:
            log.error("ERROR: Error on fetching the data!")
            log.error(f"DESC: {type(e)} - {e}")
            # traceback.print_exc()
        finally:
            self.chrome.quit()


class TradeMapManager:
    dir_output = os.path.join(os.getcwd(), "output")

    def __init__(self, args, settings):
        self.args = args
        self.settings = settings

    def setup(self):
        os.makedirs(self.dir_output, exist_ok=True)

    def fetch(self):
        workers = self.settings["workers"]["value"]
        count = 0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = []
            products = pd.read_csv("products.csv").to_dict('records')
            for product in products:
                count += 1
                future = executor.submit(
                    TradeMapScraper(count, str(product["product_id"]), product["country"], self.args, self.settings).store
                )
                futures.append(future)
        for future in as_completed(futures):
            future.result()


def get_settings():
    with open("settings.json", "r") as f:
        return json.load(f)


def get_args():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        '-t', "--type", type=str, 
        choices=list(REPORT_TYPES.keys()), required=True, 
        help="'ti': Trade Indicators; 'qt': Quarterly Time Series; 'cmp': Companies")
    return arg_parser.parse_args()


def main():
    start = dt.now()
    log.info("Script starts at: {}".format(start.strftime("%d-%m-%Y %H:%M:%S %p")))

    args, settings = get_args(), get_settings()
    manager = TradeMapManager(args, settings)

    manager.setup()
    manager.fetch()

    end = dt.now()
    log.info("Script ends at: {}".format(end.strftime("%d-%m-%Y %H:%M:%S %p")))
    elapsed = round(((end - start).seconds / 60), 4)
    log.info("Time Elapsed: {} minutes".format(elapsed))


if __name__ == "__main__":
    main()
