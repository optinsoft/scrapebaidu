# scrapebaidu

scrapebaidu is a Python script that scrapes baidu search results and resolves target links.

## Features

* Scrape baidu search results.
* Search in URLs and in domains.
* Resolve target links.
* Get WHOIS information for target domains, find expired domains.
* Supports proxies.

## Dependencies

1. Selenium: https://selenium-python.readthedocs.io/installation.html
2. Webdriver Manager: https://github.com/SergeyPirogov/webdriver_manager
3. aiohttp: https://pypi.org/project/aiohttp/
4. asynwhois: https://pypi.org/project/asyncwhois/
5. PyYAML: https://pypi.org/project/PyYAML/
6. dateutil: https://pypi.org/project/python-dateutil/

## Usage

```shell
$ python scrape-baidu.py
```

## Configuration file

`scrape-config.yml` example:

```yml
search_list:
  - book
  - food
  - hotel

search_pages: 3

inurl: false
inurl_filter: false
indomain_filter: false

resolve_links: true

whois_hosts: true

# proxy_list:
#  - 127.0.0.1:8888

browser_timeout: 10

headless: false

lists_dir: ./lists

log_level: debug
```

## Output directory structure

```
./lists/
├── 20220616114421/
│   └── baidu_extracted_links/
│       ├── baidu_extracted_hosts.txt
│       ├── baidu_extracted_links.csv
│       ├── baidu_links_empty.csv
│       ├── baidu_links_failed.csv
│       ├── baidu_links_other.csv
│       ├── baidu_links_rejected.csv
│       └── baidu_links_success.csv
└── baidu_whois/
    ├── baidu_whois_expired.csv
    ├── baidu_whois_failed.csv
    ├── baidu_whois_no_expires.csv
    ├── baidu_whois_not_expired.csv
    └── baidu_whois_not_found.csv
```
