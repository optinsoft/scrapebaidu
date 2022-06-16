#!/usr/bin/env python

# Copyright (c) 2022 Vitaly Yakovlev <vitaly@optinsoft.net>
#
# scrapebaidu - scrapes baidu search results and resolves target links.

from xmlrpc.client import boolean
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from logging import Logger
import re
from re import Pattern
import asyncio
from aiohttp import ClientSession, ClientTimeout
import asyncwhois
from asyncwhois.errors import NotFoundError
from datetime import datetime
import dateutil.parser
import os
from urllib.parse import urlparse, quote
import time
from itertools import cycle
import csv
from collections.abc import Iterable

def parsePage(browser: WebDriver, logger: Logger, pn: str, url_links: list[str], page_links: list[str]) -> str:
    url_link_re = re.compile(r"\/\/www\.baidu\.com\/link\?url=[^&]+")
    page_link_re = re.compile(r"\/\/www\.baidu\.com\/s\?(.+&)?pn=([1-9][0-9]*)0(&.+|$)")
    links = browser.find_elements(by=By.TAG_NAME, value="a")
    for link in links:
        href = link.get_attribute("href")
        # logger.debug("link:href:"+str(href or ''))
        if href is not None:
            m = url_link_re.search(href)
            if m:
                url_link = 'https:'+m.group(0)
                logger.debug(f"baidu url link:{url_link}")
                url_links.append(url_link)
            m = page_link_re.search(href)
            if m:
                page_link = 'https:'+m.group(0)
                # logger.debug(f"page link:{page_link}")
                page_pn = m.group(2).rjust(10, '0')                
                if page_pn > pn:
                    logger.debug(f"new page link:{page_link}")
                    pn = page_pn
                    page_links.append(page_link)
                # else:
                #    logger.debug(f"pn {page_pn} already exists")
    return pn

def delete_cache(driver):
    driver.execute_script("window.open('');")
    time.sleep(2)
    driver.switch_to.window(driver.window_handles[-1])
    time.sleep(2)
    driver.get('chrome://settings/clearBrowserData') # for old chromedriver versions use cleardriverData
    time.sleep(2)
    actions = ActionChains(driver) 
    actions.send_keys(Keys.TAB * 3 + Keys.DOWN * 3) # send right combination
    actions.perform()
    time.sleep(2)
    actions = ActionChains(driver) 
    actions.send_keys(Keys.TAB * 4 + Keys.ENTER) # confirm
    actions.perform()
    time.sleep(5) # wait some time to finish
    driver.close() # close this tab
    driver.switch_to.window(driver.window_handles[0]) # switch back

def extractSearchBaiduLinks(logger: Logger, search: str, max_pages: int, proxy: str = '', extract_options: dict = []) -> Iterable[str, str]:

    browser_timeout: int = extract_options["browser_timeout"] if "browser_timeout" in extract_options else 10
    headless: bool = extract_options["headless"] if "headless" in extract_options else False
    clear_cookies: bool = extract_options["clear_cookies"] if "clear_cookies" in extract_options else True
    clear_cache: bool = extract_options["clear_cache"] if "clear_cache" in extract_options else False

    page_links = []

    pn = ''

    options = webdriver.ChromeOptions()
    
    if headless:
        options.add_argument('--headless')
    if proxy:
        options.add_argument(f"--proxy-server={proxy}")

    options.add_experimental_option("prefs", {"profile. Managed_default_content_settings. Images": 2})
    options.add_experimental_option('excludeSwitches', ['enable automation '])

    browser = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    if clear_cookies:
        browser.delete_all_cookies()
    
    if clear_cache:
        delete_cache(browser)
        url = 'https://www.baidu.com/'
        browser.get(url)
        time.sleep(2)
        kw = browser.find_element(by=By.XPATH, value="//input[@id='kw']")
        kw.send_keys(search)
        time.sleep(2)
        su = browser.find_element(by=By.XPATH, value="//input[@id='su']")
        su.click()
    
    browser.implicitly_wait(2)

    url = 'https://www.baidu.com/s?wd=' + quote(search)
    try:
        browser.get(url)
    except TimeoutException:
        logger.warn("Loading took too much time!")
        return

    time.sleep(2)

    current_page = 0

    while True:
        page_ready = False
        
        try:
            WebDriverWait(browser, 5).until(EC.presence_of_element_located((By.CLASS_NAME, 'nors')))
            page_ready = True
            logger.debug(f"'{search}' not found!")
        except TimeoutException:
            # logger.warn("Loading took too much time!")
            logger.debug(f"Loading page  {current_page+1} for '{search}'...")
        
        if not page_ready:
            try:
                WebDriverWait(browser, browser_timeout).until(EC.presence_of_element_located((By.ID, 'page')))
                page_ready = True
                logger.debug(f"Page {current_page+1} is ready!")
            except TimeoutException:
                logger.warn("Loading took too much time!")
            if page_ready:
                url_links = []
                next_pn = parsePage(browser, logger, pn, url_links, page_links)
                for link in url_links:
                    yield (link, pn)
                pn = next_pn

        next_page = True

        while next_page:
            if current_page >= len(page_links):
                next_page = False
                break
            current_page += 1
            if current_page >= max_pages:
                next_page = False
                break
            url = page_links[current_page-1]
            try:
                browser.get(url)
                break
            except TimeoutException:
                logger.warn("Loading took too much time!")            

        if not next_page:
            break

    browser.close()
    browser.quit()

