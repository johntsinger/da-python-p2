import re
import csv
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup


def get_soup(url):
    """Get BeautifulSoup object"""
    try:
        response = requests.get(url)
    except requests.ConnectionError as err:
        # raise ConnectionError if wrong url
        message = f'\nPlease check the url :\n - {url}'
        raise requests.ConnectionError(err, message)
    else:
        if response.ok:
            # change the encoding (ISO-8859-1) to utf-8 to avoid bad characters
            response.encoding = 'utf-8'

            return BeautifulSoup(response.text, 'lxml')
        # raise HTTPError if not response.ok
        response.raise_for_status()


def extract_with_css(query, soup, multi_values=False):
    """Extract value with css"""
    if multi_values:
        return [
            value.get_text(strip=True) if soup.select(query) else "" 
            for value in soup.select(query)
        ]
    return (
        soup.select_one(query)
        .get_text(strip=True) if soup.select_one(query) else ""
    )