import re
import csv
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


def get_soup(session, url):
    """Get BeautifulSoup object"""
    try:
        response = session.get(url)
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


def get_category_urls(url, soup):
    """Get urls of each cateagory"""
    # get href for each <a> in <div> that has side_categories class
    # dont get the books category that is the category of all books  
    category_relative_urls = [
        a['href'] for a in soup.select('.side_categories a')
        if 'books' not in a.get_text(strip=True).lower()
    ]
    category_urls = [
        urljoin(url, relative_url) for relative_url in category_relative_urls
    ]

    return category_urls


def get_book_urls(session, url, soup):
    """Get urls of each book in a category"""
    # get href for each <a> in <h3> for each <article> that has product_pod class
    book_relative_urls = [
        a['href'] for a in soup.select('.product_pod > h3 > a')
    ]
    # get url to next page
    # get <a> in <li> that has next class in <ul> thas has pager class
    # if not pager return None
    pager_relative_url = soup.select_one('.pager > .next > a')
    # loop on each page
    while pager_relative_url:
        pager_url = urljoin(url, pager_relative_url['href'])
        # get soup for the new page
        soup = get_soup(session, pager_url)
        # update pager url
        pager_relative_url = soup.select_one('.pager > .next > a')
        book_relative_urls.extend(
            [a['href'] for a in soup.select('.product_pod > h3 > a')]
        )
    # transform relative url to absolute url
    book_urls = [
        urljoin(url, relative_url) for relative_url in book_relative_urls
    ]

    return book_urls


def parse_rating(query, soup):
    """Change the rating number in word form to it's integer form"""
    text_to_int = {
        'one': 1,
        'two': 2,
        'three': 3,
        'four': 4,
        'five': 5,
    }
    # get the class name of <p class=star-rating Five>,
    # get only the second class and lower it
    rating = soup.select_one(query)['class'][1].lower()

    return text_to_int[rating] if rating in text_to_int.keys() else 'not-rated'


def parse_image_url(url, query, soup):
    """Create absolute url with the relative url"""
    # get the base url http://books.toscrape.com
    base_url = urljoin(url, '/')
    # get src attribute of <img>
    relative_url = soup.select_one(query)['src']

    return urljoin(base_url, relative_url)


def parse_product_information(soup):
    """Parse the table <tr> that contains product informations"""
    def transform(match):
        """re.sub repl function"""
        if match.group(1):
            return match.group(1)+'uding'
        elif match.group(2):
            return ''
        else:
            return '_'

    # list of all <th> values
    labels = extract_with_css('tr th', soup, True)
    # list of all <td> values
    values = extract_with_css('tr td',soup, True)
    excluding_values = ['product type', 'tax', 'number of reviews']
    product_information = {}
    for i, label in enumerate(labels):
        # exclude unwanted values
        if label.lower() not in excluding_values:
            if label.lower() == 'availability':
                label = 'number_available'
                # matches any digit character (0-9)
                # get only the number of available books
                values[i] = re.search(r'\d+', values[i]).group()
            if label.lower() == 'upc':
                label = 'universal_product_code'
            # \B matches any position that is not a word boundary.
            # \b matches a word boundary position between a word character
            # and non-word character or position (start / end of string).
            # \s matches any whitespace character (spaces, tabs, line breaks).
            # add 'uding' after (cl) group to get excluding and including
            # remove parenthesis and dot in the label if there are any
            # replace spaces by '_'
            # change the value of the string to an integer if it is a number
            # can use lambda instead of function :
            # lambda m: m.group(1)+'uding' if m.group(1) else ('' if m.group(2) else '_')
            # but line is too long
            label = re.sub(r'(\Bcl\b)|([().])|(\s)', transform, label.lower())
            product_information[label] = int(
                values[i]) if values[i].isdigit() else values[i]

    return product_information


def get_book(url, soup):
    """Create dictionary to store scraped values"""
    book = {}
    book['product_page_url'] = url
    # get <a> in the second last <li> in <ul> that has breadcrumb class
    book['category'] = extract_with_css(
        '.breadcrumb li:nth-last-child(2) a',
        soup
    )
    # get <h1>
    book['title'] = extract_with_css('h1', soup)
    # get <img> src attribute in <div> that has product_gallery id
    book['image_url'] = parse_image_url(
        book['product_page_url'],
        '#product_gallery img',
        soup
    )
    # get <p class=star-rating Five> class attribute
    # that is not in product_pod and parse it to get an integer
    book['review_rating'] = parse_rating(
        ':not(.product_pod) > .star-rating',
        soup
    )
    # get first <p> just after <div> that has product_description class
    book['product_description'] = extract_with_css(
        '#product_description + p',
        soup
    )
    # get product information
    product_information = parse_product_information(soup)
    for key, value in product_information.items():
        book[key] = value

    return book


def write_csv(dictionary, now):
    """Write dictionary in csv file"""
    base_directory = 'scraped_data'
    category_name = dictionary['category'].lower()
    file_name = f'{category_name}_{now}.csv'
    # create directories
    Path(base_directory, category_name).mkdir(parents=True, exist_ok=True)
    # get the path to the file
    file = Path(base_directory, category_name, file_name)
    # verify if the file exists
    file_exist = file.exists()
    with open(file, 'a', newline='', encoding='utf-8') as csv_file:
        header = dictionary.keys()
        writer = csv.DictWriter(csv_file, fieldnames=header)
        if not file_exist:
            writer.writeheader()
        writer.writerow(dictionary)


def get_datetime():
    """Get datetime using ISO format for file timestamp"""
    now = datetime.now()
    return now.strftime("%Y%m%dT%H%M%S")


def main():
    """Main function"""
    start_url = 'http://books.toscrape.com/'
    with requests.Session() as session:
        soup = get_soup(session, start_url)
        category_urls = get_category_urls(start_url, soup)
        # raise exception if no categories found in the page
        if not category_urls:
            print(
                'No category was found on the page for '
                'this url please select another one'
            )
            return None
        nb_category = len(category_urls)
        # use tqdm to show progess because it can be very long
        for i, category_url in enumerate(category_urls):
            soup = get_soup(session, category_url)
            category_name = extract_with_css('.breadcrumb > .active', soup)
            book_urls = get_book_urls(session, category_url, soup)
            now = get_datetime()
            description = f'{category_name} ({i+1}/{nb_category})'
            for book_url in tqdm(book_urls, desc=description):
                soup = get_soup(session, book_url)
                book = get_book(book_url, soup)
                write_csv(book, now)


if __name__ == '__main__':
    main()