def saveBaiduLinks(baidu_link_list: list[str, str, str], filepath: str, inurl: bool = False):
    with open(filepath, "w", newline='') as fp:
        writer = csv.writer(fp, quoting=csv.QUOTE_ALL)
        for link, search, pn in baidu_link_list:
            writer.writerow([link, search, pn, "inurl" if inurl else ''])

def loadBaiduLinks(filepath: str) -> Iterable[str, str, str, bool]:
    with open(filepath, "r") as fp:
        reader = csv.reader(fp)
        #for link in fp:
        for row in reader:
            link = row[0]
            search = row[1] if len(row) > 1 else ''
            pn = row[2] if len(row) > 2 else ''
            inurl = "inurl" == row[3] if len(row) > 3 else False
            yield link.strip(), search.strip(), pn.strip(), inurl

async def fetch(logger: Logger, url: str, reject_patterns: list[Pattern], options: dict = []):
    inurl_filter: bool = options["inurl_filter"] if "inurl_filter" in options else False
    indomain_filter: bool = options["indomain_filter"] if "indomain_filter" in options else False
    search: str = options["search"] if "search" in options else ''
    timeout_seconds: int = options["fetch_timeout"] if "fetch_timeout" in options else  15
    try:
        session_timeout = ClientTimeout(total=None, sock_connect=timeout_seconds, sock_read=timeout_seconds)    
        async with ClientSession(timeout=session_timeout) as session:
            async with session.get(url, allow_redirects=False) as response:                
                if response.status == 200:
                    msg = f"status: {response.status}, not a redirect"
                    logger.debug(f"rejected URL: '{url}', {msg}")
                    return (url, "REJECTED", msg)
                if response.status not in [301, 302]:
                    msg = f"status: {response.status}, bad status"
                    logger.debug(f"failed URL: '{url}', {msg}")
                    return (url, "FAILED", msg)
                if 'location' not in response.headers:
                    msg = f"status: {response.status}, no location"
                    logger.debug(f"rejected URL: '{url}', {msg}")
                    return (url, "REJECTED", msg)
                location = response.headers['location']
                if not location:
                    msg = f"status: {response.status}, empty location"
                    logger.debug(f"rejected URL: '{url}', {msg}")
                    return (url, "REJECTED", msg)
                for p in reject_patterns:
                    if p.search(location):
                        msg = f"status: {response.status}, rejected location: '{location}'"
                        logger.debug(f"rejected URL: '{url}', {msg}")
                        return (url, "REJECTED", msg)
                locationURL = urlparse(location)
                host = locationURL.netloc
                if indomain_filter:
                    if (not search) or (search.lower() not in host.lower()):
                        msg = f"status: {response.status}, `{search}` is not in domain: '{host}', location: '{location}'"
                        logger.debug(f"rejected URL: '{url}', {msg}")
                        return (url, "REJECTED", msg)
                if inurl_filter:
                    if (not search) or (search.lower() not in location.lower()):
                        msg = f"status: {response.status}, `{search}` is not in url: '{location}'"
                        logger.debug(f"rejected URL: '{url}', {msg}")
                        return (url, "REJECTED", msg)
                logger.debug(f"redirect URL: '{url}', status: {response.status}, location: '{location}'")
                return (url, "OK", {"host": host, "location": location})
    except Exception as e:
        msg = str(e)
        if (msg):
            msg = type(e).__name__ + ": " + msg
        else:
            msg = type(e).__name__
        logger.debug(f"failed to get URL '{url}': {msg}")
        return (url, "FAILED", msg)

