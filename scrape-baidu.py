from scrapebaidu import *

import yaml
import logging
import asyncio

import yaml
import logging
import asyncio
import os
import re
from datetime import datetime

def main():
    logging.basicConfig()

    logger = logging.getLogger("scrape-baidu")

    with open("scrape-config.yml") as fp:
        config = yaml.safe_load(fp)

    if "log_level" in config:
        try:
            logger.setLevel({ 
                "critical": logging.CRITICAL,
                "fatal":    logging.FATAL,
                "error":    logging.ERROR ,
                "warning":  logging.WARNING,
                "warn":     logging.WARN,
                "info":     logging.INFO,
                "debug":    logging.DEBUG,
                "notset":   logging.NOTSET
            }[config['log_level']])
        except KeyError:
            logger.setLevel(logging.DEBUG)
            logger.error(f"Bad 'log_level': {config['log_level']}")
    else:
        logger.setLevel(logging.DEBUG)

    loop = asyncio.get_event_loop()

    search_list = config["search_list"]  if "search_list" in config else []
    search_pages = config["search_pages"]  if "search_pages" in config else 1
    inurl = config["inurl"] if "inurl" in config else False
    inurl_filter = config["inurl_filter"] if "inurl_filter" in config else False
    indomain_filter = config["indomain_filter"] if "indomain_filter" in config else False
    resolve_links = config["resolve_links"] if "resolve_links" in config else False
    whois_hosts = config["whois_hosts"] if "whois_hosts" in config else False
    proxy_list = config["proxy_list"] if "proxy_list" in config else []
    browser_timeout = config["browser_timeout"] if "browser_timeout" in config else 10
    lists_dir = config["list_dirs"] if "list_dirs" in config else os.path.join(".", "lists")
    
    working_dir = os.path.join(lists_dir, datetime.today().strftime('%Y%m%d%H%M%S'))    
    # working_dir = os.path.join(lists_dir, "20220523165245")    

    baidu_links_extracted_dir = os.path.join(working_dir, "baidu_extracted_links")
    baidu_whois_dir = os.path.join(lists_dir, 'baidu_whois')

    makeDirs([working_dir, baidu_links_extracted_dir, baidu_whois_dir])
    
    baidu_link_list = list(extractBaiduLinks(logger, search_list, search_pages, proxy_list, {
            "inurl": inurl,
            "browser_timeout": browser_timeout
        }))
    saveBaiduLinks(baidu_link_list, os.path.join(baidu_links_extracted_dir, "baidu_extracted_links.csv"), inurl)
    # baidu_link_list = list(loadBaiduLinks(os.path.join(baidu_links_extracted_dir, "baidu_extracted_links.csv")))

    if resolve_links:
        baidu_links_checked = list(checkBaiduLinks(logger, baidu_link_list,
            [
                re.compile(r"\/\/([^\.\/]+\.)?baidu\.")
            ],
            6, loop, {
                "inurl_filter": inurl_filter,
                "indomain_filter": indomain_filter
            }))
        saveBaiduCheckedLinks(baidu_links_checked, baidu_links_extracted_dir)

        extracted_host_list = getHostsFromCheckedBaiduLinks(baidu_links_checked)
        saveBaiduTargetHosts(extracted_host_list, os.path.join(baidu_links_extracted_dir, "baidu_extracted_hosts.txt"))
        # host_list = list(loadBaiduTargetHosts(os.path.join(baidu_links_extracted_dir, "baidu_extracted_hosts.txt")))

        if whois_hosts:
            whois_not_expired = []    
            whois_host_list = list(filterWhoisHosts(extracted_host_list, whois_not_expired, baidu_whois_dir))
            whois_info_list = list(getWhoisForHosts(logger, whois_host_list, 3, loop, 10))
            saveWhoisForHosts(logger, whois_info_list, whois_not_expired, baidu_whois_dir)


    # input("Press Enter to continue...")

if __name__ == '__main__':
    main()