def checkBaiduLinks(logger: Logger, baidu_links: list[str or tuple[str, ...]], reject_patterns: list[Pattern], parallel_tasks: int, loop: asyncio.AbstractEventLoop, options: dict =  []) -> Iterable[str, str, str]:
    inurl_filter: bool = options["inurl_filter"] if "inurl_filter" in options else False
    indomain_filter: bool = options["indomain_filter"] if "indomain_filter" in options else False
    fetch_timeout: int = options["fetch_timeout"] if "fetch_timeout" in options else 15
    tasks = []
    for row in baidu_links:
        link = row[0] if type(row) is tuple else row
        search = row[1] if type(row) is tuple and len(row) > 1 else ''
        task = asyncio.ensure_future(fetch(logger, link, reject_patterns, {
            "inurl_filter": inurl_filter,
            "indomain_filter": indomain_filter,
            "search": search,
            "timeout": fetch_timeout
        }))
        tasks.append(task)
        if len(tasks) >= parallel_tasks:
            responses = loop.run_until_complete(asyncio.gather(*tasks))
            tasks = []
            for requestURL, responseStatus, responseResult in responses:
                yield (requestURL,responseStatus,responseResult)
    if len(tasks) > 0:
        responses = loop.run_until_complete(asyncio.gather(*tasks))
        for requestURL, responseStatus, responseResult in responses:
            yield (requestURL,responseStatus,responseResult)

def saveBaiduCheckedLinks(baidu_links_checked: list[tuple[str, str, str]], dir: str):
    with open(os.path.join(dir, "baidu_links_success.csv"), "w", newline='') as fp:
        writer = csv.writer(fp, quoting=csv.QUOTE_ALL)
        for requestURL, responseStatus, responseResult in baidu_links_checked:
            if responseStatus == 'OK':
                writer.writerow([requestURL,responseResult['host'],responseResult['location']])
    with open(os.path.join(dir, "baidu_links_failed.csv"), "w", newline='') as fp:
        writer = csv.writer(fp, quoting=csv.QUOTE_ALL)
        for requestURL, responseStatus, responseResult in baidu_links_checked:
            if responseStatus == 'FAILED':
                writer.writerow([requestURL,responseResult])
    with open(os.path.join(dir, "baidu_links_empty.csv"), "w", newline='') as fp:
        writer = csv.writer(fp, quoting=csv.QUOTE_ALL)
        for requestURL, responseStatus, responseResult in baidu_links_checked:
            if responseStatus == 'EMPTY':
                writer.writerow([requestURL,responseResult])
    with open(os.path.join(dir, "baidu_links_rejected.csv"), "w", newline='') as fp:
        writer = csv.writer(fp, quoting=csv.QUOTE_ALL)
        for requestURL, responseStatus, responseResult in baidu_links_checked:
            if responseStatus == 'REJECTED':
                writer.writerow([requestURL,responseResult])
    with open(os.path.join(dir, "baidu_links_other.csv"), "w", newline='') as fp:
        writer = csv.writer(fp, quoting=csv.QUOTE_ALL)
        for requestURL, responseStatus, responseResult in baidu_links_checked:
            if responseStatus not in ['OK','FAILED','EMPTY','REJECTED']:
                writer.writerow([requestURL,responseStatus,responseResult])

def getHostsFromCheckedBaiduLinks(baidu_links_checked) -> list[str]:
    hosts = set()
    for requestURL, responseStatus, responseResult in baidu_links_checked:
        if responseStatus == 'OK':
            hosts.add(responseResult['host'])
    return list(hosts)

def saveBaiduTargetHosts(host_list: list[str], filepath: str):
    with open(filepath, "w") as fp:
        for host in host_list:
            fp.write(f"{host}\n")

def loadBaiduTargetHosts(filepath: str) -> Iterable[str]:
    with open(filepath, "r") as fp:
        for line in fp:
            yield line.strip()

async def whois_lookup(logger: Logger, host: str, whois_timeout: int = 15):
    try:
        whois_result = await asyncwhois.aio_whois_domain(domain=host, timeout=whois_timeout)
        logger.debug(whois_result.query_output)
        if whois_result.query_output is None:
            logger.debug(f"no whois response for '{host}'")
            return (host, 'FAILED', 'query_output is None')
        expires_str = ''
        expires = None
        expires_re = re.compile(r"(?i)(expiry|expiration)\s(date|time):\s?([0-9T:+-]+Z?)")
        query_output = []
        for line in str(whois_result.query_output or '').split('\n'):
            line = line.strip()
            if expires is None:
                m = expires_re.search(line)
                if m:
                    expires_str = m.group(3)
                    expires = dateutil.parser.parse(expires_str)
            query_output.append(line)
        '''
        if whois_result.parser_output is None:
            logger.debug(f"unable parse whois for '{host}'")
            return (host, 'FAILED', 'parser_output is None')
        '''
        return (host, 'OK', {"expires_str":expires_str,"expires":expires,"query_output":query_output})
    except NotFoundError as e:
        msg = str(e)
        if (msg):
            msg = type(e).__name__ + ": " + msg
        else:
            msg = type(e).__name__
        logger.debug(f"whois not found for '{host}', {msg}")
        return (host, 'NOT_FOUND', str(e))
    except Exception as e:
        msg = str(e)
        if (msg):
            msg = type(e).__name__ + ": " + msg
        else:
            msg = type(e).__name__
        logger.debug(f"whois failed for '{host}', {msg}")
        return (host, 'FAILED', msg)

def getWhoisForHosts(logger: Logger, host_list: list[str], parallel_tasks: int, loop: asyncio.AbstractEventLoop, whois_timeout: int = 15) -> Iterable[str, str, str]:
    tasks = []
    for host in host_list:
        logger.debug(f"Checking whois for {host}")
        '''
        w = whois.whois(host)
        logger.debug(f"whois for {host}:\n\n{w}")
        '''
        task = asyncio.ensure_future(whois_lookup(logger, host, whois_timeout))
        tasks.append(task)
        if len(tasks) >= parallel_tasks:
            responses = loop.run_until_complete(asyncio.gather(*tasks))
            for host, status, whois_result in responses:
                yield (host, status, whois_result)
            tasks = []    
    if len(tasks) > 0:
        responses = loop.run_until_complete(asyncio.gather(*tasks))
        for host, status, whois_result in responses:
            yield (host, status, whois_result)

def saveWhoisForHosts(logger: Logger, whois_info_list, whois_not_expired: list[str or tuple[str, ...]], dir: str):
    now_timestamp =  datetime.timestamp(datetime.now())
    not_expired = []
    with open(os.path.join(dir, "baidu_whois_expired.csv"), "w", newline='') as fp:
        writer = csv.writer(fp, quoting=csv.QUOTE_ALL)
        for host, status, whois_result in whois_info_list:
            expired = False
            if status == 'OK':
                if whois_result['expires'] is not None:
                    if datetime.timestamp(whois_result['expires']) <= now_timestamp:
                        expired = True
                        writer.writerow([host,whois_result['expires'].isoformat(),whois_result['expires_str'],str(whois_result['query_output']).encode("utf8")])
                else:
                    logger.debug(f"no 'expires' info in whois for '{host}'")
                    status = 'NO_EXPIRES'
            if not expired:
                not_expired.append((host, status, whois_result))
    with open(os.path.join(dir, "baidu_whois_not_found.csv"), "w", newline='') as fp:
        writer = csv.writer(fp, quoting=csv.QUOTE_ALL)
        for host, status, whois_result in not_expired:
            if status == 'NOT_FOUND':
                writer.writerow([host,whois_result.encode("utf8")])
    with open(os.path.join(dir, "baidu_whois_failed.csv"), "w", newline='') as fp:
        writer = csv.writer(fp, quoting=csv.QUOTE_ALL)
        for host, status, whois_result in not_expired:
            if status == 'FAILED':
                writer.writerow([host,whois_result.encode("utf8")])
    with open(os.path.join(dir, "baidu_whois_no_expires.csv"), "w", newline='') as fp:
        writer = csv.writer(fp, quoting=csv.QUOTE_ALL)
        for host, status, whois_result in not_expired:
            if status == 'NO_EXPIRES':
                writer.writerow([host,status,whois_result['expires_str'],str(whois_result['query_output']).encode("utf8")])
    with open(os.path.join(dir, "baidu_whois_not_expired.csv"), "w", newline='') as fp:
        writer = csv.writer(fp, quoting=csv.QUOTE_ALL)
        for row in whois_not_expired:
            writer.writerow(row)
        for host, status, whois_result in not_expired:
            if status == 'OK':
                writer.writerow([host,status,whois_result['expires'].isoformat(),whois_result['expires_str'],str(whois_result['query_output']).encode("utf8")])
            elif status not in ['NOT_FOUND', 'FAILED', 'NO_EXPIRES']:
                writer.writerow([host,status,whois_result.encode("utf8")])

def filterWhoisHosts(host_list: list[str], whois_not_expired: list[str or tuple[str, ...]], dir: str) -> Iterable[str]:
    exclude_hosts = set()
    if os.path.exists(os.path.join(dir, "baidu_whois_exclude.txt")):
        with open(os.path.join(dir, "baidu_whois_exclude.txt"), "r") as fp:
            for line in fp:
                host = line.strip()
                if host:
                    exclude_hosts.add(host)
    if (os.path.exists(os.path.join(dir, "baidu_whois_not_expired.csv"))):
        with open(os.path.join(dir, "baidu_whois_not_expired.csv"), "r") as fp:
            reader = csv.reader(fp)
            now_timestamp =  datetime.timestamp(datetime.now())
            for row in reader:
                if len(row) > 0:
                    host = row[0].strip()
                    if host and len(row) > 2:
                        expires = datetime.fromisoformat(row[2].strip())
                        if datetime.timestamp(expires) > now_timestamp:
                            exclude_hosts.add(host)
                            whois_not_expired.append(row)
    for host in host_list:
        if host and host not in exclude_hosts:
            yield host

def makeDirs(dirlist: list[str]):
    for dir in dirlist:
        if not os.path.exists(dir):
            os.makedirs(dir)

def extractBaiduLinks(logger: Logger, search_list: list[str], max_pages: int, proxy_list: list[str], options: dict = []) -> Iterable[str, str, str]:
    inurl: bool = options["inurl"] if "inurl" in options else False
    browser_timeout: int = options["browser_timeout"] if "browser_timeout" in options else 10
    headless: bool = options["headless"] if "headless" in options else False
    clear_cookies: bool = options["clear_cookies"] if "clear_cookies" in options else True
    clear_cache: bool = options["clear_cache"] if "clear_cache" in options else False
    proxy_cycle = cycle(proxy_list)
    baidu_link_set = set()
    for search in search_list:
        proxy = next(proxy_cycle, '')
        s = "inurl: " + search if inurl else search
        for link, page in extractSearchBaiduLinks(logger, s, max_pages, proxy, {
                "browser_timeout": browser_timeout,
                "headless": headless,
                "clear_cookies": clear_cookies,
                "clear_cache": clear_cache
            }):
            if not link in baidu_link_set:
                baidu_link_set.add(link)
                yield (link, search, page)
